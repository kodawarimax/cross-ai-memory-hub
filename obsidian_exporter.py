#!/usr/bin/env python3
"""
obsidian_exporter.py - Incrementally mirrors all AI sessions (Codex, Claude Code, Antigravity)
into the Obsidian Vault (knowledge-empire/raw/sessions/<provider>/<YYYY-MM>/) as structured
Markdown notes with YAML frontmatter, wikilinks, and updates memory/CHAT_ARCHIVE.md.

Inspired by:
- chaenmasahiro0425/exbrain (4-Layer Architecture: raw -> wiki -> digest -> identity)
- mattbirchler/claude-code-obsidian & NickLennonLiu/obsidian-codex-session-archive
- mcncarl/agent-memory-vault (Unified SQLite FTS5 + Markdown Vault)
"""

import os
import re
import sqlite3
import time
import unicodedata
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("CHAT_ARCHIVE_DB", str(BASE_DIR / "archive.db")))

def _resolve_vault_dir() -> Path:
    if os.environ.get("OBSIDIAN_VAULT"):
        return Path(os.path.expanduser(os.environ["OBSIDIAN_VAULT"]))
    home = Path.home()
    if (home / "Claude" / "knowledge-empire").exists():
        return home / "Claude" / "knowledge-empire"
    return home / "knowledge-empire"

VAULT_DIR = _resolve_vault_dir()
SESSIONS_ROOT = VAULT_DIR / "raw" / "sessions"
LINKED_DIR = VAULT_DIR / "linked"
CHAT_ARCHIVE_MD = VAULT_DIR / "memory" / "CHAT_ARCHIVE.md"


def slugify(text: str, max_len: int = 36) -> str:
    if not text:
        return "session"
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"[^\w\s-]", "", text.lower())
    text = re.sub(r"[\s_-]+", "-", text).strip("-")
    return text[:max_len] if text else "session"


