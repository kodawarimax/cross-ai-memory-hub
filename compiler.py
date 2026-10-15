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

HOME_DIR = Path.home()
_default_vault = HOME_DIR / "Claude" / "knowledge-empire" if (HOME_DIR / "Claude").exists() else HOME_DIR / "knowledge-empire"
VAULT_DIR = Path(os.environ.get("OBSIDIAN_VAULT", str(_default_vault))).expanduser()
MEMORY_DIR = VAULT_DIR / "memory"
SHARED_MEMORY_FILE = MEMORY_DIR / "SHARED_MEMORY.md"

CLAUDE_MEMORY_DIR = HOME_DIR / ".claude" / "memory"
_proj_slug = "-" + str(HOME_DIR / "Claude").strip("/").replace("/", "-")
CLAUDE_PROJ_MEMORY_DIR = HOME_DIR / ".claude" / "projects" / _proj_slug / "memory"
CODEX_MEMORY_DIR = HOME_DIR / ".codex" / "memories"
_default_archive_db = (HOME_DIR / "Claude" / "dev" / "ai-chat-archive" / "archive.db") if (HOME_DIR / "Claude" / "dev" / "ai-chat-archive").exists() else (VAULT_DIR / ".ai-hub" / "archive.db")
ARCHIVE_DB = Path(os.environ.get("AI_ARCHIVE_DB", str(_default_archive_db))).expanduser()

def clean_body_text(text: str) -> str:
    # Remove YAML frontmatter if present
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            text = parts[2]
    # Remove markdown headers and clean extra spaces
    lines = [l.strip() for l in text.splitlines() if l.strip() and not l.strip().startswith("#")]
    return " ".join(lines)

def extract_recent_notes(directory: Path, pattern: str = "*.md", limit: int = 5, source_prefix: str = "") -> list:
    items = []
    if not directory.exists():
        return items
    files = sorted(
        directory.glob(pattern),
        key=lambda x: x.stat().st_mtime,
        reverse=True
    )
    for p in files:
        if p.name in ("index.md", "MEMORY.md", "MEMORY_ARCHIVE.md"):
            continue
        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
            title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
            title = title_match.group(1).strip() if title_match else p.stem
            body = clean_body_text(content)
            if title and body:
                mtime_str = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d")
                src = f"{source_prefix}{p.name}" if source_prefix else p.name
                items.append({
                    "title": title[:90],
                    "summary": body[:200],
                    "source": src,
                    "date": mtime_str
                })
                if len(items) >= limit:
                    break
        except Exception:
            pass
    return items

def extract_archive_stats_and_recent() -> dict:
    import sqlite3
    info = {"stats": {}, "mirrored": 0, "recent": []}
    if not ARCHIVE_DB.exists():
        return info
    try:
        conn = sqlite3.connect(f"file:{ARCHIVE_DB}?mode=ro", uri=True)
        info["stats"] = dict(conn.execute("SELECT provider, COUNT(*) FROM sessions GROUP BY provider").fetchall())
        try:
            info["mirrored"] = conn.execute("SELECT COUNT(*) FROM obsidian_exports").fetchone()[0]
        except Exception:
            info["mirrored"] = 0
        for prov in ("codex", "claude", "antigravity"):
            rows = conn.execute("""
                SELECT session_id, provider, title, updated_at
                FROM sessions
                WHERE provider = ? AND message_count > 0
                ORDER BY updated_at DESC
                LIMIT 3
            """, (prov,)).fetchall()
            info["recent"].extend(rows)
        conn.close()
    except Exception:
        pass
    return info

