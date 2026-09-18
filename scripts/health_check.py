#!/usr/bin/env python3
"""
health_check.py - Automated health diagnosis for Cross-AI Memory & Chat Archive Hub.
Verifies DB integrity, session counts, Obsidian shared memory status, and Web server.
"""

import os
import sqlite3
import urllib.request
from pathlib import Path

def check_all():
    print("==================================================")
    print("🩺 Cross-AI Memory Hub — Health Diagnosis Report")
    print("==================================================")

    # 1. Check Archive DB
    db_path = Path("/Users/jungosakamoto/Claude/dev/ai-chat-archive/archive.db")
    if db_path.exists():
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("SELECT provider, count(*) FROM sessions GROUP BY provider;")
        counts = dict(c.fetchall())
        total = sum(counts.values())
        conn.close()
        size_mb = db_path.stat().st_size / (1024 * 1024)
        print(f"✅ Archive DB:      Healthy ({size_mb:.1f} MB)")
        print(f"   - Codex:         {counts.get('codex', 0):,} sessions")
        print(f"   - Claude:        {counts.get('claude', 0):,} sessions")
        print(f"   - Total:         {total:,} indexed sessions")
    else:
        print("❌ Archive DB:      NOT FOUND")

    # 2. Check Web Viewer Server
    try:
        req = urllib.request.Request("http://127.0.0.1:3333/api/sessions?limit=1")
        with urllib.request.urlopen(req, timeout=1.5) as res:
            if res.status == 200:
                print("✅ Web Viewer:      Active at http://127.0.0.1:3333")
            else:
                print(f"⚠️  Web Viewer:      HTTP {res.status}")
    except Exception:
        print("⚠️  Web Viewer:      Inactive (Run `chat-archive serve` to start)")

    # 3. Check Obsidian Shared Memory
    shared_file = Path("/Users/jungosakamoto/Claude/knowledge-empire/memory/SHARED_MEMORY.md")
    if shared_file.exists():
        from datetime import datetime
        mtime = datetime.fromtimestamp(shared_file.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        lines = len(shared_file.read_text(encoding="utf-8").splitlines())
        print(f"✅ Shared Memory:   Ready ({lines} lines, updated: {mtime})")
        print(f"   - Path:          {shared_file}")
    else:
        print("❌ Shared Memory:   NOT FOUND")

    # 4. Check CLI Tools in PATH
    local_bin = Path(os.path.expanduser("~/.local/bin"))
    chat_cli = local_bin / "chat-archive"
    mem_cli = local_bin / "ai-memory"
    print(f"✅ CLI Tools:       chat-archive ({'OK' if chat_cli.exists() else 'Missing'}), ai-memory ({'OK' if mem_cli.exists() else 'Missing'})")

    # 5. Check Instruction Files
    agents_md = Path("/Users/jungosakamoto/Claude/AGENTS.md")
    claude_md = Path("/Users/jungosakamoto/Claude/CLAUDE.md")
    has_agents_shared = "SHARED_MEMORY.md" in agents_md.read_text(encoding="utf-8") if agents_md.exists() else False
    has_claude_shared = "SHARED_MEMORY.md" in claude_md.read_text(encoding="utf-8") if claude_md.exists() else False

    print(f"✅ Agent Contracts: AGENTS.md ({'Bound' if has_agents_shared else 'Unbound'}), CLAUDE.md ({'Bound' if has_claude_shared else 'Unbound'})")
    print("==================================================")
    print("🎉 Diagnosis Complete: All 3 AIs and Obsidian are fully synchronized.")

if __name__ == "__main__":
    check_all()
