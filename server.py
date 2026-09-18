#!/usr/bin/env python3
"""
server.py - Zero-dependency local web server for AI Chat Archive.
Serves a responsive, clean browser interface to search and read Codex/Claude chats.
"""

import json
import os
import sqlite3
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

from reader import get_session_data, render_markdown

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "archive.db"
WEB_DIR = BASE_DIR / "web"

class ArchiveHandler(BaseHTTPRequestHandler):
    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, text, content_type="text/plain; charset=utf-8", status=200):
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        # 1. API: List/Search sessions
        if path == "/api/sessions":
            provider = qs.get("provider", [None])[0]
            query = qs.get("q", [""])[0].strip()
            limit = int(qs.get("limit", [50])[0])

            if not DB_PATH.exists():
                self._send_json({"error": "Archive DB not ready"}, 500)
                return

            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()

            if query:
                # FTS search
                fts_sql = """
                SELECT session_id, snippet(messages_fts, 3, '<mark>', '</mark>', '...', 25)
                FROM messages_fts
                WHERE messages_fts MATCH ?
                """
                params = [query]
                if provider and provider.lower() != "all":
                    fts_sql += " AND provider = ?"
                    params.append(provider.lower())
                fts_sql += " LIMIT ?"
                params.append(limit * 3)

                try:
                    cursor.execute(fts_sql, params)
                    hits = cursor.fetchall()
                except sqlite3.OperationalError:
                    params[0] = f'"{query}"'
                    try:
                        cursor.execute(fts_sql, params)
                        hits = cursor.fetchall()
                    except Exception as e:
                        conn.close()
                        self._send_json({"error": str(e)}, 400)
                        return

                snip_map = {}
                for sid, snip in hits:
                    if sid not in snip_map:
                        snip_map[sid] = snip

                if not snip_map:
                    conn.close()
                    self._send_json({"sessions": []})
                    return

                sids = list(snip_map.keys())[:limit]
                placeholders = ",".join("?" for _ in sids)
                cursor.execute(f"""
                SELECT session_id, provider, title, project_path, updated_at, message_count, preview
                FROM sessions
                WHERE session_id IN ({placeholders})
                ORDER BY updated_at DESC
                """, sids)
                rows = cursor.fetchall()
                conn.close()

                result = []
                for r in rows:
                    sid, prov, title, proj, up, cnt, prev = r
                    result.append({
                        "session_id": sid,
                        "provider": prov,
                        "title": title or "Untitled",
                        "project_path": proj or "",
                        "updated_at": up,
                        "message_count": cnt,
                        "preview": prev or "",
                        "snippet": snip_map.get(sid, "")
                    })
                self._send_json({"sessions": result})
                return

            else:
                # Regular list
                sql = "SELECT session_id, provider, title, project_path, updated_at, message_count, preview FROM sessions"
                params = []
                if provider and provider.lower() != "all":
                    sql += " WHERE provider = ?"
                    params.append(provider.lower())
                sql += " ORDER BY updated_at DESC LIMIT ?"
                params.append(limit)

                cursor.execute(sql, params)
                rows = cursor.fetchall()
                conn.close()

                result = []
                for r in rows:
                    sid, prov, title, proj, up, cnt, prev = r
                    result.append({
                        "session_id": sid,
                        "provider": prov,
                        "title": title or "Untitled",
                        "project_path": proj or "",
                        "updated_at": up,
                        "message_count": cnt,
                        "preview": prev or "",
                        "snippet": ""
                    })
                self._send_json({"sessions": result})
                return

        # 2. API: Get Session Details
        if path.startswith("/api/session/"):
            subpath = path[len("/api/session/"):]
            if subpath.endswith("/markdown"):
                sid = subpath[:-len("/markdown")]
                th = qs.get("thinking", ["0"])[0] == "1"
                tl = qs.get("tools", ["0"])[0] == "1"
                md = render_markdown(sid, include_thinking=th, include_tools=tl)
                self._send_text(md, content_type="text/markdown; charset=utf-8")
                return
            else:
                sid = subpath
                data = get_session_data(sid)
                if not data:
                    self._send_json({"error": "Session not found"}, 404)
                    return
                self._send_json(data)
                return

        # 3. Static Web Files
        if path in ("/", "/index.html"):
            index_file = WEB_DIR / "index.html"
            if index_file.exists():
                with open(index_file, "r", encoding="utf-8") as f:
                    self._send_text(f.read(), content_type="text/html; charset=utf-8")
                return
            else:
                self._send_text("<h1>Web UI not found.</h1>", 404)
                return

        self._send_text("Not Found", 404)

def start_server(port: int = 3333, host: str = "127.0.0.1"):
    server_addr = (host, port)
    httpd = HTTPServer(server_addr, ArchiveHandler)
    url = f"http://{host}:{port}"
    print(f"\n=======================================================")
    print(f"🚀 AI Chat Archive Web Viewer is running at:")
    print(f"   👉 {url}")
    print(f"=======================================================\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
        httpd.server_close()

if __name__ == "__main__":
    start_server()