def ensure_memory_symlinks():
    """
    Ensure all siloed AI memory directories and subfolder workspaces across $HOME
    are automatically linked or merged into knowledge-empire/linked/ and wiki/.
    """
    import shutil
    import subprocess
    home = Path.home()
    LINKED_DIR.mkdir(parents=True, exist_ok=True)
    esc_home = "-" + str(home).lstrip("/\\").replace("/", "-").replace("\\", "-").replace(":", "")

    def safe_link_or_junction(link_p: Path, target_p: Path):
        if not target_p.exists() or link_p.exists() or link_p.is_symlink():
            return
        try:
            link_p.symlink_to(target_p, target_is_directory=target_p.is_dir())
        except Exception:
            if os.name == "nt" and target_p.is_dir():
                try:
                    subprocess.run(["cmd", "/c", "mklink", "/J", str(link_p), str(target_p)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return
                except Exception:
                    pass
            try:
                if target_p.is_dir():
                    shutil.copytree(target_p, link_p, dirs_exist_ok=True)
            except Exception:
                pass

    # 1. Core AI memory symlinks
    targets = {
        "codex-memories": home / ".codex" / "memories",
        "claude-project-memories": home / ".claude" / "projects" / f"{esc_home}-Claude" / "memory",
        "claude-root-memories": home / ".claude" / "projects" / esc_home / "memory",
        "claude-global-memories": home / ".claude" / "memory",
        "claude-session-data": home / ".claude" / "session-data",
    }
    for link_name, target_path in targets.items():
        safe_link_or_junction(LINKED_DIR / link_name, target_path)

    # 2. Dynamically discover and symlink ALL ~/.claude/projects/<workspace>/memory directories (present & future)
    ws_links_dir = LINKED_DIR / "claude-workspaces"
    ws_links_dir.mkdir(parents=True, exist_ok=True)
    claude_projects = home / ".claude" / "projects"
    if claude_projects.exists():
        for ws_dir in claude_projects.iterdir():
            if not ws_dir.is_dir():
                continue
            mem_sub = ws_dir / "memory"
            if mem_sub.exists() and any(mem_sub.glob("*.md")):
                safe_link_or_junction(ws_links_dir / ws_dir.name, mem_sub)

    # 3. Dynamically symlink subfolder AI workspaces in user's home directory
    subfolders_dir = LINKED_DIR / "subfolders"
    subfolders_dir.mkdir(parents=True, exist_ok=True)
    subfolder_targets = {
        "documents-codex-tasks": home / "Documents" / "Codex",
        "codex-standalone-til": home / "Codex" / "it-system-dev" / "references" / "til",
        "claude-dots-hasshin": home / "Claude" / "dots" / "hasshin",
        "claude-dots-ittou": home / "Claude" / "dots" / "ittou",
        "claude-artifacts": home / "Claude" / "artifacts",
    }
    for s_name, s_target in subfolder_targets.items():
        safe_link_or_junction(subfolders_dir / s_name, s_target)

    # 4. Merge any split-brain notes from ~/Codex/knowledge-empire/wiki/ into main Vault wiki/
    split_wiki = home / "Codex" / "knowledge-empire" / "wiki"
    if split_wiki.exists():
        for src_md in split_wiki.rglob("*.md"):
            rel = src_md.relative_to(split_wiki)
            dest_md = VAULT_DIR / "wiki" / rel
            if not dest_md.exists():
                dest_md.parent.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.copy2(src_md, dest_md)
                except Exception:
                    pass

    # 5. Auto-sync any new files in ~/.codex/.chatgpt-projects/<id>/sources/
    cgp_root = home / ".codex" / ".chatgpt-projects"
    dest_cgp = VAULT_DIR / "wiki" / "chatgpt-project-jungo-clone"
    if cgp_root.exists():
        dest_cgp.mkdir(parents=True, exist_ok=True)
        for src_f in cgp_root.rglob("*.md"):
            if src_f.name == "03_cia_profile_jungo.md" and (dest_cgp / "03_cia_profile_jungo_FULL.md").exists():
                continue
            target_f = dest_cgp / src_f.name
            if not target_f.exists() or src_f.stat().st_mtime > target_f.stat().st_mtime:
                try:
                    shutil.copy2(src_f, target_f)
                except Exception:
                    pass


def init_export_table(conn: sqlite3.Connection):
    conn.execute("""
    CREATE TABLE IF NOT EXISTS obsidian_exports (
        session_id TEXT PRIMARY KEY,
        md_rel_path TEXT NOT NULL,
        exported_mtime REAL NOT NULL
    );
    """)
    conn.commit()


def export_sessions_to_obsidian(verbose: bool = True, force_all: bool = False) -> dict:
    start_t = time.time()
    ensure_memory_symlinks()
    SESSIONS_ROOT.mkdir(parents=True, exist_ok=True)

    if not DB_PATH.exists():
        return {"exported": 0, "total_mirrored": 0}

    conn = sqlite3.connect(DB_PATH)
    init_export_table(conn)
    cursor = conn.cursor()

    cursor.execute("SELECT session_id, md_rel_path, exported_mtime FROM obsidian_exports")
    exported_map = {r[0]: (r[1], r[2]) for r in cursor.fetchall()}

    cursor.execute("""
        SELECT session_id, provider, title, project_path, file_path, created_at, updated_at, message_count, mtime
        FROM sessions
        WHERE message_count > 0
        ORDER BY updated_at DESC
    """)
    all_sessions = cursor.fetchall()

    to_export = []
    for row in all_sessions:
        sid, prov, title, proj, fpath, c_at, u_at, m_cnt, mt = row
        mt_val = float(mt or 0)
        if not force_all and sid in exported_map:
            rel_p, prev_mt = exported_map[sid]
            full_p = VAULT_DIR / rel_p
            if prev_mt >= mt_val and full_p.exists():
                continue
        to_export.append(row)

    if verbose:
        print(f"Obsidian Exporter: {len(to_export)} session(s) to mirror (out of {len(all_sessions)} non-empty sessions)...")

    exported_count = 0
    export_records = []

    if to_export:
        # Fetch messages in chunks of 500 sessions from messages_fts for blazing-fast export
        chunk_size = 500
        for i in range(0, len(to_export), chunk_size):
            chunk = to_export[i:i + chunk_size]
            sids = [r[0] for r in chunk]
            placeholders = ",".join("?" for _ in sids)
            msg_rows = cursor.execute(
                f"SELECT session_id, role, content, timestamp FROM messages_fts WHERE session_id IN ({placeholders}) ORDER BY rowid ASC",
                sids
            ).fetchall()

            msgs_by_sid = {}
            for m_sid, role, content, ts in msg_rows:
                msgs_by_sid.setdefault(m_sid, []).append((role, content, ts))

            for row in chunk:
                sid, prov, title, proj, fpath, c_at, u_at, m_cnt, mt = row
                date_str = (c_at or u_at or "2026-01-01")[:10]
                if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
                    date_str = "2026-01-01"
                ym_str = date_str[:7]

                safe_slug = slugify(title, 32)
                sid_short = re.sub(r"[^\w-]", "", sid)[:8]
                filename = f"{date_str}_{safe_slug}_{sid_short}.md"

                target_dir = SESSIONS_ROOT / prov / ym_str
                target_dir.mkdir(parents=True, exist_ok=True)
                target_file = target_dir / filename
                rel_path = str(target_file.relative_to(VAULT_DIR))

                clean_title = (title or f"{prov} session {sid_short}").replace('"', "'").replace("\n", " ")
                clean_proj = (proj or "Unknown").replace('"', "'")

                lines = [
                    "---",
                    f'title: "{clean_title}"',
                    f'session_id: "{sid}"',
                    f"provider: {prov}",
                    f'project: "{clean_proj}"',
                    f"date: {date_str}",
                    f'updated: "{u_at or c_at}"',
                    f"message_count: {m_cnt}",
                    f"tags: [ai-session, {prov}]",
                    "---",
                    "",
                    f"# {clean_title}",
                    "",
                    f"> **AI**: `{prov.upper()}` | **Session ID**: `{sid}` | **Date**: `{(u_at or c_at or '')[:19].replace('T', ' ')}`",
                    f"> **Project**: `{clean_proj}` | **Hub**: [[CHAT_ARCHIVE]] / [[SHARED_MEMORY]]",
                    "",
                    "---",
                    "",
                ]

                session_msgs = msgs_by_sid.get(sid, [])
                for role, content, ts in session_msgs:
                    time_badge = f" `[{ts[11:19]}]`" if ts and len(ts) >= 19 else ""
                    if role == "user":
                        lines.append(f"### 👤 User{time_badge}\n\n{content}\n")
                    else:
                        lines.append(f"### 🤖 Assistant ({prov.upper()}){time_badge}\n\n{content}\n")
                    lines.append("")

                try:
                    target_file.write_text("\n".join(lines), encoding="utf-8")
                    export_records.append((sid, rel_path, float(mt or time.time())))
                    exported_count += 1
                except Exception:
                    pass

            if export_records:
                conn.executemany(
                    "INSERT OR REPLACE INTO obsidian_exports (session_id, md_rel_path, exported_mtime) VALUES (?, ?, ?)",
                    export_records
                )
                conn.commit()
                export_records.clear()

    # Update memory/CHAT_ARCHIVE.md dashboard with live stats and links
    update_chat_archive_hub(conn)
    total_mirrored = conn.execute("SELECT COUNT(*) FROM obsidian_exports").fetchone()[0]
    conn.close()

    elapsed = time.time() - start_t
    if verbose:
        print(f"Obsidian Exporter complete: {exported_count} updated, {total_mirrored} total Markdown notes in Vault ({elapsed:.2f}s).")

    return {"exported": exported_count, "total_mirrored": total_mirrored}


def update_chat_archive_hub(conn: sqlite3.Connection):
    cursor = conn.cursor()
    stats = dict(cursor.execute("SELECT provider, COUNT(*) FROM sessions GROUP BY provider").fetchall())
    non_empty = dict(cursor.execute("SELECT provider, COUNT(*) FROM sessions WHERE message_count > 0 GROUP BY provider").fetchall())
    total_msgs = cursor.execute("SELECT SUM(message_count) FROM sessions").fetchone()[0] or 0
    total_sessions = sum(stats.values())
    total_mirrored = cursor.execute("SELECT COUNT(*) FROM obsidian_exports").fetchone()[0]

    recent_rows = cursor.execute("""
        SELECT s.session_id, s.provider, s.title, s.updated_at, s.message_count, e.md_rel_path
        FROM sessions s
        LEFT JOIN obsidian_exports e ON s.session_id = e.session_id
        WHERE s.message_count > 0
        ORDER BY s.updated_at DESC
        LIMIT 35
    """).fetchall()

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    md = f"""---
title: "AI Chat Archive — 3大AI全チャット履歴ハブ"
date: {datetime.now().strftime("%Y-%m-%d")}
updated: "{now_str}"
type: hub
tags: [chat-archive, codex, claude, antigravity, memory, exbrain]
author: AI統合運用基盤
---

# AI Chat Archive — Codex・Claude Code・Antigravity 全チャット履歴ハブ

> **最終自動同期**: `{now_str}`
> **関連正典**: [[坂本淳悟_正典]] | [[IT部_正典]] | [[SHARED_MEMORY]]
> **格納レイヤー**: `knowledge-empire/raw/sessions/{{codex,claude,antigravity}}/YYYY-MM/` + `dev/ai-chat-archive/archive.db` (FTS5)

---

## 1. リアルタイム統合統計（全AI横断）

| AI プロバイダ | 総セッション数 | 実質会話セッション数 | Vault内Markdownミラー先 |
| :--- | ---: | ---: | :--- |
| **Anthropic Claude Code** | {stats.get('claude', 0):,} | {non_empty.get('claude', 0):,} | `raw/sessions/claude/` + `linked/claude-project-memories/` |
| **OpenAI Codex CLI** | {stats.get('codex', 0):,} | {non_empty.get('codex', 0):,} | `raw/sessions/codex/` + `linked/codex-memories/` |
| **Google Antigravity (Gemini)** | {stats.get('antigravity', 0):,} | {non_empty.get('antigravity', 0):,} | `raw/sessions/antigravity/` |
| **合計 (Total)** | **{total_sessions:,}** | **{total_mirrored:,} Notes** | **総メッセージ数: {total_msgs:,} 件** |

---

## 2. 直近のAIセッション一覧（Obsidian 直接リンク）

| 更新日時 | AI | Msg数 | セッションノート (Obsidian Link) |
| :--- | :--- | ---: | :--- |
"""
    for sid, prov, title, u_at, m_cnt, rel_p in recent_rows:
        up_short = (u_at or "")[:16].replace("T", " ")
        clean_t = (title or sid[:8]).replace("|", "｜").replace("[", "［").replace("]", "］")[:55]
        if rel_p:
            link_str = f"[[{rel_p[:-3] if rel_p.endswith('.md') else rel_p}|{clean_t}]]"
        else:
            link_str = f"`{sid[:8]}` {clean_t}"
        md += f"| `{up_short}` | **{prov.upper()}** | {m_cnt} | {link_str} |\n"

    md += """
---

## 3. 全AI共通の検索・参照コマンド

### ターミナル / AIエージェントからの高速全文検索 (FTS5)
```bash
# 全3大AI（Codex / Claude / Antigravity）横断でキーワード検索
chat-archive search "<キーワード>"

# プロバイダ指定検索 (codex / claude / antigravity)
chat-archive search "<キーワード>" --provider antigravity

# 会話全文をObsidian形式で表示
chat-archive show <session_id> --thinking --tools --obsidian

# 最新セッションの即時インデックス＆Obsidian書き出し同期
chat-archive sync
```

### 共通記憶・全ノート横断検索 (`ai-memory`)
```bash
# Obsidian全707+ノート、Claude記憶(1,633件)、Codex記憶(MEMORY.md)、全チャット履歴を一括横断検索
ai-memory search "<キーワード>"
ai-memory get "<トピック>"
```
"""
    CHAT_ARCHIVE_MD.parent.mkdir(parents=True, exist_ok=True)
    CHAT_ARCHIVE_MD.write_text(md, encoding="utf-8")


if __name__ == "__main__":
    export_sessions_to_obsidian(verbose=True)
