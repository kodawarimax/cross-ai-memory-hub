#!/usr/bin/env python3
"""
recorder.py - Records new knowledge, lessons, decisions, or project updates into Obsidian Vault (knowledge-empire).
Complies with knowledge-empire Chronicler rules (frontmatter, minimum 2 wikilinks, clean markdown).
"""

import os
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

VAULT_DIR = Path("/Users/jungosakamoto/Claude/knowledge-empire")

def slugify(text: str) -> str:
    # simple slug for filename
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[^\w\s-]", "", text.lower())
    text = re.sub(r"[\s_-]+", "-", text).strip("-")
    return text[:40] if text else "note"

def record_knowledge(entry_type: str, title: str, content: str, links: list = None, author: str = "AI"):
    if not VAULT_DIR.exists():
        raise RuntimeError(f"Vault directory does not exist: {VAULT_DIR}")

    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    datetime_str = now.strftime("%Y-%m-%d %H:%M:%S")

    # Default wikilinks if fewer than 2 provided
    if not links:
        links = []
    default_links = ["[[坂本淳悟_正典]]", "[[IT部_正典]]", "[[真の王]]"]
    for dl in default_links:
        if len(links) >= 2:
            break
        if dl not in links and dl not in content:
            links.append(dl)

    slug = slugify(title)
    filename = f"{date_str}_{slug}.md"

    # Determine target directory
    type_dir_map = {
        "lesson": VAULT_DIR / "wiki" / "cases",
        "case": VAULT_DIR / "wiki" / "cases",
        "playbook": VAULT_DIR / "wiki" / "playbooks",
        "concept": VAULT_DIR / "wiki" / "concepts",
        "strategy": VAULT_DIR / "wiki" / "strategies",
        "project": VAULT_DIR / "crm",
    }
    target_dir = type_dir_map.get(entry_type.lower(), VAULT_DIR / "wiki" / "cases")
    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = target_dir / filename

    # Prepare Wikilinks text block
    links_str = " ".join(links)

    # Format Markdown document
    md_text = f"""---
title: "{title}"
date: {date_str}
type: {entry_type}
tags: [{entry_type}, ai-memory, chronicler]
author: {author}
---

# {title}

> 記録日時: {datetime_str} | 記録者: {author} | 関連: {links_str}

## 概要・要約
{content.strip()}

## 関連正典・Wikilinks
- {chr(10).join(f"- {l}" for l in links)}

## 適用影響・今後のアクション
- この知見は全AI（Codex / Claude Code / Antigravity）の共通記憶に反映されました。
"""

    target_file.write_text(md_text, encoding="utf-8")

    # Update log.md
    log_file = VAULT_DIR / "log.md"
    if log_file.exists():
        log_entry = f"\n- **{datetime_str}** [{entry_type.upper()}] [[{target_file.relative_to(VAULT_DIR)}|{title}]] (by {author})\n  {content.strip()[:100]}...\n"
        current_log = log_file.read_text(encoding="utf-8", errors="ignore")
        log_file.write_text(log_entry + current_log, encoding="utf-8")

    # Trigger compiler to update SHARED_MEMORY.md
    from compiler import compile_shared_memory
    compile_shared_memory()

    return {
        "file_path": str(target_file),
        "relative_path": str(target_file.relative_to(VAULT_DIR)),
        "title": title,
        "type": entry_type
    }

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--type", choices=["lesson", "case", "playbook", "concept", "strategy", "project"], default="lesson")
    parser.add_argument("--title", required=True)
    parser.add_argument("--content", required=True)
    parser.add_argument("--links", nargs="*", default=[])
    parser.add_argument("--author", default="AI")
    args = parser.parse_args()

    res = record_knowledge(args.type, args.title, args.content, args.links, args.author)
    print(f"Recorded to Obsidian: {res['file_path']}")
