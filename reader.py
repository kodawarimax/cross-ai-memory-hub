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

def render_markdown(session_id: str, include_thinking: bool = False, include_tools: bool = False) -> str:
    sinfo = get_session_info(session_id)
    if not sinfo:
        p = Path(session_id)
        if p.exists():
            provider = "claude" if ".claude" in str(p) else "codex"
            sinfo = {
                "session_id": p.stem,
                "provider": provider,
                "title": p.stem,
                "project_path": "",
                "file_path": str(p),
                "created_at": "",
                "updated_at": "",
            }
        else:
            return f"Session `{session_id}` not found in archive DB."

    file_path = sinfo["file_path"]
    if not os.path.exists(file_path):
        return f"Error: Session file `{file_path}` does not exist on disk."

    provider = sinfo["provider"]
    if provider == "codex":
        meta, messages = read_codex_session(file_path)
    else:
        meta, messages = read_claude_session(file_path)

    title = sinfo.get("title") or "Session"
    project = sinfo.get("project_path") or meta.get("cwd") or "Unknown"
    created = sinfo.get("created_at") or meta.get("timestamp") or "Unknown"

    lines = []
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
                lines.append(f"<details><summary>🧠 <b>思考プロセス (Thinking)</b>{time_str}</summary>\n\n{msg['content']}\n</details>\n")
        elif mtype == "tool_call":
            if include_tools:
                lines.append(f"> 🛠️ **Tool**: `{msg.get('name')}`\n>\n> ```json\n> {msg.get('arguments', '')}\n> ```\n")
        elif mtype == "tool_output":
            if include_tools:
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
    file_path = sinfo["file_path"]
    if not os.path.exists(file_path):
        return None
    provider = sinfo["provider"]
    if provider == "codex":
        meta, messages = read_codex_session(file_path)
    else:
        meta, messages = read_claude_session(file_path)
    return {
        "info": sinfo,
        "meta": meta,
        "messages": messages
    }

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: reader.py <session_id> [--thinking] [--tools]")
        sys.exit(1)
    sid = sys.argv[1]
    th = "--thinking" in sys.argv
    tl = "--tools" in sys.argv
    print(render_markdown(sid, include_thinking=th, include_tools=tl))
