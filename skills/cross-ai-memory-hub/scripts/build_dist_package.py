#!/usr/bin/env python3
"""
build_dist_package.py — Builds a clean, zero-PII, universal distribution ZIP package
of the Self-Improving Cross-AI Memory & Persona Agent Archetype (v3.0).

Output:
  dist/universal-self-improving-agent-v3.0.zip
  Contains:
    - Install_Mac.command (Double-click installer for macOS)
    - Install_Windows.bat (Double-click installer for Windows)
    - README_QUICKSTART.md
    - SKILL.md
    - scripts/ (universal_hub_installer.py, setup_obsidian.sh, health_check.py, engine/*)
  Guarantees:
    - Zero personal session logs, zero SQLite databases, zero API keys/secrets included.
"""

import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = SKILL_ROOT.parent.parent.parent
DIST_DIR = REPO_ROOT / "dev" / "ai-shared-memory" / "dist"


MAC_COMMAND_SCRIPT = """#!/usr/bin/env bash
# Double-click installer for macOS
set -euo pipefail
cd "$(dirname "$0")"

echo "=================================================================="
echo "🚀 Universal Self-Improving AI Agent Hub (v3.0) — セットアップ"
echo "=================================================================="
echo ""
read -r -p "あなたの氏名（または屋号・ハンドルネーム）を入力してください [EnterでOS名を使用]: " USER_NAME
echo ""

if [ -n "${USER_NAME}" ]; then
    bash scripts/setup_obsidian.sh "" "${USER_NAME}"
else
    bash scripts/setup_obsidian.sh
fi

echo ""
echo "🎉 セットアップが完了しました！このウィンドウを閉じて構いません。"
read -r -p "Enterキーを押して終了..." _
"""

WIN_BAT_SCRIPT = """@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ==================================================================
echo Universal Self-Improving AI Agent Hub (v3.0) - Setup
echo ==================================================================
echo.
set /p USER_NAME="Enter your name (or press Enter for default): "
echo.
if "%USER_NAME%"=="" (
    python scripts\\universal_hub_installer.py --sync-now --install-daemon
) else (
    python scripts\\universal_hub_installer.py --persona-name "%USER_NAME%" --sync-now --install-daemon
)
echo.
echo Setup complete!
pause
"""

QUICKSTART_MD = """# Universal Self-Improving AI Agent Hub (v3.0) — クイックスタートガイド

Claude Code、OpenAI Codex、Google Antigravity (Gemini)、および ChatGPT の全対話履歴・音声入力を Obsidian Vault に一元集約し、**使うほどあなた自身の言葉（使う言葉・反応する言葉・行動する言葉・NG表現）を自己学習して進化する汎用エージェント原型モデル**です。

---

## 1. 導入方法（30秒）

### macOS の場合
1. フォルダ内の **`Install_Mac.command`** をダブルクリックします（またはターミナルで `bash scripts/setup_obsidian.sh` を実行）。
2. 名前を聞かれたら入力して Enter を押すだけで、Obsidian Vault の自動検出・構築・初回同期・10分毎のバックグラウンド自動同期がすべて設定されます。

### Windows / Linux / WSL の場合
- **Windows**: **`Install_Windows.bat`** をダブルクリックします。
- **Linux / WSL**: ターミナルで `bash scripts/setup_obsidian.sh` を実行します。

---

## 2. 導入直後に使える主要コマンド

```bash
# 初期データが少ない場合：5問の人格コア抽出インタビュー（5分）
ai-memory onboard --interview

# 全AIの過去チャット横断検索
chat-archive search "検索ワード"

# 自己改善型・人格コア＆SNSドラフト（X / Threads / note）の即時生成
ai-memory persona --mode sync
ai-memory persona --mode sns

# 重要な意思決定や教訓の記録
ai-memory record --type lesson --title "教訓タイトル" --content "内容"
```
"""


def verify_no_leaks(staging_dir: Path):
    """Deterministic security check ensuring no personal DBs, logs, or secrets are bundled."""
    forbidden_exts = {".db", ".sqlite", ".jsonl", ".zst", ".env", ".pem", ".key"}
    secret_re = re.compile(r"\b(?:sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_-]{30,})\b")

    for p in staging_dir.rglob("*"):
        if p.is_dir():
            continue
        if p.suffix.lower() in forbidden_exts:
            raise RuntimeError(f"Security gate blocked forbidden file in distribution: {p}")
        if p.suffix.lower() in {".py", ".sh", ".md", ".command", ".bat"}:
            txt = p.read_text(encoding="utf-8", errors="ignore")
            if secret_re.search(txt):
                raise RuntimeError(f"Security gate blocked potential secret in: {p}")


def build_package() -> Path:
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = DIST_DIR / "universal-self-improving-agent-v3.0.zip"

    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / "universal-self-improving-agent"
        scripts_dst = stage / "scripts"
        engine_Archive_dst = scripts_dst / "engine" / "ai-chat-archive"
        engine_mem_dst = scripts_dst / "engine" / "ai-shared-memory"
        (engine_Archive_dst / "bin").mkdir(parents=True, exist_ok=True)
        engine_mem_dst.mkdir(parents=True, exist_ok=True)

        # Copy SKILL.md & top-level installers
        shutil.copy2(SKILL_ROOT / "SKILL.md", stage / "SKILL.md")
        (stage / "README_QUICKSTART.md").write_text(QUICKSTART_MD, encoding="utf-8")

        mac_cmd = stage / "Install_Mac.command"
        mac_cmd.write_text(MAC_COMMAND_SCRIPT, encoding="utf-8")
        mac_cmd.chmod(0o755)

        win_bat = stage / "Install_Windows.bat"
        win_bat.write_text(WIN_BAT_SCRIPT, encoding="utf-8")

        # Copy core scripts
        for s_name in ["universal_hub_installer.py", "setup_obsidian.sh", "health_check.py"]:
            src = SKILL_ROOT / "scripts" / s_name
            if src.exists():
                shutil.copy2(src, scripts_dst / s_name)
                (scripts_dst / s_name).chmod(0o755)

        # Copy latest verified engine files
        src_archive = REPO_ROOT / "dev" / "ai-chat-archive"
        for f_name in ["indexer.py", "obsidian_exporter.py", "reader.py", "cli.py"]:
            if (src_archive / f_name).exists():
                shutil.copy2(src_archive / f_name, engine_Archive_dst / f_name)
        if (src_archive / "bin" / "auto-sync-obsidian.sh").exists():
            shutil.copy2(src_archive / "bin" / "auto-sync-obsidian.sh", engine_Archive_dst / "bin" / "auto-sync-obsidian.sh")

        src_mem = REPO_ROOT / "dev" / "ai-shared-memory"
        for f_name in ["compiler.py", "persona_extractor.py", "onboarding_coach.py", "recorder.py", "cli.py"]:
            if (src_mem / f_name).exists():
                shutil.copy2(src_mem / f_name, engine_mem_dst / f_name)

        # Run deterministic leak check
        verify_no_leaks(stage)

        # Create ZIP archive
        if zip_path.exists():
            zip_path.unlink()
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_p in sorted(stage.rglob("*")):
                if file_p.is_file():
                    arcname = file_p.relative_to(Path(tmp))
                    zf.write(file_p, arcname)

    print(f"✅ Clean distribution package built & verified: {zip_path} ({zip_path.stat().st_size:,} bytes)")
    return zip_path


if __name__ == "__main__":
    build_package()
