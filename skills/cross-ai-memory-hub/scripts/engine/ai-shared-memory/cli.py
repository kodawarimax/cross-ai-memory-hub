#!/usr/bin/env python3
"""
ai-memory CLI - Cross-agent shared memory bridge powered by Obsidian (knowledge-empire).
Used by Codex, Claude Code, and Antigravity.
"""

import argparse
import glob
import os
import re
import sqlite3
import sys
from pathlib import Path

HOME_DIR = Path.home()
_default_vault = HOME_DIR / "Claude" / "knowledge-empire" if (HOME_DIR / "Claude").exists() else HOME_DIR / "knowledge-empire"
VAULT_DIR = Path(os.environ.get("OBSIDIAN_VAULT", str(_default_vault))).expanduser()
SHARED_MEMORY_FILE = VAULT_DIR / "memory" / "SHARED_MEMORY.md"
_default_archive_db = (HOME_DIR / "Claude" / "dev" / "ai-chat-archive" / "archive.db") if (HOME_DIR / "Claude" / "dev" / "ai-chat-archive").exists() else (VAULT_DIR / ".ai-hub" / "archive.db")
ARCHIVE_DB = Path(os.environ.get("AI_ARCHIVE_DB", str(_default_archive_db))).expanduser()
_proj_slug = "-" + str(HOME_DIR / "Claude").strip("/").replace("/", "-")
_root_slug = "-" + str(HOME_DIR).strip("/").replace("/", "-")
CLAUDE_PROJ_MEM = HOME_DIR / ".claude" / "projects" / _proj_slug / "memory"
CLAUDE_GLOB_MEM = HOME_DIR / ".claude" / "memory"
CODEX_MEM = HOME_DIR / ".codex" / "memories"


def search_markdown_dirs(query: str, limit: int = 12) -> list:
    q_low = query.lower()
    results = []
    search_roots = [
        ("Obsidian Wiki", VAULT_DIR / "wiki"),
        ("Obsidian CRM", VAULT_DIR / "crm"),
        ("Obsidian Memory", VAULT_DIR / "memory"),
        ("Claude Proj Memory", CLAUDE_PROJ_MEM),
        ("Claude Root Memory", HOME_DIR / ".claude" / "projects" / _root_slug / "memory"),
        ("Claude Global Memory", CLAUDE_GLOB_MEM),
        ("Codex Memory", CODEX_MEM),
        ("Claude Dots (Hasshin/Ittou)", HOME_DIR / "Claude" / "dots"),
        ("Codex TIL", HOME_DIR / "Codex" / "it-system-dev" / "references" / "til"),
    ]
    for label, root in search_roots:
        if not root.exists():
            continue
        for p in sorted(root.rglob("*.md"), key=lambda x: x.stat().st_mtime if x.exists() else 0, reverse=True):
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            idx = text.lower().find(q_low)
            if idx != -1 or q_low in p.name.lower():
                start = max(0, idx - 60) if idx != -1 else 0
                snippet = re.sub(r"\s+", " ", text[start:start + 220]).strip()
                results.append({
                    "source": label,
                    "path": str(p),
                    "name": p.name,
                    "snippet": snippet
                })
                if len(results) >= limit:
                    return results
    return results


def search_chat_archive_fts(query: str, limit: int = 8) -> list:
    if not ARCHIVE_DB.exists():
        return []
    hits = []
    try:
        conn = sqlite3.connect(f"file:{ARCHIVE_DB}?mode=ro", uri=True)
        sql = """
            SELECT m.session_id, m.provider, s.title, s.updated_at,
                   snippet(messages_fts, 3, '[', ']', '...', 24)
            FROM messages_fts m
            JOIN sessions s ON m.session_id = s.session_id
            WHERE messages_fts MATCH ?
            ORDER BY s.updated_at DESC
            LIMIT ?
        """
        try:
            rows = conn.execute(sql, (query, limit * 2)).fetchall()
        except sqlite3.OperationalError:
            rows = conn.execute(sql, (f'"{query}"', limit * 2)).fetchall()
        conn.close()
        seen = set()
        for sid, prov, title, u_at, snip in rows:
            if sid in seen:
                continue
            seen.add(sid)
            hits.append({
                "session_id": sid,
                "provider": prov,
                "title": title or sid[:8],
                "updated_at": (u_at or "")[:16].replace("T", " "),
                "snippet": re.sub(r"\s+", " ", snip or "").strip()
            })
            if len(hits) >= limit:
                break
    except Exception:
        pass
    return hits


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
            print("=== [1] SHARED_MEMORY.md Matches ===")
            print("\n\n".join(matched))
            print()

        md_hits = search_markdown_dirs(args.topic, limit=10)
        if md_hits:
            print(f"=== [2] Obsidian Vault & AI Silo Memory Matches ({len(md_hits)}) ===")
            for h in md_hits:
                print(f"- [{h['source']}] {h['name']} ({h['path']})\n  {h['snippet']}")
            print()

        chat_hits = search_chat_archive_fts(args.topic, limit=6)
        if chat_hits:
            print(f"=== [3] 3-AI Chat Archive FTS5 Matches ({len(chat_hits)}) ===")
            for c in chat_hits:
                print(f"- [{c['provider'].upper()} | {c['updated_at']}] {c['title']} (ID: {c['session_id']})\n  {c['snippet']}")
            print()

        if not matched and not md_hits and not chat_hits:
            print(f"No specific match found for '{args.topic}'. Showing core SHARED_MEMORY.md:\n")
            print(content)
    else:
        print(content)


