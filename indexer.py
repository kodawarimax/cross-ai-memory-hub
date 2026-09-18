#!/usr/bin/env python3
"""
indexer.py - Codex & Claude session indexer with SQLite FTS5.
Scans ~/.codex/sessions and ~/.claude/projects, extracting metadata and
conversations into a searchable SQLite full-text database.
"""

import glob
import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "archive.db"

CODEX_DIR = Path(os.path.expanduser("~/.codex"))
CLAUDE_DIR = Path(os.path.expanduser("~/.claude"))

def init_db(conn: sqlite3.Connection):
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA cache_size = 100000;")

    conn.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        provider TEXT NOT NULL,
        title TEXT,
        project_path TEXT,
        file_path TEXT NOT NULL,
        created_at TEXT,
        updated_at TEXT,
        message_count INTEGER DEFAULT 0,
        preview TEXT,
        mtime REAL
    );
    """)

    conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_provider ON sessions(provider);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions(updated_at DESC);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project_path);")

    # FTS5 Virtual Table for full-text search
    conn.execute("""
    CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
        session_id UNINDEXED,
        provider UNINDEXED,
        role,
        content,
        timestamp UNINDEXED,
        tokenize = 'unicode61'
    );
    """)

def load_codex_name_map() -> dict:
    name_map = {}
    index_file = CODEX_DIR / "session_index.jsonl"
    if index_file.exists():
        try:
            with open(index_file, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    try:
                        d = json.loads(line)
                        sid = d.get("id")
                        name = d.get("thread_name")
                        up = d.get("updated_at")
                        if sid:
                            name_map[sid] = {"name": name, "updated_at": up}
                    except Exception:
                        pass
        except Exception as e:
            print(f"Warning loading codex name map: {e}", file=sys.stderr)
    return name_map

def clean_text_preview(text: str, max_len: int = 200) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    return cleaned[:max_len]

def parse_codex_file(file_path: Path, codex_names: dict):
    mtime = file_path.stat().st_mtime
    session_id = None
    cwd = None
    created_at = None
    updated_at = None
    messages = []
    first_user_prompt = None

    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue

                ts = d.get("timestamp")
                if not created_at and ts:
                    created_at = ts
                if ts:
                    updated_at = ts

                t = d.get("type")
                if t == "session_meta":
                    payload = d.get("payload", {})
                    session_id = payload.get("id") or session_id
                    cwd = payload.get("cwd") or cwd
                    if payload.get("timestamp"):
                        created_at = payload.get("timestamp")

                elif t == "turn_context":
                    payload = d.get("payload", {})
                    cwd = payload.get("cwd") or cwd

                elif t == "response_item":
                    payload = d.get("payload", {})
                    p_type = payload.get("type")
                    if p_type == "message":
                        role = payload.get("role")
                        if role in ("user", "assistant"):
                            content_items = payload.get("content", [])
                            text_parts = []
                            for c in content_items:
                                if isinstance(c, dict):
                                    txt = c.get("text", "")
                                    if txt:
                                        text_parts.append(txt)
                            full_text = "\n".join(text_parts).strip()
                            if full_text:
                                # Skip system prompt injections in user message if possible
                                is_system = (role == "user" and (
                                    full_text.startswith("# AGENTS.md") or 
                                    full_text.startswith("<INSTRUCTIONS>") or
                                    full_text.startswith("<environment_context>")
                                ))
                                if not is_system:
                                    if role == "user" and not first_user_prompt:
                                        first_user_prompt = full_text
                                messages.append({
                                    "role": role,
                                    "content": full_text[:4000],  # index up to 4000 chars
                                    "timestamp": ts or ""
                                })

    except Exception:
        return None

    if not session_id:
        # try to extract from filename: rollout-YYYY-MM-DDTHH-MM-SS-<uuid>.jsonl
        match = re.search(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", file_path.name)
        if match:
            session_id = match.group(1)
        else:
            session_id = file_path.stem

    # Determine title
    title = None
    if session_id in codex_names:
        title = codex_names[session_id].get("name")
        if not updated_at and codex_names[session_id].get("updated_at"):
            updated_at = codex_names[session_id].get("updated_at")

    if not title and first_user_prompt:
        title = clean_text_preview(first_user_prompt, 80)
    if not title:
        title = f"Codex Session {session_id[:8]}"

    preview = clean_text_preview(first_user_prompt or (messages[0]["content"] if messages else ""), 200)

    if not created_at:
        created_at = datetime.fromtimestamp(mtime).isoformat()
    if not updated_at:
        updated_at = created_at

    return {
        "session_id": session_id,
        "provider": "codex",
        "title": title,
        "project_path": cwd or "",
        "file_path": str(file_path),
        "created_at": created_at,
        "updated_at": updated_at,
        "message_count": len(messages),
        "preview": preview,
        "mtime": mtime,
        "messages": messages
    }

def decode_claude_project_path(escaped_dir_name: str) -> str:
    if escaped_dir_name.startswith("-"):
        return "/" + escaped_dir_name[1:].replace("-", "/")
    return escaped_dir_name.replace("-", "/")

def parse_claude_file(file_path: Path):
    mtime = file_path.stat().st_mtime
    session_id = file_path.stem
    parent_dir_name = file_path.parent.name
    cwd = decode_claude_project_path(parent_dir_name)
    created_at = None
    updated_at = None
    messages = []
    first_user_prompt = None

    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue

                ts = d.get("timestamp")
                if not created_at and ts:
                    created_at = ts
                if ts:
                    updated_at = ts

                file_cwd = d.get("cwd")
                if file_cwd:
                    cwd = file_cwd

                sid = d.get("sessionId")
                if sid:
                    session_id = sid

                t = d.get("type")
                if t == "user":
                    msg = d.get("message", {})
                    content = msg.get("content", "")
                    if isinstance(content, list):
                        parts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("text")]
                        text = "\n".join(parts).strip()
                    else:
                        text = str(content).strip()

                    if text:
                        if not first_user_prompt and not text.startswith("Invoke the `"):
                            first_user_prompt = text
                        messages.append({
                            "role": "user",
                            "content": text[:4000],
                            "timestamp": ts or ""
                        })

                elif t == "assistant":
                    msg = d.get("message", {})
                    content = msg.get("content", [])
                    if isinstance(content, list):
                        parts = []
                        for c in content:
                            if isinstance(c, dict) and c.get("type") == "text":
                                parts.append(c.get("text", ""))
                        text = "\n".join(parts).strip()
                    else:
                        text = str(content).strip()

                    if text:
                        messages.append({
                            "role": "assistant",
                            "content": text[:4000],
                            "timestamp": ts or ""
                        })

    except Exception:
        return None

    if not created_at:
        created_at = datetime.fromtimestamp(mtime).isoformat()
    if not updated_at:
        updated_at = created_at

    title = None
    if first_user_prompt:
        title = clean_text_preview(first_user_prompt, 80)
    if not title:
        title = f"Claude Session {session_id[:8]}"

    preview = clean_text_preview(first_user_prompt or (messages[0]["content"] if messages else ""), 200)

    return {
        "session_id": session_id,
        "provider": "claude",
        "title": title,
        "project_path": cwd or "",
        "file_path": str(file_path),
        "created_at": created_at,
        "updated_at": updated_at,
        "message_count": len(messages),
        "preview": preview,
        "mtime": mtime,
        "messages": messages
    }

def sync_indexes(verbose: bool = True):
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    # Get already indexed sessions and mtimes
    cursor = conn.cursor()
    cursor.execute("SELECT session_id, mtime FROM sessions;")
    indexed = dict(cursor.fetchall())

    if verbose:
        print(f"Current indexed sessions: {len(indexed)}")

    codex_names = load_codex_name_map()

    # 1. Collect Codex files
    codex_files = [Path(p) for p in glob.glob(os.path.expanduser("~/.codex/sessions/**/*.jsonl"), recursive=True)]
    # 2. Collect Claude files
    claude_files = [Path(p) for p in glob.glob(os.path.expanduser("~/.claude/projects/**/*.jsonl"), recursive=True)]

    total_files = len(codex_files) + len(claude_files)
    if verbose:
        print(f"Found {len(codex_files)} Codex files, {len(claude_files)} Claude files (Total: {total_files})")

    # Filter files that need updating
    to_process_codex = []
    for fp in codex_files:
        try:
            mt = fp.stat().st_mtime
            match = re.search(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", fp.name)
            sid = match.group(1) if match else fp.stem
            if sid not in indexed or indexed[sid] < mt:
                to_process_codex.append(fp)
        except Exception:
            pass

    to_process_claude = []
    for fp in claude_files:
        try:
            mt = fp.stat().st_mtime
            sid = fp.stem
            if sid not in indexed or indexed[sid] < mt:
                to_process_claude.append(fp)
        except Exception:
            pass

    if verbose:
        print(f"Files needing index: Codex={len(to_process_codex)}, Claude={len(to_process_claude)}")

    if not to_process_codex and not to_process_claude:
        if verbose:
            print("Index is already up to date.")
        conn.close()
        return 0

    batch_sessions = {} # sid -> session tuple
    batch_messages = [] # list of message tuples
    processed_count = 0
    start_time = time.time()

    def commit_batch():
        nonlocal batch_sessions, batch_messages
        if not batch_sessions:
            return
        
        sids = list(batch_sessions.keys())
        placeholders = ",".join("?" for _ in sids)
        conn.execute(f"DELETE FROM sessions WHERE session_id IN ({placeholders})", sids)
        conn.execute(f"DELETE FROM messages_fts WHERE session_id IN ({placeholders})", sids)

        conn.executemany("""
        INSERT OR REPLACE INTO sessions (session_id, provider, title, project_path, file_path, created_at, updated_at, message_count, preview, mtime)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, list(batch_sessions.values()))

        conn.executemany("""
        INSERT INTO messages_fts (session_id, provider, role, content, timestamp)
        VALUES (?, ?, ?, ?, ?)
        """, batch_messages)

        conn.commit()
        batch_sessions.clear()
        batch_messages.clear()

    # Process Codex
    for i, fp in enumerate(to_process_codex):
        res = parse_codex_file(fp, codex_names)
        if res:
            sid = res["session_id"]
            batch_sessions[sid] = (
                sid, res["provider"], res["title"], res["project_path"],
                res["file_path"], res["created_at"], res["updated_at"],
                res["message_count"], res["preview"], res["mtime"]
            )
            for m in res["messages"]:
                batch_messages.append((
                    sid, res["provider"], m["role"], m["content"], m["timestamp"]
                ))
            processed_count += 1

        if len(batch_sessions) >= 100:
            commit_batch()
            if verbose and (i + 1) % 500 == 0:
                print(f"Processed {i + 1}/{len(to_process_codex)} Codex files...")

    # Process Claude
    for i, fp in enumerate(to_process_claude):
        res = parse_claude_file(fp)
        if res:
            sid = res["session_id"]
            batch_sessions[sid] = (
                sid, res["provider"], res["title"], res["project_path"],
                res["file_path"], res["created_at"], res["updated_at"],
                res["message_count"], res["preview"], res["mtime"]
            )
            for m in res["messages"]:
                batch_messages.append((
                    sid, res["provider"], m["role"], m["content"], m["timestamp"]
                ))
            processed_count += 1

        if len(batch_sessions) >= 100:
            commit_batch()
            if verbose and (i + 1) % 200 == 0:
                print(f"Processed {i + 1}/{len(to_process_claude)} Claude files...")

    commit_batch()
    conn.close()

    elapsed = time.time() - start_time
    if verbose:
        print(f"Sync complete! Processed {processed_count} sessions in {elapsed:.2f}s.")
    return processed_count

if __name__ == "__main__":
    sync_indexes()
