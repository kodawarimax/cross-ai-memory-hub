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

HOME_DIR = Path.home()
_default_vault = HOME_DIR / "Claude" / "knowledge-empire" if (HOME_DIR / "Claude").exists() else HOME_DIR / "knowledge-empire"
VAULT_DIR = Path(os.environ.get("OBSIDIAN_VAULT", str(_default_vault))).expanduser()

def slugify(text: str) -> str:
    # simple slug for filename
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[^\w\s-]", "", text.lower())
    text = re.sub(r"[\s_-]+", "-", text).strip("-")
    return text[:40] if text else "note"

def record_knowledge(
    entry_type: str,
    title: str,
    content: str,
    links: list = None,
    author: str = "AI",
    area: str = "work",
    status: str = "active",
):
    if not VAULT_DIR.exists():
        raise RuntimeError(f"Vault directory does not exist: {VAULT_DIR}")

    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    datetime_str = now.strftime("%Y-%m-%d %H:%M:%S")

    # Sanitize content unless explicitly marked private
    clean_content = content.strip()
    if area.lower() != "private":
        try:
            from persona_extractor import sanitize_pii_and_secrets
            clean_content = sanitize_pii_and_secrets(clean_content)
        except Exception:
            pass

    # Default wikilinks if fewer than 2 provided
    if not links:
        links = []
    default_links = ["[[SHARED_MEMORY]]", "[[PERSONA_CORE]]"]
    for dl in default_links:
        if len(links) >= 2:
            break
        if dl not in links and dl not in clean_content:
            links.append(dl)

    slug = slugify(title)
    filename = f"{date_str}_{slug}.md"

    # Determine target directory (compatible with both knowledge-empire and obsidian-vault-setup)
    etype = entry_type.lower()
    type_dir_map = {
        "lesson": VAULT_DIR / "wiki" / "cases",
        "case": VAULT_DIR / "wiki" / "cases",
        "playbook": VAULT_DIR / "wiki" / "playbooks",
        "concept": VAULT_DIR / "wiki" / "concepts",
        "entity": VAULT_DIR / "wiki" / "entities",
        "strategy": VAULT_DIR / "wiki" / "strategies",
        "adr": VAULT_DIR / "wiki" / "playbooks" / "decisions",
        "project": VAULT_DIR / "crm",
        "resource": VAULT_DIR / "Resources",
        "note": VAULT_DIR / "Notes",
    }
    target_dir = type_dir_map.get(etype, VAULT_DIR / "wiki" / "cases")
    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = target_dir / filename

    links_str = " ".join(links)
    related_yaml = "\n".join(f'  - "{l}"' for l in links)
    clean_title = title.replace('"', "'")

    dataview_block = ""
    if etype == "playbook":
        dataview_block = """
## 関連ノート自動一覧 (Dataview)
```dataview
LIST
FROM #ATLAS_INDEX
WHERE contains(related, this.file.link)
SORT date DESC
```
"""

    # Format Obsidian Flavored Markdown document (Unified Schema v3.1)
    md_text = f"""---
title: "{clean_title}"
type: {etype}
status: {status}
area: {area}
date: {date_str}
updated: {date_str}
author: "{author}"
tags:
  - ATLAS_INDEX
  - ai-memory
  - chronicler
  - {etype}
related:
{related_yaml}
---

# {title}

> [!info] メタデータ
> **記録日時**: `{datetime_str}` | **記録者**: `{author}` | **領域**: `{area}` | **関連**: {links_str}

> [!abstract] 概要・本質 (Essence)
> {clean_content.replace(chr(10), chr(10) + "> ")}

## 関連正典・Wikilinks
{chr(10).join(f"- {l}" for l in links)}

> [!tip] 適用影響・今後のアクション
> この知見は全AI（Codex / Claude Code / Antigravity）の共通記憶（[[SHARED_MEMORY]]）および [[Knowledge_Atlas.base]] に反映されました。（`area: private` の場合はAI共通記憶から自動隔離されます）
{dataview_block}"""

    from persona_extractor import atomic_write_text
    atomic_write_text(target_file, md_text)

    # Update log.md
    log_file = VAULT_DIR / "log.md"
    if log_file.exists() and area.lower() != "private":
        log_entry = f"\n- **{datetime_str}** [{etype.upper()}] [[{target_file.relative_to(VAULT_DIR)}|{title}]] (by {author})\n  {clean_content[:100]}...\n"
        current_log = log_file.read_text(encoding="utf-8", errors="ignore")
        atomic_write_text(log_file, log_entry + current_log)

    # Trigger compiler to update SHARED_MEMORY.md
    from compiler import compile_shared_memory
    compile_shared_memory()

    return {
        "file_path": str(target_file),
        "relative_path": str(target_file.relative_to(VAULT_DIR)),
        "title": title,
        "type": etype,
        "area": area,
        "status": status,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--type", choices=["lesson", "case", "playbook", "concept", "entity", "strategy", "adr", "project", "resource", "note"], default="lesson")
    parser.add_argument("--title", required=True)
    parser.add_argument("--content", required=True)
    parser.add_argument("--links", nargs="*", default=[])
    parser.add_argument("--author", default="AI")
    parser.add_argument("--area", choices=["work", "personal", "private"], default="work")
    parser.add_argument("--status", choices=["active", "draft", "archived"], default="active")
    args = parser.parse_args()

    res = record_knowledge(args.type, args.title, args.content, args.links, args.author, args.area, args.status)
    print(f"Recorded to Obsidian: {res['file_path']}")
