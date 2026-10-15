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
                                    "content": full_text[:32000],  # index up to 32000 chars
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
    is_subagent = "subagents" in file_path.parts or file_path.stem.startswith("agent-")
    session_id = file_path.stem
    parent_dir_name = file_path.parent.parent.name if is_subagent else file_path.parent.name
    cwd = decode_claude_project_path(parent_dir_name)
    created_at = None
    updated_at = None
    messages = []
    first_user_prompt = None
    internal_sid = None

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

                sid = d.get("sessionId") or d.get("session_id")
                if sid and not internal_sid:
                    internal_sid = sid

                t = d.get("type")
                if t == "queue-operation" and d.get("content"):
                    text = str(d.get("content")).strip()
                    if text:
                        if not first_user_prompt:
                            first_user_prompt = text
                        messages.append({
                            "role": "user",
                            "content": text[:32000],
                            "timestamp": ts or ""
                        })
                elif t == "user":
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
                            "content": text[:32000],
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
                            "content": text[:32000],
                            "timestamp": ts or ""
                        })

    except Exception:
        return None

    # Avoid overwriting parent sessions when indexing subagents or audit.jsonl files
    if is_subagent and internal_sid:
        session_id = f"{internal_sid}__{file_path.stem}"
    elif file_path.name == "audit.jsonl":
        session_id = f"claude-desktop-{internal_sid or file_path.parent.name}"
    else:
        session_id = file_path.stem

    if not created_at:
        created_at = datetime.fromtimestamp(mtime).isoformat()
    if not updated_at:
        updated_at = created_at

    title = None
    if first_user_prompt:
        title = clean_text_preview(first_user_prompt, 80)
    if not title:
        title = f"Claude Session {session_id[:8]}"
    if is_subagent:
        title = f"[Subagent] {title}"

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

def extract_agy_user_text(raw_content: str) -> str:
    if not raw_content:
        return ""
    m = re.search(r"<USER_REQUEST>(.*?)</USER_REQUEST>", raw_content, re.DOTALL)
    if m:
        return m.group(1).strip()
    cleaned = re.sub(r"<ADDITIONAL_METADATA>.*?</ADDITIONAL_METADATA>", "", raw_content, flags=re.DOTALL)
    cleaned = re.sub(r"<USER_SETTINGS_CHANGE>.*?</USER_SETTINGS_CHANGE>", "", cleaned, flags=re.DOTALL)
    return cleaned.strip()

def parse_antigravity_file(file_path: Path):
    mtime = file_path.stat().st_mtime
    try:
        session_id = file_path.parents[2].name
    except Exception:
        session_id = file_path.stem

    created_at = None
    updated_at = None
    messages = []
    first_user_prompt = None
    cwd = str(Path.home() / "Claude")

    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue

                ts = d.get("created_at")
                if not created_at and ts:
                    created_at = ts
                if ts:
                    updated_at = ts

                t = d.get("type")
                if t == "USER_INPUT":
                    raw_c = str(d.get("content") or "")
                    text = extract_agy_user_text(raw_c)
                    if text:
                        if not first_user_prompt:
                            first_user_prompt = text
                        messages.append({
                            "role": "user",
                            "content": text[:32000],
                            "timestamp": ts or ""
                        })
                elif t == "PLANNER_RESPONSE":
                    text = str(d.get("content") or "").strip()
                    if text and text != "None":
                        messages.append({
                            "role": "assistant",
                            "content": text[:32000],
                            "timestamp": ts or ""
                        })
    except Exception:
        return None

    if not created_at:
        created_at = datetime.fromtimestamp(mtime).isoformat()
    if not updated_at:
        updated_at = created_at

    title = clean_text_preview(first_user_prompt, 80) if first_user_prompt else f"Antigravity Session {session_id[:8]}"
    preview = clean_text_preview(first_user_prompt or (messages[0]["content"] if messages else ""), 200)

    return {
        "session_id": session_id,
        "provider": "antigravity",
        "title": title,
        "project_path": cwd,
        "file_path": str(file_path),
        "created_at": created_at,
        "updated_at": updated_at,
        "message_count": len(messages),
        "preview": preview,
        "mtime": mtime,
        "messages": messages
    }

