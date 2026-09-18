#!/usr/bin/env python3
"""
compiler.py - Compiles Obsidian Vault (knowledge-empire) and recent lessons into
a compact, authoritative SHARED_MEMORY.md accessible by Codex, Claude Code, and Antigravity.
"""

import os
import re
import glob
from datetime import datetime
from pathlib import Path

VAULT_DIR = Path("/Users/jungosakamoto/Claude/knowledge-empire")
MEMORY_DIR = VAULT_DIR / "memory"
SHARED_MEMORY_FILE = MEMORY_DIR / "SHARED_MEMORY.md"

CLAUDE_MEMORY_DIR = Path(os.path.expanduser("~/.claude/memory"))

def clean_body_text(text: str) -> str:
    # Remove YAML frontmatter if present
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            text = parts[2]
    # Remove markdown headers and clean extra spaces
    lines = [l.strip() for l in text.splitlines() if l.strip() and not l.strip().startswith("#")]
    return " ".join(lines)

def extract_recent_lessons(limit=8):
    lessons = []
    
    # 1. Search recent cases in knowledge-empire/wiki/cases/
    cases_dir = VAULT_DIR / "wiki" / "cases"
    if cases_dir.exists():
        files = sorted(
            cases_dir.glob("*.md"),
            key=lambda x: x.stat().st_mtime,
            reverse=True
        )[:limit]
        for p in files:
            if p.name == "index.md":
                continue
            try:
                content = p.read_text(encoding="utf-8", errors="ignore")
                title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
                title = title_match.group(1).strip() if title_match else p.stem
                body = clean_body_text(content)
                if title and body:
                    lessons.append({"title": title, "summary": body[:180], "source": f"wiki/cases/{p.name}"})
            except Exception:
                pass

    # 2. Search recent feedback_*.md in ~/.claude/memory
    if CLAUDE_MEMORY_DIR.exists() and len(lessons) < limit:
        files = sorted(
            glob.glob(str(CLAUDE_MEMORY_DIR / "feedback_*.md")),
            key=lambda x: os.path.getmtime(x),
            reverse=True
        )[:limit - len(lessons)]
        for f in files:
            p = Path(f)
            try:
                content = p.read_text(encoding="utf-8", errors="ignore")
                title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
                title = title_match.group(1).strip() if title_match else p.stem.replace("feedback_", "")
                body = clean_body_text(content)
                if title and body:
                    lessons.append({"title": title, "summary": body[:180], "source": p.name})
            except Exception:
                pass

    return lessons[:limit]

def compile_shared_memory():
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    lessons = extract_recent_lessons(limit=6)

    content = f"""# AI Shared Memory — 3大AI共通記憶正本 (Single Source of Truth)

> **更新日時**: {now_str}
> **正本保管場所**: `/Users/jungosakamoto/Claude/knowledge-empire/memory/SHARED_MEMORY.md`
> **対象AI**: OpenAI Codex CLI / Anthropic Claude Code / Google Antigravity (Gemini)
> **目的**: Obsidian Vault を共通ハブとし、全AIが同一の前提・組織方針・案件状況・教訓を共有して協調動作する。

---

## 1. 創業者・組織方針・ドクトリン（Canon & Identity）

- **創業者・CEO**: [[坂本淳悟_正典]]（こだわりMAXグローバル代表）
  - 価値観: 最小差分・証拠主義・自動化推進・現場負荷の徹底軽減・自立型システム構築。
- **最上位ドクトリン**: [[真の王]]（灯巡組織最上位ドクトリン / 全AIクローン約56体の共通目的）
- **主要役職エージェント**:
  - [[桜田_正典]]: AI桜田・経理総務部長（経理/税務/財務/法務/労務）
  - [[hiroki_daichi_正典]]: 広木大地・ITシステム開発部長（アーキテクチャ/保守性/DevOps）
  - [[北原孝彦_COO]]: 北原COO・最高執行責任者（事業展開/マーケティング/実行推進）
  - 部門正典: [[IT部_正典]] | [[デザイン部_正典]] | [[営業部_正典]] | [[教育商品開発部_正典]] | [[AIクローン_正典]]

---

## 2. 現在進行中の主要プロジェクト状況（Active Projects）

| プロジェクト | 重点課題・最新の決定事項 | 関連パス・正典 |
|---|---|---|
| **アガスティア様DX** | 9月の顧客急増前に決済（GMO+振込リンク）先行構築。1申込=1請求の原則。予約システムは1月開発。 | `sales/agastia-it-consulting/`, `[[アガスティア]]` |
| **AIクローン** | FastAPI + WebSocket 構成。リアルタイム音声秘書「灯子」「ゆかちゃん」。個人記憶保全と低遅延応答。 | `Service/Clone/`, `[[AIクローン_正典]]` |
| **賃REVO (岡さん)** | NotebookLM・契約条件に基づく提案検証。1社実証と明確な判断ゲート重視。 | `Desktop/岡さん/`, `[[賃REVO]]` |
| **U-AI協会 価格表** | Google Sheets API 経由でのマスター直接読み書きスクリプト本番化。9列ステージ表同期。 | `dev/uai-price-sheet/` |
| **AI統合運用基盤** | Codex / Claude / Antigravity のチャット全履歴FTS5検索、Obsidian共通記憶ハブの常時運用。 | `dev/ai-chat-archive/`, `dev/ai-shared-memory/` |

---

## 3. 全AI共通規律（Global Constitution & Rules）

1. **強制停止・人間承認（force_l0）**:
   - 金銭決済、法務・契約締結、本番デプロイ、外部メール/LINE送信、個人情報(PII)変更は**必ず人間（坂本さん）の承認を得てから実行**する。
2. **証拠主義（Evidence-Based）**:
   - 「動くはず」での完了宣言禁止。必ずテスト実行ログ、ビルドログ、HTTPステータス等の検証証拠を確認する。
   - 自動修復の試行は最大3回まで。3回失敗したら直ちに停止して原因と代替案を提示する。
3. **機密・PII防衛**:
   - APIキー、トークン、秘密鍵、顧客の実名・本文をログやチャット、Obsidianの一般公開領域に書き込まない。
4. **コーディング & ファイル配置**:
   - 既存コード・ヘルパー・命名規約を最優先で尊重し、最小の差分で修正する。
   - 作業は `dev/` `sales/` `content/` `ventures/` `Service/` 配下で行い、ルート直下にファイルを増やさない。
   - コミットプレフィックス: `feat:`, `fix:`, `docs:`, `refactor:`。

---

## 4. 直近の重要教訓・ハマりどころ（Lessons & Best Practices）

"""
    for l in lessons:
        content += f"- **{l['title']}** (`{l['source']}`)\n  {l['summary']}\n"

    content += """
---

## 5. 知識の書き戻しプロトコル（Recording Back to Obsidian）

各AIが作業中に「永続化すべき決定」「新たな教訓」「案件のステータス変更」を生み出した場合、以下のコマンドでObsidianに記録する：

```bash
# 決定事項や教訓の記録
ai-memory record --type lesson --title "タイトル" --content "教訓・決定内容"
ai-memory record --type project --title "案件名" --content "進捗・更新情報"

# 共通記憶の再コンパイル・同期
ai-memory sync
```
"""

    SHARED_MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    SHARED_MEMORY_FILE.write_text(content, encoding="utf-8")
    return SHARED_MEMORY_FILE

if __name__ == "__main__":
    path = compile_shared_memory()
    print(f"Compiled SHARED_MEMORY to: {path}")
