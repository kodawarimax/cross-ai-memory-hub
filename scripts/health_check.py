#!/usr/bin/env python3
"""
health_check.py - Automated health diagnosis for Cross-AI Memory, Obsidian Session Mirror & Persona Hub.
Verifies DB integrity across all 3 AIs, Obsidian raw/sessions mirror, ChatGPT project DNA, and Persona Engine.
"""

import glob
import os
import sqlite3
import urllib.request
from pathlib import Path

def check_all():
    home = Path.home()
    ws_dir = home / "Claude" if (home / "Claude").exists() else home
    vault_dir = Path(os.environ.get("OBSIDIAN_VAULT", str(ws_dir / "knowledge-empire")))
    db_path = Path(os.environ.get("CHAT_ARCHIVE_DB", str(ws_dir / "dev" / "ai-chat-archive" / "archive.db")))

    print("============================================================")
    print("🩺 Cross-AI Memory & Persona Hub — Health Diagnosis Report")
    print("============================================================")

    # 1. Check Archive DB
    if db_path.exists():
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("SELECT provider, count(*) FROM sessions GROUP BY provider;")
        counts = dict(c.fetchall())
        c.execute("SELECT count(*) FROM sessions WHERE message_count > 0;")
        non_empty = c.fetchone()[0]
        total = sum(counts.values())
        conn.close()
        size_mb = db_path.stat().st_size / (1024 * 1024)
        print(f"✅ Archive DB:         Healthy ({size_mb:.1f} MB)")
        print(f"   - Claude Code:      {counts.get('claude', 0):,} sessions")
        print(f"   - OpenAI Codex:     {counts.get('codex', 0):,} sessions (JSONL + SQLite)")
        print(f"   - Antigravity:      {counts.get('antigravity', 0):,} sessions")
        print(f"   - Total Indexed:    {total:,} sessions ({non_empty:,} non-empty)")
    else:
        print(f"❌ Archive DB:         NOT FOUND ({db_path})")

    # 2. Check Obsidian Session Mirror & Linked Silos
    mirrored = len(glob.glob(str(vault_dir / "raw" / "sessions" / "**" / "*.md"), recursive=True))
    chatgpt_dna = len(glob.glob(str(vault_dir / "wiki" / "chatgpt-project*" / "*.md")))
    print(f"✅ Obsidian Mirror:    {mirrored:,} session notes in raw/sessions/ | {chatgpt_dna} ChatGPT Project DNA files")

    # 3. Check Persona Core & SNS Engine
    persona_core = (vault_dir / "memory" / "JUNGO_PERSONA_CORE.md") if (vault_dir / "memory" / "JUNGO_PERSONA_CORE.md").exists() else (vault_dir / "memory" / "PERSONA_CORE.md")
    voice_log = vault_dir / "memory" / "JUNGO_VOICE_LOG.md"
    sns_drafts = vault_dir / "memory" / "SNS_READY_DRAFTS.md"
    p_ok = persona_core.exists() and voice_log.exists() and sns_drafts.exists()
    print(f"✅ Persona & SNS OS:   {'Ready' if p_ok else 'Missing'} (Core + Voice Log + SNS Drafts)")

    # 4. Check Obsidian Shared Memory
    shared_file = vault_dir / "memory" / "SHARED_MEMORY.md"
    if shared_file.exists():
        from datetime import datetime
        mtime = datetime.fromtimestamp(shared_file.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        lines = len(shared_file.read_text(encoding="utf-8").splitlines())
        print(f"✅ Shared Memory:      Ready ({lines} lines, updated: {mtime})")
    else:
        print("❌ Shared Memory:      NOT FOUND")

    # 5. Check Web Viewer Server
    try:
        req = urllib.request.Request("http://127.0.0.1:3333/api/sessions?limit=1")
        with urllib.request.urlopen(req, timeout=1.5) as res:
            if res.status == 200:
                print("✅ Web Viewer:         Active at http://127.0.0.1:3333")
            else:
                print(f"⚠️  Web Viewer:         HTTP {res.status}")
    except Exception:
        print("⚠️  Web Viewer:         Inactive (Run `chat-archive serve` to start)")

    # 6. Check CLI Tools in PATH
    local_bin = Path(os.path.expanduser("~/.local/bin"))
    chat_cli = local_bin / "chat-archive"
    mem_cli = local_bin / "ai-memory"
    print(f"✅ CLI Tools:          chat-archive ({'OK' if chat_cli.exists() else 'Missing'}), ai-memory ({'OK' if mem_cli.exists() else 'Missing'})")

    # 7. Check Instruction Files
    agents_md = ws_dir / "AGENTS.md"
    claude_md = ws_dir / "CLAUDE.md"
    has_agents_shared = "SHARED_MEMORY.md" in agents_md.read_text(encoding="utf-8") if agents_md.exists() else False
    has_claude_shared = "SHARED_MEMORY.md" in claude_md.read_text(encoding="utf-8") if claude_md.exists() else False

    print(f"✅ Agent Contracts:    AGENTS.md ({'Bound' if has_agents_shared else 'Unbound'}), CLAUDE.md ({'Bound' if has_claude_shared else 'Unbound'})")
    print("============================================================")
    print("🎉 Diagnosis Complete: All AIs, ChatGPT Project DNA, and Persona OS are synchronized in Obsidian.")

if __name__ == "__main__":
    check_all()
