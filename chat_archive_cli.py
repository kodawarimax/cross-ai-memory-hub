#!/usr/bin/env python3
"""
chat-archive CLI - Cross-agent chat history search and reader for Codex and Claude.
"""

import argparse
import os
import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "archive.db"

def cmd_sync(args):
    from indexer import sync_indexes
    sync_indexes(verbose=True)

def cmd_list(args):
    if not DB_PATH.exists():
        print("Archive DB does not exist yet. Run `chat-archive sync` first.", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    query = "SELECT session_id, provider, title, project_path, updated_at, message_count FROM sessions"
    params = []
    if args.provider:
        query += " WHERE provider = ?"
        params.append(args.provider.lower())

    query += " ORDER BY updated_at DESC LIMIT ?"
    params.append(args.limit)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        print("No sessions found.")
        return

    print(f"{'PROVIDER':<8} {'UPDATED':<19} {'MESSAGES':<8} {'SESSION ID':<36} {'TITLE'}")
    print("-" * 110)
    for r in rows:
        sid, prov, title, proj, up, cnt = r
        up_str = up[:19].replace("T", " ") if up else "Unknown"
        title_str = (title or "Untitled")[:50]
        print(f"{prov.upper():<8} {up_str:<19} {cnt:<8} {sid:<36} {title_str}")

def cmd_search(args):
    if not DB_PATH.exists():
        print("Archive DB does not exist yet. Run `chat-archive sync` first.", file=sys.stderr)
        sys.exit(1)

    keyword = args.query.strip()
    if not keyword:
        print("Please provide a search keyword.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Search in FTS5
    fts_sql = """
    SELECT 
        session_id, 
        provider, 
        role,
        snippet(messages_fts, 3, '\033[1;33m', '\033[0m', '...', 30) as snip
    FROM messages_fts
    WHERE messages_fts MATCH ?
    """
    params = [keyword]
    if args.provider:
        fts_sql += " AND provider = ?"
        params.append(args.provider.lower())
    fts_sql += " LIMIT ?"
    params.append(args.limit * 4)

    rows = []
    try:
        cursor.execute(fts_sql, params)
        rows = cursor.fetchall()
    except sqlite3.OperationalError:
        # Retry with quoted keyword
        params[0] = f'"{keyword}"'
        try:
            cursor.execute(fts_sql, params)
            rows = cursor.fetchall()
        except Exception as e:
            print(f"Search error: {e}", file=sys.stderr)
            conn.close()
            return

    if not rows:
        print(f"No results found for '{keyword}'.")
        conn.close()
        return

    # Deduplicate by session_id while keeping best snippet
    session_snippets = {}
    for sid, prov, role, snip in rows:
        if sid not in session_snippets:
            session_snippets[sid] = {"provider": prov, "role": role, "snippet": snip}

    # Fetch session metadata
    sids = list(session_snippets.keys())[:args.limit]
    placeholders = ",".join("?" for _ in sids)
    cursor.execute(f"""
    SELECT session_id, provider, title, project_path, updated_at, message_count
    FROM sessions
    WHERE session_id IN ({placeholders})
    ORDER BY updated_at DESC
    """, sids)

    meta_rows = cursor.fetchall()
    conn.close()

    print(f"\n🔍 Found {len(meta_rows)} matching session(s) for '{keyword}':\n")
    for r in meta_rows:
        sid, prov, title, proj, up, cnt = r
        snip_info = session_snippets.get(sid, {})
        snip = snip_info.get("snippet", "").replace("\n", " ").strip()
        up_str = up[:19].replace("T", " ") if up else "Unknown"

        print(f"[{prov.upper()}] {title or 'Untitled'}")
        print(f"  Session ID: {sid}")
        print(f"  Updated:    {up_str} | Messages: {cnt} | Project: {proj or 'N/A'}")
        print(f"  Match:      {snip}")
        print("-" * 80)

def cmd_show(args):
    from reader import render_markdown, get_session_data
    if args.format == "json":
        import json
        data = get_session_data(args.session_id)
        if not data:
            print(f"Session '{args.session_id}' not found.", file=sys.stderr)
            sys.exit(1)
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        content = render_markdown(args.session_id, include_thinking=args.thinking, include_tools=args.tools)
        print(content)

def cmd_serve(args):
    from server import start_server
    start_server(port=args.port, host=args.host)

def main():
    parser = argparse.ArgumentParser(
        prog="chat-archive",
        description="Codex & Claude cross-agent chat history manager and viewer."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # list
    p_list = subparsers.add_parser("list", help="List recent chat sessions")
    p_list.add_argument("--provider", choices=["codex", "claude"], help="Filter by provider")
    p_list.add_argument("--limit", type=int, default=20, help="Number of sessions to show (default: 20)")
    p_list.set_defaults(func=cmd_list)

    # search
    p_search = subparsers.add_parser("search", help="Full-text search in chat history")
    p_search.add_argument("query", help="Keywords to search")
    p_search.add_argument("--provider", choices=["codex", "claude"], help="Filter by provider")
    p_search.add_argument("--limit", type=int, default=15, help="Number of results to show (default: 15)")
    p_search.set_defaults(func=cmd_search)

    # show
    p_show = subparsers.add_parser("show", help="Show full conversation of a session")
    p_show.add_argument("session_id", help="Session ID (UUID or partial ID)")
    p_show.add_argument("--thinking", action="store_true", help="Include assistant thinking process")
    p_show.add_argument("--tools", action="store_true", help="Include tool execution logs")
    p_show.add_argument("--format", choices=["md", "json"], default="md", help="Output format (default: md)")
    p_show.set_defaults(func=cmd_show)

    # sync
    p_sync = subparsers.add_parser("sync", help="Synchronize and update session index")
    p_sync.set_defaults(func=cmd_sync)

    # serve
    p_serve = subparsers.add_parser("serve", help="Start local web viewer server")
    p_serve.add_argument("--port", type=int, default=3333, help="Port to listen on (default: 3333)")
    p_serve.add_argument("--host", default="127.0.0.1", help="Host to bind (default: 127.0.0.1)")
    p_serve.set_defaults(func=cmd_serve)

    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
