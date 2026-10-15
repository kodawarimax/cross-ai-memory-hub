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

QUICKSTART_MD = """# Universal Self-Improving AI Agent Hub (v3.1 Obsidian Native Edition) — クイックスタートガイド

Claude Code、OpenAI Codex、Google Antigravity (Gemini)、および ChatGPT の全対話履歴・音声入力と手元のドキュメント群を Obsidian Vault に一元集約し、**使うほどあなた自身の言葉（使う言葉・反応する言葉・行動する言葉・NG表現）を自己学習して進化する汎用エージェント原型モデル（Obsidian Bases `.base` ＆ 4ステージ資料蒸留統合版）**です。

---

## 1. 導入方法（30秒）

### macOS の場合
1. フォルダ内の **`Install_Mac.command`** をダブルクリックします（またはターミナルで `bash scripts/setup_obsidian.sh` を実行）。
2. 名前を聞かれたら入力して Enter を押すだけで、Obsidian Vault の自動検出・構築・データベースビュー（`.base`）・初回同期・10分毎のバックグラウンド自動同期がすべて設定されます。

### Windows / Linux / WSL の場合
- **Windows**: **`Install_Windows.bat`** をダブルクリックします。
- **Linux / WSL**: ターミナルで `bash scripts/setup_obsidian.sh` を実行します。

---

## 2. 導入直後に使える主要コマンド

```bash
# 初期セットアップ：Vault構造4問 ＋ 人格コア抽出3問の統合インタビュー（5分）
ai-memory onboard --interview

# 手元のPDF・Word・テキスト等のフォルダを4ステージ非破壊蒸留してVaultへ取り込み
ai-memory ingest ~/Documents/MyDocs --area work

# Obsidian Bases (.base) データベースビューと Home.md の生成・更新
ai-memory scaffold

# 全AIの過去チャット横断検索
chat-archive search "検索ワード"

# 自己改善型・人格コア＆SNSドラフト（X / Threads / note）の即時生成
ai-memory persona --mode sync
ai-memory persona --mode sns

# 重要な意思決定や教訓の記録（area: private 指定でAI共有から隔離可能）
ai-memory record --type playbook --area work --title "タイトル" --content "内容"
```
"""