def parse_codex_zst_file(file_path: Path, codex_names: dict):
    """Decompress and parse ~/.codex/archived_sessions/*.jsonl.zst files."""
    import subprocess
    mtime = file_path.stat().st_mtime
    match = re.search(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", file_path.name)
    session_id = match.group(1) if match else file_path.name.replace(".jsonl.zst", "")
    cwd = ""
    created_at = None
    updated_at = None
    messages = []
    first_user_prompt = None

    try:
        raw_out = subprocess.check_output(["zstd", "-dc", str(file_path)], text=True, errors="ignore")
        for line in raw_out.splitlines():
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
            elif t == "turn_context":
                cwd = d.get("payload", {}).get("cwd") or cwd
            elif t == "response_item":
                payload = d.get("payload", {})
                if payload.get("type") == "message":
                    role = payload.get("role")
                    if role in ("user", "assistant"):
                        text_parts = [c.get("text", "") for c in payload.get("content", []) if isinstance(c, dict) and c.get("text")]
                        full_text = "\n".join(text_parts).strip()
                        if full_text:
                            is_sys = (role == "user" and (full_text.startswith("# AGENTS.md") or full_text.startswith("<INSTRUCTIONS>") or full_text.startswith("<environment_context>")))
                            if not is_sys and role == "user" and not first_user_prompt:
                                first_user_prompt = full_text
                            messages.append({"role": role, "content": full_text[:32000], "timestamp": ts or ""})
    except Exception:
        return None

    if not created_at:
        created_at = datetime.fromtimestamp(mtime).isoformat()
    if not updated_at:
        updated_at = created_at
    title = codex_names.get(session_id, {}).get("name") or (clean_text_preview(first_user_prompt, 80) if first_user_prompt else f"Codex Archived {session_id[:8]}")
    preview = clean_text_preview(first_user_prompt or (messages[0]["content"] if messages else ""), 200)
    return {
        "session_id": session_id,
        "provider": "codex",
        "title": title,
        "project_path": cwd,
        "file_path": str(file_path),
        "created_at": created_at,
        "updated_at": updated_at,
        "message_count": len(messages),
        "preview": preview,
        "mtime": mtime,
        "messages": messages,
    }

def collect_codex_sqlite_sessions(indexed: dict, codex_names: dict) -> list:
    codex_homes = [CODEX_DIR, Path(os.path.expanduser("~/.openclaw/agents/main/agent/codex-home"))]
    for p in Path.home().glob(".codex-*"):
        if p.is_dir() and p not in codex_homes:
            codex_homes.append(p)
    results = []
    for home_dir in codex_homes:
        state_db = home_dir / "state_5.sqlite"
        hist_db = home_dir / "thread_history_1.sqlite"
        mem_db = home_dir / "memories_1.sqlite"

        # 1. state_5 + thread_history_1
        if state_db.exists() and hist_db.exists():
            try:
                s_conn = sqlite3.connect(str(state_db), timeout=5.0)
                h_conn = sqlite3.connect(str(hist_db), timeout=5.0)
                threads = s_conn.execute("""
                    SELECT id, title, cwd, created_at, updated_at, rollout_path, first_user_message, preview
                    FROM threads
                """).fetchall()
                for row in threads:
                    tid, title, cwd, c_at, u_at, r_path, first_u, prev = row
                    if not tid:
                        continue
                    if r_path and os.path.exists(r_path):
                        continue
                    mt = float(u_at or c_at or 0)
                    if tid in indexed and indexed[tid] >= mt:
                        continue
                    item_rows = h_conn.execute("""
                        SELECT item_type, item_json, created_at_ms
                        FROM thread_items
                        WHERE thread_id = ? AND item_type IN ('userMessage', 'agentMessage')
                        ORDER BY rollout_ordinal ASC, created_at_ms ASC
                    """, (tid,)).fetchall()
                    messages = []
                    first_prompt = first_u or ""
                    for itype, ijson, cms in item_rows:
                        try:
                            jd = json.loads(ijson)
                        except Exception:
                            continue
                        ts_iso = datetime.fromtimestamp(cms / 1000.0).isoformat() if cms else ""
                        if itype == "userMessage":
                            c_list = jd.get("content", [])
                            txt = "\n".join(c.get("text", "") for c in c_list if isinstance(c, dict) and c.get("text")).strip()
                            if txt and not txt.startswith("# AGENTS.md") and not txt.startswith("<INSTRUCTIONS>"):
                                if not first_prompt:
                                    first_prompt = txt
                                messages.append({"role": "user", "content": txt[:32000], "timestamp": ts_iso})
                        elif itype == "agentMessage":
                            txt = str(jd.get("text") or "").strip()
                            if txt:
                                messages.append({"role": "assistant", "content": txt[:32000], "timestamp": ts_iso})
                    if not messages and first_prompt:
                        c_iso = datetime.fromtimestamp(c_at).isoformat() if c_at else ""
                        messages.append({"role": "user", "content": first_prompt[:32000], "timestamp": c_iso})
                    if not messages:
                        continue
                    c_iso = datetime.fromtimestamp(c_at).isoformat() if c_at else datetime.now().isoformat()
                    u_iso = datetime.fromtimestamp(u_at).isoformat() if u_at else c_iso
                    if not title and tid in codex_names:
                        title = codex_names[tid].get("name")
                    if not title and first_prompt:
                        title = clean_text_preview(first_prompt, 80)
                    if not title:
                        title = f"Codex Session {tid[:8]}"
                    preview_txt = clean_text_preview(prev or first_prompt or messages[0]["content"], 200)
                    results.append({
                        "session_id": tid,
                        "provider": "codex",
                        "title": title,
                        "project_path": cwd or "",
                        "file_path": f"sqlite://thread_history_1/{tid}",
                        "created_at": c_iso,
                        "updated_at": u_iso,
                        "message_count": len(messages),
                        "preview": preview_txt,
                        "mtime": mt,
                        "messages": messages
                    })
                s_conn.close()
                h_conn.close()
            except Exception as e:
                print(f"Warning reading Codex SQLite in {home_dir}: {e}", file=sys.stderr)

        # 2. memories_1.sqlite (stage1_outputs distilled memories)
        if mem_db.exists():
            try:
                m_conn = sqlite3.connect(str(mem_db), timeout=5.0)
                rows = m_conn.execute("""
                    SELECT thread_id, source_updated_at, raw_memory, rollout_summary, rollout_slug, generated_at
                    FROM stage1_outputs
                """).fetchall()
                for tid, s_up, raw_mem, r_sum, r_slug, gen_at in rows:
                    sid = f"codex-mem-{tid}"
                    mt = float(s_up or gen_at or 0)
                    if sid in indexed and indexed[sid] >= mt:
                        continue
                    body = f"## Rollout Summary\n\n{r_sum or ''}\n\n## Raw Distilled Memory\n\n{raw_mem or ''}".strip()
                    if not body:
                        continue
                    c_iso = datetime.fromtimestamp(mt).isoformat() if mt > 0 else datetime.now().isoformat()
                    title = f"[Codex Memory] {(r_slug or tid[:8]).replace('-', ' ')}"
                    results.append({
                        "session_id": sid,
                        "provider": "codex",
                        "title": title[:80],
                        "project_path": str(home_dir),
                        "file_path": f"sqlite://memories_1/{tid}",
                        "created_at": c_iso,
                        "updated_at": c_iso,
                        "message_count": 1,
                        "preview": clean_text_preview(r_sum or raw_mem or "", 200),
                        "mtime": mt,
                        "messages": [{"role": "assistant", "content": body[:32000], "timestamp": c_iso}]
                    })
                m_conn.close()
            except Exception:
                pass

    return results

def collect_history_and_subfolder_sessions(indexed: dict) -> list:
    """
    Harvests all remaining conversation stores across the user's home directory:
    1. ~/.claude/history.jsonl (all prompts across every subfolder, grouped by sessionId)
    2. ~/.codex/history.jsonl & ~/.codex/transcription-history.jsonl (voice dictations & CLI prompts)
    3. ~/Claude/dev/open-dot/.data/dots.db (Open-Dot autonomous agent conversations & memories)
    4. ~/Skill/data/history/*.json & ~/Skill/temp/voice_chat_history.json
    5. Any ChatGPT export (conversations.json) across ~/{Downloads,Desktop,Documents,Claude}
    """
    home = Path.home()
    results = []

    # 1. ~/.claude/history.jsonl (capture prompts for sessions whose JSONL was cleaned up or in ephemeral folders)
    claude_hist = CLAUDE_DIR / "history.jsonl"
    if claude_hist.exists():
        mt = claude_hist.stat().st_mtime
        by_sid = {}
        try:
            for line in claude_hist.read_text(encoding="utf-8", errors="ignore").splitlines():
                if not line.strip():
                    continue
                d = json.loads(line)
                sid = d.get("sessionId")
                disp = str(d.get("display") or "").strip()
                proj = str(d.get("project") or "")
                ts_ms = d.get("timestamp")
                if sid and disp and not disp.startswith("/"):
                    by_sid.setdefault(sid, {"project": proj, "msgs": [], "ts_ms": ts_ms})
                    ts_iso = datetime.fromtimestamp(ts_ms / 1000.0).isoformat() if ts_ms else ""
                    by_sid[sid]["msgs"].append({"role": "user", "content": disp[:32000], "timestamp": ts_iso})
                    if ts_ms:
                        by_sid[sid]["ts_ms"] = ts_ms
            for sid, info in by_sid.items():
                # Only add if the full JSONL session isn't already indexed
                if sid in indexed:
                    continue
                h_sid = f"claude-hist-{sid}"
                if h_sid in indexed and indexed[h_sid] >= mt:
                    continue
                msgs = info["msgs"]
                if not msgs:
                    continue
                c_iso = msgs[0]["timestamp"] or datetime.fromtimestamp(mt).isoformat()
                u_iso = msgs[-1]["timestamp"] or c_iso
                results.append({
                    "session_id": h_sid,
                    "provider": "claude",
                    "title": f"[CLI History] {clean_text_preview(msgs[0]['content'], 65)}",
                    "project_path": info["project"],
                    "file_path": str(claude_hist),
                    "created_at": c_iso,
                    "updated_at": u_iso,
                    "message_count": len(msgs),
                    "preview": clean_text_preview(msgs[0]["content"], 200),
                    "mtime": mt,
                    "messages": msgs
                })
        except Exception:
            pass

    # 2. ~/.codex/transcription-history.jsonl & ~/.codex/history.jsonl
    for fname, label in [("transcription-history.jsonl", "Voice Dictation"), ("history.jsonl", "Codex CLI History")]:
        fpath = CODEX_DIR / fname
        if fpath.exists():
            mt = fpath.stat().st_mtime
            sid = f"codex-{fname.replace('.jsonl', '')}"
            if sid not in indexed or indexed[sid] < mt:
                msgs = []
                try:
                    for line in fpath.read_text(encoding="utf-8", errors="ignore").splitlines():
                        if not line.strip():
                            continue
                        d = json.loads(line)
                        txt = str(d.get("text") or "").strip()
                        ts_val = d.get("createdAtMs") or (d.get("ts", 0) * 1000 if d.get("ts") else 0)
                        ts_iso = datetime.fromtimestamp(ts_val / 1000.0).isoformat() if ts_val else ""
                        if txt:
                            msgs.append({"role": "user", "content": txt[:32000], "timestamp": ts_iso})
                    if msgs:
                        c_iso = msgs[0]["timestamp"] or datetime.fromtimestamp(mt).isoformat()
                        u_iso = msgs[-1]["timestamp"] or c_iso
                        results.append({
                            "session_id": sid,
                            "provider": "codex",
                            "title": f"[{label}] 音声・直接入力ログ ({len(msgs)}件)",
                            "project_path": str(CODEX_DIR),
                            "file_path": str(fpath),
                            "created_at": c_iso,
                            "updated_at": u_iso,
                            "message_count": len(msgs),
                            "preview": clean_text_preview(msgs[-1]["content"], 200),
                            "mtime": mt,
                            "messages": msgs
                        })
                except Exception:
                    pass

    # 3. Open-Dot conversations & memories (~/Claude/dev/open-dot/.data/dots.db)
    dots_db = home / "Claude" / "dev" / "open-dot" / ".data" / "dots.db"
    if dots_db.exists():
        mt = dots_db.stat().st_mtime
        try:
            d_conn = sqlite3.connect(str(dots_db), timeout=5.0)
            convs = d_conn.execute("SELECT id, dot_id, title, created_at, updated_at FROM conversations").fetchall()
            for cid, dot_id, title, c_ms, u_ms in convs:
                sid = f"opendot-{cid}"
                c_mt = float(u_ms or c_ms or mt * 1000) / 1000.0
                if sid in indexed and indexed[sid] >= c_mt:
                    continue
                m_rows = d_conn.execute(
                    "SELECT role, text, created_at FROM messages WHERE conversation_id = ? ORDER BY created_at ASC",
                    (cid,)
                ).fetchall()
                msgs = []
                for role, txt, m_ms in m_rows:
                    if not txt:
                        continue
                    r_norm = "user" if role == "user" else "assistant"
                    t_iso = datetime.fromtimestamp(m_ms / 1000.0).isoformat() if m_ms else ""
                    msgs.append({"role": r_norm, "content": str(txt)[:32000], "timestamp": t_iso})
                if not msgs:
                    continue
                c_iso = datetime.fromtimestamp(c_ms / 1000.0).isoformat() if c_ms else datetime.now().isoformat()
                u_iso = datetime.fromtimestamp(u_ms / 1000.0).isoformat() if u_ms else c_iso
                results.append({
                    "session_id": sid,
                    "provider": "codex",
                    "title": f"[OpenDot] {title or cid}",
                    "project_path": str(dots_db.parent),
                    "file_path": f"sqlite://dots.db/{cid}",
                    "created_at": c_iso,
                    "updated_at": u_iso,
                    "message_count": len(msgs),
                    "preview": clean_text_preview(msgs[0]["content"], 200),
                    "mtime": c_mt,
                    "messages": msgs
                })
            d_conn.close()
        except Exception:
            pass

    # 4. Auto-detect ChatGPT export .zip files in ~/Downloads, ~/Desktop, ~/Documents and extract conversations.json
    import zipfile
    export_dest_dir = CODEX_DIR / ".chatgpt-projects" / "auto-extracted-exports"
    for z_dir in [home / "Downloads", home / "Desktop", home / "Documents"]:
        if not z_dir.exists():
            continue
        for z_file in z_dir.glob("*.zip"):
            try:
                if z_file.stat().st_size > 2 * 1024 * 1024 * 1024:
                    continue
                with zipfile.ZipFile(z_file, "r") as zf:
                    names = zf.namelist()
                    conv_members = [n for n in names if n == "conversations.json" or n.endswith("/conversations.json")]
                    if conv_members:
                        target_out = export_dest_dir / z_file.stem / "conversations.json"
                        if not target_out.exists() or target_out.stat().st_mtime < z_file.stat().st_mtime:
                            target_out.parent.mkdir(parents=True, exist_ok=True)
                            target_out.write_bytes(zf.read(conv_members[0]))
            except Exception:
                pass

    # 5. Any ChatGPT conversations.json exports in ~/Downloads, ~/Desktop, ~/Documents, ~/.codex/.chatgpt-projects
    for search_dir in [home / "Downloads", home / "Desktop", home / "Documents", CODEX_DIR / ".chatgpt-projects"]:
        if not search_dir.exists():
            continue
        for conv_file in search_dir.rglob("conversations.json"):
            try:
                mt = conv_file.stat().st_mtime
                data = json.loads(conv_file.read_text(encoding="utf-8", errors="ignore"))
                if not isinstance(data, list):
                    continue
                for item in data:
                    if not isinstance(item, dict) or "mapping" not in item:
                        continue
                    cid = item.get("id") or item.get("conversation_id")
                    if not cid:
                        continue
                    sid = f"chatgpt-{cid}"
                    u_time = float(item.get("update_time") or item.get("create_time") or mt)
                    if sid in indexed and indexed[sid] >= u_time:
                        continue
                    msgs = []
                    for node in item.get("mapping", {}).values():
                        msg = node.get("message") if isinstance(node, dict) else None
                        if not msg:
                            continue
                        role = (msg.get("author") or {}).get("role")
                        if role not in ("user", "assistant"):
                            continue
                        parts = (msg.get("content") or {}).get("parts") or []
                        txt = "\n".join(str(p) for p in parts if isinstance(p, str) and p.strip()).strip()
                        if txt:
                            m_ts = msg.get("create_time")
                            t_iso = datetime.fromtimestamp(m_ts).isoformat() if m_ts else ""
                            msgs.append({"role": role, "content": txt[:32000], "timestamp": t_iso})
                    if not msgs:
                        continue
                    c_iso = datetime.fromtimestamp(item.get("create_time") or u_time).isoformat()
                    u_iso = datetime.fromtimestamp(u_time).isoformat()
                    title = item.get("title") or clean_text_preview(msgs[0]["content"], 80)
                    results.append({
                        "session_id": sid,
                        "provider": "codex",
                        "title": f"[ChatGPT] {title}",
                        "project_path": str(conv_file.parent),
                        "file_path": str(conv_file),
                        "created_at": c_iso,
                        "updated_at": u_iso,
                        "message_count": len(msgs),
                        "preview": clean_text_preview(msgs[0]["content"], 200),
                        "mtime": u_time,
                        "messages": msgs
                    })
            except Exception:
                pass

    return results

def sync_indexes(verbose: bool = True, export_obsidian: bool = True):
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    cursor = conn.cursor()
    cursor.execute("SELECT session_id, mtime FROM sessions;")
    indexed = dict(cursor.fetchall())

    if verbose:
        print(f"Current indexed sessions: {len(indexed)}")

    codex_names = load_codex_name_map()

    # 1. Collect Codex JSONL files across all Codex homes + archived .jsonl.zst
    codex_files = (
        [Path(p) for p in glob.glob(os.path.expanduser("~/.codex/sessions/**/*.jsonl"), recursive=True)]
        + [Path(p) for p in glob.glob(os.path.expanduser("~/.openclaw/agents/**/codex-home/sessions/**/*.jsonl"), recursive=True)]
    )
    codex_zst_files = [Path(p) for p in glob.glob(os.path.expanduser("~/.codex/archived_sessions/**/*.jsonl.zst"), recursive=True)]

    # 2. Collect Claude JSONL files across all 54+ ~/.claude/projects subfolders AND Claude Desktop App
    claude_files = (
        [Path(p) for p in glob.glob(os.path.expanduser("~/.claude/projects/**/*.jsonl"), recursive=True)]
        + [Path(p) for p in glob.glob(os.path.expanduser("~/Library/Application Support/Claude/local-agent-mode-sessions/**/*.jsonl"), recursive=True)]
    )

    # 3. Collect Antigravity transcript.jsonl files
    agy_files = [Path(p) for p in glob.glob(os.path.expanduser("~/.gemini/antigravity/brain/*/.system_generated/logs/transcript.jsonl"))]

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

    to_process_codex_zst = []
    for fp in codex_zst_files:
        try:
            mt = fp.stat().st_mtime
            match = re.search(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", fp.name)
            sid = match.group(1) if match else fp.name.replace(".jsonl.zst", "")
            if sid not in indexed or indexed[sid] < mt:
                to_process_codex_zst.append(fp)
        except Exception:
            pass

    to_process_claude = []
    for fp in claude_files:
        try:
            mt = fp.stat().st_mtime
            is_sub = "subagents" in fp.parts or fp.stem.startswith("agent-")
            sid = f"{fp.parent.parent.name}__{fp.stem}" if is_sub else (f"claude-desktop-{fp.parent.name}" if fp.name == "audit.jsonl" else fp.stem)
            if sid not in indexed or indexed[sid] < mt:
                to_process_claude.append(fp)
        except Exception:
            pass

    to_process_agy = []
    for fp in agy_files:
        try:
            mt = fp.stat().st_mtime
            sid = fp.parents[2].name
            if sid not in indexed or indexed[sid] < mt:
                to_process_agy.append(fp)
        except Exception:
            pass

    # 4. Collect Codex SQLite sessions + memories_1.sqlite
    codex_sqlite_sessions = collect_codex_sqlite_sessions(indexed, codex_names)

    # 5. Collect subfolder histories, voice dictations, Open-Dot DB, and ChatGPT exports
    extra_sessions = collect_history_and_subfolder_sessions(indexed)

    if verbose:
        print(
            f"Files needing index: Codex(JSONL)={len(to_process_codex)}, "
            f"Codex(ZST)={len(to_process_codex_zst)}, "
            f"Codex(SQLite+Mem)={len(codex_sqlite_sessions)}, "
            f"Claude(AllSubfolders+Desktop)={len(to_process_claude)}, "
            f"Antigravity={len(to_process_agy)}, "
            f"Extra(Hist+Voice+OpenDot+ChatGPT)={len(extra_sessions)}"
        )

    batch_sessions = {}
    batch_messages = []
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

    def add_res_to_batch(res):
        nonlocal processed_count
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

    for fp in to_process_codex:
        res = parse_codex_file(fp, codex_names)
        if res:
            add_res_to_batch(res)
        if len(batch_sessions) >= 100:
            commit_batch()

    for fp in to_process_codex_zst:
        res = parse_codex_zst_file(fp, codex_names)
        if res:
            add_res_to_batch(res)
        if len(batch_sessions) >= 100:
            commit_batch()

    for res in codex_sqlite_sessions:
        add_res_to_batch(res)
        if len(batch_sessions) >= 100:
            commit_batch()

    for i, fp in enumerate(to_process_claude):
        res = parse_claude_file(fp)
        if res:
            add_res_to_batch(res)
        if len(batch_sessions) >= 100:
            commit_batch()

    for fp in to_process_agy:
        res = parse_antigravity_file(fp)
        if res:
            add_res_to_batch(res)
        if len(batch_sessions) >= 50:
            commit_batch()

    for res in extra_sessions:
        add_res_to_batch(res)
        if len(batch_sessions) >= 100:
            commit_batch()

    commit_batch()
    conn.close()

    elapsed = time.time() - start_time
    if verbose:
        print(f"Sync complete! Processed {processed_count} sessions in {elapsed:.2f}s.")

    if export_obsidian:
        try:
            from obsidian_exporter import export_sessions_to_obsidian
            export_sessions_to_obsidian(verbose=verbose)
        except Exception as e:
            if verbose:
                print(f"Warning during Obsidian export: {e}", file=sys.stderr)

    return processed_count

if __name__ == "__main__":
    sync_indexes()