def cmd_search(args):
    args.topic = args.query
    cmd_get(args)


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

    curated_count = len(glob.glob(str(VAULT_DIR / "wiki" / "**" / "*.md"), recursive=True))
    session_mirror_count = len(glob.glob(str(VAULT_DIR / "raw" / "sessions" / "**" / "*.md"), recursive=True))
    shared_exists = SHARED_MEMORY_FILE.exists()
    mtime_str = "N/A"
    if shared_exists:
        from datetime import datetime
        mtime_str = datetime.fromtimestamp(SHARED_MEMORY_FILE.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")

    print(f"🏛️  Obsidian Knowledge Empire Hub Status:")
    print(f"   Vault Path:           {VAULT_DIR}")
    print(f"   Curated Wiki Notes:   {curated_count:,} markdown notes")
    print(f"   Mirrored AI Sessions: {session_mirror_count:,} markdown notes (in raw/sessions/)")
    print(f"   Shared Memory:        {'✅ Ready' if shared_exists else '❌ Missing'} (Updated: {mtime_str})")
    from persona_extractor import PERSONA_CORE_FILE, VOICE_LOG_FILE, SNS_DRAFTS_FILE
    print(f"   Persona Core & SNS:   ✅ {PERSONA_CORE_FILE.name} / {VOICE_LOG_FILE.name} / {SNS_DRAFTS_FILE.name}")
    print(f"\n🤖 Connected AI Agents & Silos:")
    print(f"   - Google Antigravity (Gemini): Enabled (Transcripts + Skills + Rules)")
    print(f"   - Anthropic Claude Code:       Enabled (JSONL + Proj Memories + Global Memories)")
    print(f"   - OpenAI Codex CLI & ChatGPT:  Enabled (SQLite + JSONL + Rollout Memories + ChatGPT Project DNA)")


def cmd_persona(args):
    from persona_extractor import sync_persona_engine, PERSONA_CORE_FILE as core_file, VOICE_LOG_FILE as voice_file, SNS_DRAFTS_FILE as sns_file

    if args.mode == "sync" or not voice_file.exists() or not sns_file.exists():
        sync_persona_engine(verbose=True)
        if args.mode == "sync":
            return

    target = core_file
    if args.mode == "voice":
        target = voice_file
    elif args.mode == "sns":
        target = sns_file

    if target.exists():
        print(target.read_text(encoding="utf-8"))
    else:
        print(f"❌ File not found: {target}")


def cmd_onboard(args):
    import subprocess
    coach_script = Path(__file__).resolve().parent / "onboarding_coach.py"
    cmd = [sys.executable, str(coach_script)]
    if args.diagnose:
        cmd.append("--diagnose")
    if args.interview:
        cmd.append("--interview")
    if args.open_chatgpt:
        cmd.append("--open-chatgpt")
    if args.seed_philosophy:
        cmd.extend(["--seed-philosophy", args.seed_philosophy])
    if args.seed_reaction:
        cmd.extend(["--seed-reaction", args.seed_reaction])
    if args.seed_action:
        cmd.extend(["--seed-action", args.seed_action])
    if args.seed_ng:
        cmd.extend(["--seed-ng", args.seed_ng])
    subprocess.run(cmd)


def cmd_contradictions(args):
    import subprocess
    resolver_script = Path(__file__).resolve().parent / "contradiction_resolver.py"
    cmd = [sys.executable, str(resolver_script)]
    if args.scan:
        cmd.append("--scan")
    if args.daily_cron:
        cmd.append("--daily-cron")
    if args.ask:
        cmd.append("--ask")
    if args.resolve:
        cmd.extend(["--resolve", args.resolve])
    if args.choice:
        cmd.extend(["--choice", args.choice])
    if args.note:
        cmd.extend(["--note", args.note])
    subprocess.run(cmd)


def main():
    parser = argparse.ArgumentParser(
        prog="ai-memory",
        description="Cross-agent shared memory bridge between Codex, Claude Code, Antigravity, ChatGPT, and Obsidian."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # get
    p_get = subparsers.add_parser("get", help="Get shared memory context or search specific topic across all vaults")
    p_get.add_argument("topic", nargs="?", help="Optional topic/project keyword to filter across all memories")
    p_get.set_defaults(func=cmd_get)

    # search
    p_search = subparsers.add_parser("search", help="Full search across Obsidian Vault, AI memory silos, and 3-AI chat archive")
    p_search.add_argument("query", help="Keyword to search")
    p_search.set_defaults(func=cmd_search)

    # persona
    p_pers = subparsers.add_parser("persona", help="Access Persona Core, Voice Log, or SNS Ready Drafts")
    p_pers.add_argument("--mode", choices=["core", "voice", "sns", "sync"], default="core", help="View core lexicon, voice log, SNS drafts, or resync")
    p_pers.set_defaults(func=cmd_persona)

    # record
    p_rec = subparsers.add_parser("record", help="Record a new decision, lesson, or project note into Obsidian")
    p_rec.add_argument("--type", choices=["lesson", "case", "playbook", "concept", "strategy", "project"], default="lesson")
    p_rec.add_argument("--title", required=True, help="Title of the note")
    p_rec.add_argument("--content", required=True, help="Body text / decision / lesson")
    p_rec.add_argument("--links", nargs="*", default=[], help="Optional wikilinks (e.g. [[PERSONA_CORE]])")
    p_rec.add_argument("--author", default="AI", help="Author tag (Codex, Claude, Antigravity, etc.)")
    p_rec.set_defaults(func=cmd_record)

    # sync
    p_sync = subparsers.add_parser("sync", help="Recompile and sync SHARED_MEMORY.md from Vault")
    p_sync.set_defaults(func=cmd_sync)

    # status
    p_stat = subparsers.add_parser("status", help="Show Obsidian Vault and shared memory status")
    p_stat.set_defaults(func=cmd_status)

    # onboard (built-in constraint coach & persona interviewer)
    p_onb = subparsers.add_parser("onboard", help="Built-in Onboarding Coach: diagnose constraints, run 5-min Persona Seed interview, or import ChatGPT exports")
    p_onb.add_argument("--diagnose", action="store_true", help="Diagnose constraints and show actionable guidance")
    p_onb.add_argument("--interview", action="store_true", help="Run interactive 5-question Persona Seed interview")
    p_onb.add_argument("--open-chatgpt", action="store_true", help="Open ChatGPT export settings in browser")
    p_onb.add_argument("--seed-philosophy", help="Save Philosophy (使う言葉) seed directly from chat")
    p_onb.add_argument("--seed-reaction", help="Save Reaction (反応する言葉) seed directly from chat")
    p_onb.add_argument("--seed-action", help="Save Action (行動する言葉) seed directly from chat")
    p_onb.add_argument("--seed-ng", default="", help="Save NG words / style correction seed directly from chat")
    p_onb.set_defaults(func=cmd_onboard)

    # contradictions (daily semantic contradiction detector & user resolution engine)
    p_con = subparsers.add_parser("contradictions", help="Detect semantic contradictions across memories/rules and ask user to resolve them")
    p_con.add_argument("--scan", action="store_true", help="Scan for semantic contradictions and update CONTRADICTION_INBOX.md")
    p_con.add_argument("--daily-cron", action="store_true", help="Run daily scheduled check with notification if contradictions exist")
    p_con.add_argument("--ask", action="store_true", help="Run interactive Q&A to resolve pending contradictions")
    p_con.add_argument("--resolve", metavar="ID", help="Resolve a specific contradiction by ID (e.g. contra-1a2b3c4d)")
    p_con.add_argument("--choice", choices=["A", "B", "BOTH", "DISMISS", "a", "b", "both", "dismiss"], help="Which rule is correct (A, B, BOTH, or DISMISS)")
    p_con.add_argument("--note", default="", help="Optional context split note when resolving")
    p_con.set_defaults(func=cmd_contradictions)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