README_GITHUB_MD = """# Universal Self-Improving AI Agent Archetype (v3.1 — Obsidian Native Edition)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-green.svg)](https://www.python.org/)
[![Zero Dependencies](https://img.shields.io/badge/Dependencies-Zero%20(Stdlib%20Only)-brightgreen.svg)]()
[![Obsidian Native](https://img.shields.io/badge/Obsidian-Bases%20%26%20Canvas%20Ready-purple.svg)]()

**Claude Code, OpenAI Codex CLI, Google Antigravity (Gemini), and ChatGPT** unified into a single **Obsidian Native Vault** with **Database Views (`.base`)**, **4-Stage Non-Destructive File Ingest**, and a **Closed-Loop Self-Improving Persona & Memory Engine**.

Every conversation, voice dictation, and local document across your workflow is automatically indexed into SQLite FTS5, structured into Obsidian Flavored Markdown, and distilled into an evolving **Persona Core (`PERSONA_CORE.md`)** and **Shared Memory (`SHARED_MEMORY.md`)**—using **zero external LLM API calls ($0 cost, 100% local & private)**.

---

## ✨ Key Architecture (Dual-Brain + Obsidian Native + Closed-Loop Evolution)

```mermaid
flowchart LR
    subgraph Silos["1. Multi-AI & File Inputs"]
        CC["Claude Code"]
        CX["OpenAI Codex CLI"]
        AG["Google Antigravity"]
        CG["ChatGPT Exports"]
        FI["Local Files (PDF/DOCX/TXT)"]
    end

    subgraph Engine["2. Deterministic Local Kernel (0 API Cost)"]
        ING["4-Stage File Ingestor (doc-to-md + Raw Backup)"]
        PII["PII / Secret Sanitizer + area:private Gate"]
        FTS["SQLite FTS5 Full-Text Index"]
        MINE["Rolling FIFO Correction & Lexicon Miner"]
        SLOP["Closed-Loop Slop Gate (Dynamic Banned Phrases)"]
    end

    subgraph Vault["3. Obsidian Native Hub"]
        BASE["Knowledge_Atlas.base & AI_Sessions.base"]
        SM["SHARED_MEMORY.md (Cross-AI Canon)"]
        PC["PERSONA_CORE.md (3-Voice Taxonomy)"]
        SNS["SNS_READY_DRAFTS.md (X / Threads / note)"]
    end

    Silos --> ING & PII --> FTS --> MINE --> SLOP --> Vault
    Vault -.->|"Auto-Injected into CLAUDE.md / AGENTS.md"| Silos
```

1. **Obsidian Native Database UI (`.base` & `.canvas`)**:
   - Automatically generates `Knowledge_Atlas.base` (Table & Card views of Playbooks, Strategies, Cases, and Resources), `AI_Sessions.base` (Scoped table view of mirrored AI chats), `Persona_&_SNS.base`, `Overview.canvas`, and `Home.md` (MOC).
2. **4-Stage Non-Destructive File Ingest (`ai-memory ingest <path>`)**:
   - Preserves original binaries/files in `Imports/<bundle>/`, extracts clean text (`doc-to-md` / stdlib `.docx`/`.pptx` / `pdftotext`), strips noise, masks PII, adds Unified Frontmatter v3.1, and compiles into `SHARED_MEMORY.md`.
3. **Cross-AI Full-Text Chat Archive (`chat-archive`)**:
   - Indexes sessions across Claude Code (`~/.claude/projects`), Codex CLI (`~/.codex`), Antigravity (`~/.gemini/antigravity/brain`), and ChatGPT ZIP exports.
4. **3-Voice Persona Taxonomy & Closed-Loop Self-Improvement (`ai-memory persona`)**:
   - Classifies authentic user utterances into **Philosophy Words (使う言葉)**, **Reaction Words (反応する言葉)**, and **Action Words (行動する言葉)**.
   - **Rolling FIFO Window & Dynamic Slop Gate**: Continuously mines your latest corrections (`「〜ではなく」「〜禁止」`) and strips banned phrases from future drafts.
5. **Deterministic Privacy Gate (`area: private` & PII Sanitizer)**:
   - Any note with `area: private` in its YAML frontmatter is automatically excluded from `SHARED_MEMORY.md`. API keys (`sk-*`, `ghp_*`, `AIza*`), emails, and phone numbers are deterministically redacted.
6. **Unified 7-Question Onboarding (`ai-memory onboard --interview`)**:
   - Combines 4 multiple-choice Vault Setup questions with 3 Persona Seed questions to build both your custom folder structure and initial `PERSONA_CORE.md` in 5 minutes.

---

## 🚀 Quick Start (30 Seconds)

### Option A: One-Command Terminal Setup (macOS / Linux / WSL)
```bash
git clone https://github.com/kodawarimax/universal-self-improving-agent.git
cd universal-self-improving-agent
bash scripts/setup_obsidian.sh "" "Your Name"
```

### Option B: Double-Click Installer
- **macOS**: Double-click **`Install_Mac.command`**
- **Windows**: Double-click **`Install_Windows.bat`**

---

## 🛠️ Everyday CLI Commands

Once installed, `~/.local/bin` provides two global commands (`ai-memory` and `chat-archive`):

```bash
# 1. Unified 7-question Vault Setup + Persona Seed interview
ai-memory onboard --interview

# 2. Ingest local PDFs, Word/PowerPoint docs, or folders into Obsidian (4-stage pipeline)
ai-memory ingest ~/Documents/ProjectDocs --area work

# 3. Generate or repair Obsidian .base views, Overview.canvas, and Home.md
ai-memory scaffold

# 4. Search across all past Claude / Codex / Antigravity / ChatGPT sessions
chat-archive search "architecture"
chat-archive list --limit 20

# 5. Run self-improving persona extraction & generate SNS drafts (X / Threads / note)
ai-memory persona --mode sync
ai-memory persona --mode sns

# 6. Record a permanent lesson, playbook, or project update (Unified Schema v3.1)
ai-memory record --type playbook --area work --title "Atomic Writes" --content "Always use tempfile + os.replace."

# 7. Check daily semantic contradictions across rules & memories
ai-memory contradictions --scan
```

---

## 📄 License

MIT License — Free to use, modify, and distribute for personal or commercial AI agent workflows.
"""

