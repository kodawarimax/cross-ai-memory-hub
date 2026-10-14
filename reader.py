#!/usr/bin/env python3
"""
reader.py - Renders full conversation from Codex or Claude session JSONL file.
Formats output as clean Markdown, terminal text, or JSON.
"""

import json
import os
import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "archive.db"

def get_session_info(session_id: str):
    if not DB_PATH.exists():
        return None
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
    SELECT session_id, provider, title, project_path, file_path, created_at, updated_at, message_count
    FROM sessions
    WHERE session_id = ? OR session_id LIKE ?
    LIMIT 1
    """, (session_id, f"{session_id}%"))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "session_id": row[0],
        "provider": row[1],
        "title": row[2],
        "project_path": row[3],
        "file_path": row[4],
        "created_at": row[5],
        "updated_at": row[6],
        "message_count": row[7],
    }

def extract_text_from_blocks(blocks):
    if isinstance(blocks, str):
        return blocks
    if not isinstance(blocks, list):
        return str(blocks)
    texts = []
    for b in blocks:
        if isinstance(b, str):
            texts.append(b)
        elif isinstance(b, dict):
            if "text" in b:
                texts.append(str(b["text"]))
            elif "summary" in b:
                texts.append(extract_text_from_blocks(b["summary"]))
            elif "content" in b:
                texts.append(extract_text_from_blocks(b["content"]))
    return "\n".join(texts).strip()

def read_codex_session(file_path: str):
    messages = []
    meta = {}
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue

            t = d.get("type")
            ts = d.get("timestamp", "")

            if t == "session_meta":
                meta.update(d.get("payload", {}))
            elif t == "turn_context":
                p = d.get("payload", {})
                if p.get("model"):
                    meta["model"] = p.get("model")
                if p.get("cwd"):
                    meta["cwd"] = p.get("cwd")

            elif t == "response_item":
                payload = d.get("payload", {})
                p_type = payload.get("type")

                if p_type == "message":
                    role = payload.get("role")
                    content_items = payload.get("content", [])
                    full_text = extract_text_from_blocks(content_items)
                    if full_text:
                        if role == "user" and (full_text.startswith("# AGENTS.md instructions") or full_text.startswith("<INSTRUCTIONS>")):
                            continue
                        messages.append({
                            "role": role,
                            "type": "message",
                            "content": full_text,
                            "timestamp": ts
                        })

                elif p_type == "reasoning":
                    summary = payload.get("summary")
                    thinking_text = extract_text_from_blocks(summary)
                    if thinking_text:
                        messages.append({
                            "role": "assistant",
                            "type": "reasoning",
                            "content": thinking_text,
                            "timestamp": ts
                        })

                elif p_type == "function_call":
                    name = payload.get("name", "tool")
                    args = payload.get("arguments", "")
                    messages.append({
                        "role": "assistant",
                        "type": "tool_call",
                        "name": name,
                        "arguments": args,
                        "timestamp": ts
                    })

                elif p_type == "function_call_output":
                    output = payload.get("output", "")
                    if len(output) > 2000:
                        output = output[:2000] + f"\n... [Truncated {len(output)-2000} chars]"
                    messages.append({
                        "role": "tool",
                        "type": "tool_output",
                        "content": output,
                        "timestamp": ts
                    })

    return meta, messages

def read_claude_session(file_path: str):
    messages = []
    meta = {}
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue

            t = d.get("type")
            ts = d.get("timestamp", "")

            if d.get("cwd"):
                meta["cwd"] = d.get("cwd")
            if d.get("version"):
                meta["version"] = d.get("version")
            if d.get("gitBranch"):
                meta["gitBranch"] = d.get("gitBranch")

            if t == "user":
                msg = d.get("message", {})
                content = msg.get("content", "")
                text = extract_text_from_blocks(content)
                if text:
                    messages.append({
                        "role": "user",
                        "type": "message",
                        "content": text,
                        "timestamp": ts
                    })

            elif t == "assistant":
                msg = d.get("message", {})
                content = msg.get("content", [])
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict):
                            itype = item.get("type")
                            if itype == "text":
                                txt = item.get("text", "").strip()
                                if txt:
                                    messages.append({
                                        "role": "assistant",
                                        "type": "message",
                                        "content": txt,
                                        "timestamp": ts
                                    })
                            elif itype == "thinking":
                                th = item.get("thinking", "").strip()
                                if th:
                                    messages.append({
                                        "role": "assistant",
                                        "type": "reasoning",
                                        "content": th,
                                        "timestamp": ts
                                    })
                            elif itype == "tool_use":
                                messages.append({
                                    "role": "assistant",
                                    "type": "tool_call",
                                    "name": item.get("name", "tool"),
                                    "arguments": json.dumps(item.get("input", {}), ensure_ascii=False),
                                    "timestamp": ts
                                })
                elif isinstance(content, str) and content.strip():
                    messages.append({
                        "role": "assistant",
                        "type": "message",
                        "content": content.strip(),
                        "timestamp": ts
                    })

    return meta, messages

def read_codex_sqlite_session(session_id: str):
    messages = []
    meta = {}
    codex_dir = Path(os.path.expanduser("~/.codex"))
    state_db = codex_dir / "state_5.sqlite"
    hist_db = codex_dir / "thread_history_1.sqlite"

    if state_db.exists():
        try:
            s_conn = sqlite3.connect(str(state_db), timeout=5.0)
            row = s_conn.execute(
                "SELECT cwd, model, git_branch, created_at, title, first_user_message FROM threads WHERE id = ?",
                (session_id,)
            ).fetchone()
            if row:
                meta["cwd"] = row[0] or ""
                meta["model"] = row[1] or ""
                meta["gitBranch"] = row[2] or ""
                if row[3]:
                    from datetime import datetime
                    meta["timestamp"] = datetime.fromtimestamp(row[3]).isoformat()
                meta["title"] = row[4] or ""
                meta["first_user_message"] = row[5] or ""
            s_conn.close()
        except Exception:
            pass

    if hist_db.exists():
        try:
            from datetime import datetime
            h_conn = sqlite3.connect(str(hist_db), timeout=5.0)
            rows = h_conn.execute("""
                SELECT item_type, item_json, created_at_ms
                FROM thread_items
                WHERE thread_id = ?
                ORDER BY rollout_ordinal ASC, created_at_ms ASC
            """, (session_id,)).fetchall()
            for itype, ijson, cms in rows:
                try:
                    jd = json.loads(ijson)
                except Exception:
                    continue
                ts = datetime.fromtimestamp(cms / 1000.0).isoformat() if cms else ""
                if itype == "userMessage":
                    c_list = jd.get("content", [])
                    txt = extract_text_from_blocks(c_list)
                    if txt and not txt.startswith("# AGENTS.md") and not txt.startswith("<INSTRUCTIONS>"):
                        messages.append({"role": "user", "type": "message", "content": txt, "timestamp": ts})
                elif itype == "agentMessage":
                    txt = str(jd.get("text") or "").strip()
                    if txt:
                        messages.append({"role": "assistant", "type": "message", "content": txt, "timestamp": ts})
                elif itype == "reasoning":
                    summary = jd.get("summary") or jd.get("content")
                    th_txt = extract_text_from_blocks(summary)
                    if th_txt:
                        messages.append({"role": "assistant", "type": "reasoning", "content": th_txt, "timestamp": ts})
                elif itype == "commandExecution":
                    cmd = jd.get("command", "")
                    messages.append({
                        "role": "assistant",
                        "type": "tool_call",
                        "name": "commandExecution",
                        "arguments": json.dumps({"command": cmd}, ensure_ascii=False),
                        "timestamp": ts
                    })
                    out = jd.get("aggregatedOutput") or ""
                    if out:
                        if len(out) > 2000:
                            out = out[:2000] + f"\n... [Truncated {len(out)-2000} chars]"
                        messages.append({"role": "tool", "type": "tool_output", "content": out, "timestamp": ts})
                elif itype == "mcpToolCall":
                    messages.append({
                        "role": "assistant",
                        "type": "tool_call",
                        "name": f"{jd.get('server', 'mcp')}.{jd.get('tool', 'call')}",
                        "arguments": json.dumps(jd.get("arguments", {}), ensure_ascii=False),
                        "timestamp": ts
                    })
                elif itype == "fileChange":
                    changes = jd.get("changes", [])
                    paths = [c.get("path", "") for c in changes if isinstance(c, dict)]
                    messages.append({
                        "role": "assistant",
                        "type": "tool_call",
                        "name": "fileChange",
                        "arguments": json.dumps({"files": paths}, ensure_ascii=False),
                        "timestamp": ts
                    })
            h_conn.close()
        except Exception:
            pass

    if not messages:
        messages = read_fts_fallback_messages(session_id)

    return meta, messages

def read_antigravity_session(file_path: str):
    import re
    messages = []
    meta = {"cwd": str(Path.home() / "Claude")}
    if not os.path.exists(file_path):
        return meta, messages

    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue

            t = d.get("type")
            ts = d.get("created_at", "")
            if not meta.get("timestamp") and ts:
                meta["timestamp"] = ts

            if t == "USER_INPUT":
                raw_c = str(d.get("content") or "")
                m = re.search(r"<USER_REQUEST>(.*?)</USER_REQUEST>", raw_c, re.DOTALL)
                txt = m.group(1).strip() if m else raw_c.strip()
                if txt:
                    messages.append({
                        "role": "user",
                        "type": "message",
                        "content": txt,
                        "timestamp": ts
                    })
            elif t == "PLANNER_RESPONSE":
                th = str(d.get("thinking") or "").strip()
                if th and th != "None":
                    messages.append({
                        "role": "assistant",
                        "type": "reasoning",
                        "content": th,
                        "timestamp": ts
                    })
                tcalls = d.get("tool_calls") or []
                for tc in tcalls:
                    if isinstance(tc, dict):
                        messages.append({
                            "role": "assistant",
                            "type": "tool_call",
                            "name": tc.get("name") or tc.get("tool_name") or "tool",
                            "arguments": json.dumps(tc.get("args") or tc.get("arguments") or {}, ensure_ascii=False),
                            "timestamp": ts
                        })
                txt = str(d.get("content") or "").strip()
                if txt and txt != "None":
                    messages.append({
                        "role": "assistant",
                        "type": "message",
                        "content": txt,
                        "timestamp": ts
                    })

    return meta, messages

def read_fts_fallback_messages(session_id: str) -> list:
    if not DB_PATH.exists():
        return []
    messages = []
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute(
            "SELECT role, content, timestamp FROM messages_fts WHERE session_id = ? ORDER BY rowid ASC",
            (session_id,)
        ).fetchall()
        conn.close()
        for role, content, ts in rows:
            messages.append({
                "role": role,
                "type": "message",
                "content": content,
                "timestamp": ts or ""
            })
    except Exception:
        pass
    return messages

def load_session_messages(sinfo: dict):
    sid = sinfo["session_id"]
    provider = sinfo["provider"]
    file_path = sinfo.get("file_path") or ""

    if provider == "antigravity":
        if os.path.exists(file_path):
            meta, messages = read_antigravity_session(file_path)
        else:
            meta, messages = {}, read_fts_fallback_messages(sid)
    elif provider == "codex":
        if file_path.startswith("sqlite://") or not os.path.exists(file_path):
            meta, messages = read_codex_sqlite_session(sid)
        else:
            meta, messages = read_codex_session(file_path)
            if not messages:
                meta, messages = read_codex_sqlite_session(sid)
    else:
        if os.path.exists(file_path):
            meta, messages = read_claude_session(file_path)
        else:
            meta, messages = {}, read_fts_fallback_messages(sid)

    return meta, messages

def render_markdown(session_id: str, include_thinking: bool = False, include_tools: bool = False, obsidian_format: bool = False) -> str:
    sinfo = get_session_info(session_id)
    if not sinfo:
        p = Path(session_id)
        if p.exists():
            if ".gemini/antigravity" in str(p):
                provider = "antigravity"
            elif ".claude" in str(p):
                provider = "claude"
            else:
                provider = "codex"
            sinfo = {
                "session_id": p.parents[2].name if provider == "antigravity" else p.stem,
                "provider": provider,
                "title": p.stem,
                "project_path": "",
                "file_path": str(p),
                "created_at": "",
                "updated_at": "",
                "message_count": 0,
            }
        else:
            return f"Session `{session_id}` not found in archive DB."

    file_path = sinfo["file_path"]
    provider = sinfo["provider"]
    meta, messages = load_session_messages(sinfo)

    title = (sinfo.get("title") or "Session").replace('"', "'")
    project = sinfo.get("project_path") or meta.get("cwd") or "Unknown"
    created = sinfo.get("created_at") or meta.get("timestamp") or "Unknown"
    updated = sinfo.get("updated_at") or created
    date_only = created[:10] if len(created) >= 10 else "2026-01-01"

    lines = []
    if obsidian_format:
        lines.append("---")
        lines.append(f'title: "{title}"')
        lines.append(f'session_id: "{sinfo["session_id"]}"')
        lines.append(f"provider: {provider}")
        lines.append(f'project: "{project}"')
        lines.append(f"date: {date_only}")
        lines.append(f'updated: "{updated}"')
        lines.append(f"message_count: {sinfo.get('message_count', len(messages))}")
        lines.append(f"tags: [ai-session, {provider}]")
        lines.append("---")
        lines.append("")
        lines.append(f"# {title}")
        lines.append("")
        lines.append(f"> **AI**: `{provider.upper()}` | **Date**: `{created[:19].replace('T', ' ')}` | **Project**: `{project}` | **Hub**: [[CHAT_ARCHIVE]] / [[SHARED_MEMORY]]")
        lines.append("")
        lines.append("---")
        lines.append("")
    else:
        lines.append(f"# {title}")
        lines.append("")
        lines.append(f"- **Provider**: `{provider.upper()}`")
        lines.append(f"- **Session ID**: `{sinfo['session_id']}`")
        lines.append(f"- **Project**: `{project}`")
        lines.append(f"- **Date**: `{created}`")
        lines.append(f"- **Source File**: `{file_path}`")
        lines.append("")
        lines.append("---")
        lines.append("")

    for msg in messages:
        role = msg["role"]
        mtype = msg["type"]
        ts = msg.get("timestamp", "")
        time_str = f" `[{ts[11:19]}]`" if len(ts) >= 19 else ""

        if mtype == "reasoning":
            if include_thinking:
                if obsidian_format:
                    quoted = "\n".join(f"> {l}" for l in msg["content"].splitlines())
                    lines.append(f"> [!thinking]- 🧠 Thinking{time_str}\n{quoted}\n")
                else:
                    lines.append(f"<details><summary>🧠 <b>思考プロセス (Thinking)</b>{time_str}</summary>\n\n{msg['content']}\n</details>\n")
        elif mtype == "tool_call":
            if include_tools:
                args_str = str(msg.get("arguments", ""))[:600]
                if obsidian_format:
                    quoted = "\n".join(f"> {l}" for l in args_str.splitlines())
                    lines.append(f"> [!tool]- 🛠️ Tool: `{msg.get('name')}`{time_str}\n> ```json\n{quoted}\n> ```\n")
                else:
                    lines.append(f"> 🛠️ **Tool**: `{msg.get('name')}`\n>\n> ```json\n> {args_str}\n> ```\n")
        elif mtype == "tool_output":
            if include_tools:
                if not obsidian_format:
                    lines.append(f"> 📥 **Result**:\n> ```\n> {msg['content']}\n> ```\n")
        elif role == "user":
            lines.append(f"### 👤 User{time_str}\n\n{msg['content']}\n")
        elif role == "assistant":
            lines.append(f"### 🤖 Assistant ({provider.upper()}){time_str}\n\n{msg['content']}\n")
        lines.append("")

    return "\n".join(lines)

def get_session_data(session_id: str):
    sinfo = get_session_info(session_id)
    if not sinfo:
        return None
    meta, messages = load_session_messages(sinfo)
    return {
        "info": sinfo,
        "meta": meta,
        "messages": messages
    }

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: reader.py <session_id> [--thinking] [--tools] [--obsidian]")
        sys.exit(1)
    sid = sys.argv[1]
    th = "--thinking" in sys.argv
    tl = "--tools" in sys.argv
    ob = "--obsidian" in sys.argv
    print(render_markdown(sid, include_thinking=th, include_tools=tl, obsidian_format=ob))