def compile_shared_memory():
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    vault_lessons = extract_recent_notes(VAULT_DIR / "wiki" / "cases", "*.md", limit=5, source_prefix="wiki/cases/")
    claude_feedback = extract_recent_notes(CLAUDE_MEMORY_DIR, "feedback_*.md", limit=4, source_prefix="~/.claude/memory/")
    claude_autosaves = extract_recent_notes(CLAUDE_PROJ_MEMORY_DIR, "session_*_autosave_*.md", limit=5, source_prefix="linked/claude-project-memories/")
    codex_rollouts = extract_recent_notes(CODEX_MEMORY_DIR / "rollout_summaries", "*.md", limit=5, source_prefix="linked/codex-memories/rollout_summaries/")
    crm_updates = extract_recent_notes(VAULT_DIR / "crm", "*.md", limit=5, source_prefix="crm/")
    arch_info = extract_archive_stats_and_recent()

    c_cnt = arch_info["stats"].get("claude", 0)
    x_cnt = arch_info["stats"].get("codex", 0)
    a_cnt = arch_info["stats"].get("antigravity", 0)
    tot_cnt = c_cnt + x_cnt + a_cnt

    local_canon_file = MEMORY_DIR / "LOCAL_CANON.md"
    local_cfg_file = MEMORY_DIR / "LOCAL_PERSONA_CONFIG.json"
    default_owner = HOME_DIR.name
    if local_cfg_file.exists():
        try:
            import json
            default_owner = json.loads(local_cfg_file.read_text(encoding="utf-8")).get("owner_name", default_owner)
        except Exception:
            pass
    persona_name = os.environ.get("PERSONA_NAME", default_owner)

    content = f"""# AI Shared Memory — 4大AI共通記憶正本 (Single Source of Truth)

> **更新日時**: {now_str}
> **正本保管場所**: `{SHARED_MEMORY_FILE}`
> **対象AI**: OpenAI Codex CLI / Anthropic Claude Code / Google Antigravity (Gemini) / ChatGPT Projects
> **全会話アーカイブ統合状況**: 総計 **{tot_cnt:,} セッション** (Claude: {c_cnt:,} / Codex: {x_cnt:,} / Antigravity: {a_cnt:,} / Vault内ミラー: {arch_info['mirrored']:,} notes) -> [[CHAT_ARCHIVE]]

---
"""
    if local_canon_file.exists():
        content += local_canon_file.read_text(encoding="utf-8", errors="ignore").strip() + "\n\n"
    else:
        strategies = extract_recent_notes(VAULT_DIR / "wiki" / "strategies", "*.md", limit=5, source_prefix="wiki/strategies/")
        content += f"""## 1. オーナー・人格コピー・言語エンジン正本（Canon & Persona Identity）

- **オーナー**: `{persona_name}`
  - **完全人格コピー＆SNS言語エンジン正本**: [[PERSONA_CORE]]（使う言葉・反応する言葉・行動する言葉・自己改善ループ）
  - **生音声・実チャット語録ログ**: [[VOICE_LOG]]（全AI対話・音声入力から自動抽出した思想・反応・行動フレーズ）
  - **SNS即投稿ドラフト集**: [[SNS_READY_DRAFTS]]（X / Threads / note 直結ドラフト・Slop Gate検証済）

---

## 2. 直近の戦略・プロジェクトノート（Active Strategies & Projects）

"""
        if strategies:
            for st in strategies:
                content += f"- **[{st['date']}] {st['title']}** (`{st['source']}`): {st['summary']}\n"
            content += "\n"
        else:
            content += "- `ai-memory record --type strategy --title \"...\" --content \"...\"` で記録された戦略ノートがここに自動反映されます。\n\n"
    if crm_updates:
        content += "### 直近の案件・CRM更新ノート (`crm/`)\n"
        for item in crm_updates:
            content += f"- **[{item['date']}] {item['title']}** (`{item['source']}`): {item['summary']}\n"
        content += "\n"

    content += f"""---

## 3. 全AI共通規律（Global Constitution & Rules）

1. **強制停止・人間承認（force_l0）**:
   - 金銭決済、法務・契約締結、本番デプロイ、外部メール/LINE送信、個人情報(PII)変更は**必ず人間（{persona_name}）の承認を得てから実行**する。
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

## 4. 直近の重要教訓・各AIの自動蒸留メモリ（Cross-AI Distilled Memories）

### Obsidian 正典・ケーススタディ (`wiki/cases/` & `feedback_*`)
"""
    for l in (vault_lessons + claude_feedback)[:7]:
        content += f"- **[{l['date']}] {l['title']}** (`{l['source']}`)\n  {l['summary']}\n"

    if not claude_autosaves and (HOME_DIR / ".claude" / "projects").exists():
        for ws_mem in sorted((HOME_DIR / ".claude" / "projects").glob("*/memory"), key=lambda p: p.stat().st_mtime, reverse=True)[:3]:
            claude_autosaves.extend(extract_recent_notes(ws_mem, "*.md", limit=2, source_prefix=f"linked/claude-workspaces/{ws_mem.parent.name}/"))
        claude_autosaves = claude_autosaves[:5]

    if claude_autosaves:
        content += "\n### Claude Code 直近の自動蒸留セッション記憶 (`linked/claude-workspaces/`)\n"
        for s in claude_autosaves:
            content += f"- **[{s['date']}] {s['title']}** (`{s['source']}`)\n  {s['summary']}\n"

    if codex_rollouts:
        content += "\n### Codex CLI 直近の自動蒸留ロールアウト記憶 (`linked/codex-memories/rollout_summaries/`)\n"
        for r in codex_rollouts:
            content += f"- **[{r['date']}] {r['title']}** (`{r['source']}`)\n  {r['summary']}\n"

    if arch_info["recent"]:
        content += "\n### 3大AI 直近のアクティブ会話セッション (`raw/sessions/` & `chat-archive`)\n"
        for sid, prov, title, u_at in arch_info["recent"]:
            t_clean = (title or sid[:8]).replace("\n", " ")[:75]
            u_short = (u_at or "")[:16].replace("T", " ")
            content += f"- **[{prov.upper()} | {u_short}]** `{sid}` — {t_clean}\n"

    content += f"""
---

## 5. 全コンテキスト横断検索 & 知識の書き戻しプロトコル

過去の全ノート・記憶・全チャット履歴を横断検索・記録するコマンド：

```bash
# 全メモリ・Obsidian Vault・全チャット履歴を一括横断検索
ai-memory search "検索キーワード"
ai-memory get "トピック名"

# {persona_name} 人格コピー（使う言葉・反応する言葉・行動する言葉）＆SNS即投稿ドラフト抽出
ai-memory persona --mode core
ai-memory persona --mode sns

# 決定事項や教訓のObsidianへの記録
ai-memory record --type lesson --title "タイトル" --content "教訓・決定内容"
ai-memory record --type project --title "案件名" --content "進捗・更新情報"

# 共通記憶＋全チャット履歴＋人格SNSドラフトのObsidian同期
chat-archive sync && ai-memory sync

# 内蔵エージェントによる環境制約診断＆5分間・初期人格コア抽出インタビュー
ai-memory onboard --diagnose
ai-memory onboard --interview
ai-memory onboard --open-chatgpt

# 意味上の矛盾（Semantic Contradictions）の日次スキャン＆ユーザー判断による解決
ai-memory contradictions --scan
ai-memory contradictions --ask
ai-memory contradictions --resolve <ID> --choice <A|B|BOTH|DISMISS> --note "使い分け条件"
```
"""

    try:
        from persona_extractor import sync_persona_engine
        sync_persona_engine(verbose=False)
    except Exception:
        pass

    try:
        from onboarding_coach import format_directives_for_shared_memory
        content += "\n" + format_directives_for_shared_memory(vault_dir=VAULT_DIR, archive_db=ARCHIVE_DB)
    except Exception:
        pass

    try:
        from contradiction_resolver import scan_and_update_contradictions, format_contradictions_for_shared_memory
        scan_and_update_contradictions(vault_dir=VAULT_DIR, notify_macos=False)
        content += "\n" + format_contradictions_for_shared_memory(vault_dir=VAULT_DIR)
    except Exception:
        pass

    import tempfile
    SHARED_MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_p = tempfile.mkstemp(dir=str(SHARED_MEMORY_FILE.parent), prefix=".SHARED_MEMORY.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_p, SHARED_MEMORY_FILE)
    except Exception:
        if os.path.exists(tmp_p):
            os.unlink(tmp_p)
        raise
    return SHARED_MEMORY_FILE

if __name__ == "__main__":
    path = compile_shared_memory()
    print(f"Compiled SHARED_MEMORY to: {path}")