MIT_LICENSE = """MIT License

Copyright (c) 2026 Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

GITIGNORE_TXT = """__pycache__/
*.py[cod]
*$py.class
.DS_Store
*.db
*.sqlite
*.jsonl
*.zst
.env
"""


def verify_no_leaks(staging_dir: Path):
    """Deterministic security check ensuring no personal DBs, logs, PII, or secrets are bundled."""
    forbidden_exts = {".db", ".sqlite", ".jsonl", ".zst", ".env", ".pem", ".key"}
    secret_re = re.compile(r"\b(?:sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_-]{30,})\b")
    private_terms_re = re.compile(r"(賃REVO|岡さん|アガスティア|徳永|180万|jungo|坂本|最遊記|灯巡)", re.IGNORECASE)

    for p in staging_dir.rglob("*"):
        if p.is_dir() or ".git" in p.parts:
            continue
        if p.suffix.lower() in forbidden_exts:
            raise RuntimeError(f"Security gate blocked forbidden file in distribution: {p}")
        if p.suffix.lower() in {".py", ".sh", ".md", ".command", ".bat"}:
            txt = p.read_text(encoding="utf-8", errors="ignore")
            if secret_re.search(txt):
                raise RuntimeError(f"Security gate blocked potential secret in: {p}")
            m = private_terms_re.search(txt)
            if m:
                raise RuntimeError(f"Security gate blocked private identifier '{m.group(0)}' in: {p}")


def build_package() -> Path:
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = DIST_DIR / "universal-self-improving-agent-v3.1.zip"
    repo_stage_dir = DIST_DIR / "universal-self-improving-agent"

    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / "universal-self-improving-agent"
        scripts_dst = stage / "scripts"
        refs_dst = stage / "references"
        engine_Archive_dst = scripts_dst / "engine" / "ai-chat-archive"
        engine_mem_dst = scripts_dst / "engine" / "ai-shared-memory"
        (engine_Archive_dst / "bin").mkdir(parents=True, exist_ok=True)
        engine_mem_dst.mkdir(parents=True, exist_ok=True)
        refs_dst.mkdir(parents=True, exist_ok=True)

        # Copy SKILL.md, references/, README.md, LICENSE, .gitignore & top-level installers
        shutil.copy2(SKILL_ROOT / "SKILL.md", stage / "SKILL.md")
        if (SKILL_ROOT / "references" / "OBSIDIAN_NATIVE_GUIDE.md").exists():
            shutil.copy2(SKILL_ROOT / "references" / "OBSIDIAN_NATIVE_GUIDE.md", refs_dst / "OBSIDIAN_NATIVE_GUIDE.md")
        (stage / "README.md").write_text(README_GITHUB_MD, encoding="utf-8")
        (stage / "README_QUICKSTART.md").write_text(QUICKSTART_MD, encoding="utf-8")
        (stage / "LICENSE").write_text(MIT_LICENSE, encoding="utf-8")
        (stage / ".gitignore").write_text(GITIGNORE_TXT, encoding="utf-8")

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
        for f_name in ["compiler.py", "persona_extractor.py", "onboarding_coach.py", "contradiction_resolver.py", "ingestor.py", "recorder.py", "cli.py"]:
            if (src_mem / f_name).exists():
                shutil.copy2(src_mem / f_name, engine_mem_dst / f_name)

        # Run deterministic leak check
        verify_no_leaks(stage)

        # Sync to persistent git staging folder while preserving .git
        repo_stage_dir.mkdir(parents=True, exist_ok=True)
        for item in repo_stage_dir.iterdir():
            if item.name == ".git":
                continue
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
        for item in stage.iterdir():
            dst_item = repo_stage_dir / item.name
            if item.is_dir():
                shutil.copytree(item, dst_item)
            else:
                shutil.copy2(item, dst_item)

        # Create ZIP archive
        if zip_path.exists():
            zip_path.unlink()
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_p in sorted(stage.rglob("*")):
                if file_p.is_file():
                    arcname = file_p.relative_to(Path(tmp))
                    zf.write(file_p, arcname)

    print(f"✅ Clean distribution package built & verified: {zip_path} ({zip_path.stat().st_size:,} bytes)")
    print(f"✅ Clean Git repository updated at: {repo_stage_dir}")
    return zip_path


if __name__ == "__main__":
    build_package()
