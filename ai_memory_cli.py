#!/usr/bin/env python3
"""
ai-memory CLI - Cross-agent shared memory bridge powered by Obsidian (knowledge-empire).
Used by Codex, Claude Code, and Antigravity.
"""

import argparse
import sys
from pathlib import Path

VAULT_DIR = Path("/Users/jungosakamoto/Claude/knowledge-empire")
SHARED_MEMORY_FILE = VAULT_DIR / "memory" / "SHARED_MEMORY.md"

def cmd_get(args):
    if not SHARED_MEMORY_FILE.exists():
        from compiler import compile_shared_memory
        compile_shared_memory()

    content = SHARED_MEMORY_FILE.read_text(encoding="utf-8")

    if args.topic:
        query = args.topic.lower()
        sections = content.split("\n## ")
        matched = []
        for s in sections:
            if query in s.lower():
                matched.append("## " + s if not s.startswith("#") else s)

        if matched:
            print("\n\n".join(matched))
        else:
            print(f"No specific section found matching '{args.topic}'. Showing entire shared memory:\n")
            print(content)
    else:
        print(content)

def cmd_record(args):
    from recorder import record_knowledge
    try:
        res = record_knowledge(
            entry_type=args.type,
            title=args.title,
            content=args.content,
            links=args.links,
            author=args.author
        )
        print(f"✅ Successfully recorded to Obsidian Vault:")
        print(f"   Path:  {res['file_path']}")
        print(f"   Type:  {res['type'].upper()}")
        print(f"   Title: {res['title']}")
        print(f"   Auto-updated: log.md, SHARED_MEMORY.md")
    except Exception as e:
        print(f"❌ Error recording knowledge: {e}", file=sys.stderr)
        sys.exit(1)

def cmd_sync(args):
    from compiler import compile_shared_memory
    path = compile_shared_memory()
    print(f"✅ Synced and recompiled SHARED_MEMORY.md successfully!")
    print(f"   Path: {path}")

def cmd_status(args):
    if not VAULT_DIR.exists():
        print("❌ Obsidian Vault not found at:", VAULT_DIR)
        return

    import glob
    note_count = len(glob.glob(str(VAULT_DIR / "**" / "*.md"), recursive=True))
    shared_exists = SHARED_MEMORY_FILE.exists()
    mtime_str = "N/A"
    if shared_exists:
        from datetime import datetime
        mtime_str = datetime.fromtimestamp(SHARED_MEMORY_FILE.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")

    print(f"🏛️  Obsidian Knowledge Empire Hub Status:")
    print(f"   Vault Path:    {VAULT_DIR}")
    print(f"   Total Notes:   {note_count} markdown notes")
    print(f"   Shared Memory: {'✅ Ready' if shared_exists else '❌ Missing'}")
    print(f"   Last Updated:  {mtime_str}")
    print(f"\n🤖 Supported AI Agents:")
    print(f"   - Google Antigravity (Gemini): Enabled via skill & rules")
    print(f"   - Anthropic Claude Code:       Enabled via CLAUDE.md & shared_memory")
    print(f"   - OpenAI Codex CLI:            Enabled via AGENTS.md & /obsidian_save")

def main():
    parser = argparse.ArgumentParser(
        prog="ai-memory",
        description="Cross-agent shared memory bridge between Codex, Claude Code, Antigravity, and Obsidian."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # get
    p_get = subparsers.add_parser("get", help="Get shared memory context or specific topic")
    p_get.add_argument("topic", nargs="?", help="Optional topic/project keyword to filter")
    p_get.set_defaults(func=cmd_get)

    # record
    p_rec = subparsers.add_parser("record", help="Record a new decision, lesson, or project note into Obsidian")
    p_rec.add_argument("--type", choices=["lesson", "case", "playbook", "concept", "strategy", "project"], default="lesson")
    p_rec.add_argument("--title", required=True, help="Title of the note")
    p_rec.add_argument("--content", required=True, help="Body text / decision / lesson")
    p_rec.add_argument("--links", nargs="*", default=[], help="Optional wikilinks (e.g. [[坂本淳悟_正典]])")
    p_rec.add_argument("--author", default="AI", help="Author tag (Codex, Claude, Antigravity, etc.)")
    p_rec.set_defaults(func=cmd_record)

    # sync
    p_sync = subparsers.add_parser("sync", help="Recompile and sync SHARED_MEMORY.md from Vault")
    p_sync.set_defaults(func=cmd_sync)

    # status
    p_stat = subparsers.add_parser("status", help="Show Obsidian Vault and shared memory status")
    p_stat.set_defaults(func=cmd_status)

    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
