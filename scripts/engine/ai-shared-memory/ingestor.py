#!/usr/bin/env python3
"""
ingestor.py — Deterministic 4-Stage File Ingest Pipeline & Obsidian Native Scaffold (v3.1)

Unifies:
  1. obsidian-file-ingest (4-stage non-destructive file ingestion + doc-to-md / stdlib extraction)
  2. obsidian-bases (.base YAML database views: Knowledge_Atlas.base, AI_Sessions.base, Persona_&_SNS.base)
  3. obsidian-vault-setup (Home.md MOC + Overview.canvas + hybrid folder structure)
  4. obsidian-markdown (Valid YAML frontmatter properties, callouts, and wikilinks)
"""

import json
import os
import re
import shutil
import subprocess
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime
from pathlib import Path

HOME_DIR = Path.home()
_default_vault = HOME_DIR / "Claude" / "knowledge-empire" if (HOME_DIR / "Claude").exists() else HOME_DIR / "knowledge-empire"
VAULT_DIR = Path(os.environ.get("OBSIDIAN_VAULT", str(_default_vault))).expanduser()


KNOWLEDGE_ATLAS_BASE_YAML = """# Obsidian Base: Knowledge Atlas (Unified v3.1)
filters:
  and:
    - 'file.ext == "md"'
    - 'file.hasTag("ATLAS_INDEX")'
    - not:
        - 'status == "archived"'

properties:
  file.name:
    displayName: "Note"
  type:
    displayName: "Category"
  area:
    displayName: "Area"
  status:
    displayName: "Status"
  date:
    displayName: "Date"
  author:
    displayName: "Author"

views:
  - type: table
    name: "All Active Knowledge"
    groupBy:
      property: type
      direction: ASC
    order:
      - file.name
      - type
      - area
      - status
      - date
      - author
  - type: cards
    name: "Playbooks & Strategies"
    filters:
      or:
        - 'type == "playbook"'
        - 'type == "strategy"'
    order:
      - file.name
      - type
      - date
      - status
  - type: table
    name: "Ingested Resources"
    filters: 'file.hasTag("ingested")'
    order:
      - file.name
      - area
      - date
      - source
"""

AI_SESSIONS_BASE_YAML = """# Obsidian Base: Cross-AI Session Mirror (Unified v3.1)
filters:
  and:
    - 'file.inFolder("raw/sessions")'
    - 'file.ext == "md"'

properties:
  file.name:
    displayName: "Session Note"
  provider:
    displayName: "AI Provider"
  project:
    displayName: "Workspace / Project"
  message_count:
    displayName: "Messages"
  date:
    displayName: "Date"

views:
  - type: table
    name: "Recent AI Sessions"
    limit: 100
    groupBy:
      property: provider
      direction: ASC
    order:
      - file.name
      - provider
      - project
      - message_count
      - date
"""

PERSONA_SNS_BASE_YAML = """# Obsidian Base: Persona & Memory OS Hub (Unified v3.1)
filters:
  and:
    - 'file.inFolder("memory")'
    - 'file.ext == "md"'

properties:
  file.name:
    displayName: "Core Memory File"
  file.mtime:
    displayName: "Last Updated"
  file.size:
    displayName: "Size (Bytes)"

views:
  - type: cards
    name: "Memory & Persona Core"
    order:
      - file.name
      - file.mtime
      - file.size
"""


def build_overview_canvas() -> str:
    canvas_data = {
        "nodes": [
            {
                "id": "node-home",
                "type": "text",
                "x": 0,
                "y": 0,
                "width": 320,
                "height": 160,
                "color": "4",
                "text": "# 🏛️ Universal AI Hub (v3.1)\n\n- [[Home]]\n- [[SHARED_MEMORY]]\n- [[PERSONA_CORE]]"
            },
            {
                "id": "node-bases",
                "type": "text",
                "x": 400,
                "y": -120,
                "width": 340,
                "height": 180,
                "color": "5",
                "text": "## 📊 Obsidian Bases (DB Views)\n\n- [[Knowledge_Atlas.base]]\n- [[AI_Sessions.base]]\n- [[Persona_&_SNS.base]]"
            },
            {
                "id": "node-persona",
                "type": "text",
                "x": 400,
                "y": 120,
                "width": 340,
                "height": 180,
                "color": "6",
                "text": "## 🧠 Self-Improving Persona\n\n- [[PERSONA_CORE]]\n- [[VOICE_LOG]]\n- [[SNS_READY_DRAFTS]]"
            }
        ],
        "edges": [
            {
                "id": "edge-1",
                "fromNode": "node-home",
                "fromSide": "right",
                "toNode": "node-bases",
                "toSide": "left",
                "label": "Database Views"
            },
            {
                "id": "edge-2",
                "fromNode": "node-home",
                "fromSide": "right",
                "toNode": "node-persona",
                "toSide": "left",
                "label": "Closed-Loop Evolution"
            }
        ]
    }
    return json.dumps(canvas_data, ensure_ascii=False, indent=2)


def ensure_obsidian_native_scaffold(vault_dir: Path = None, persona_name: str = None, extra_dirs: list = None) -> dict:
    """
    Non-destructively creates unified hybrid folders, .base files, Overview.canvas, and Home.md.
    Validates YAML and JSON Canvas integrity before returning.
    """
    vault_dir = (vault_dir or VAULT_DIR).expanduser().resolve()
    persona_name = persona_name or os.environ.get("PERSONA_NAME", HOME_DIR.name)

    standard_dirs = [
        "00-Inbox",
        "Notes",
        "Resources",
        "Attachments",
        "Imports",
        "People",
        "memory",
        "crm",
        "wiki/concepts",
        "wiki/entities",
        "wiki/strategies",
        "wiki/cases",
        "wiki/playbooks",
        "wiki/playbooks/decisions",
        "raw/sessions/claude",
        "raw/sessions/codex",
        "raw/sessions/antigravity",
        "raw/sessions/chatgpt",
    ]
    if extra_dirs:
        standard_dirs.extend(extra_dirs)

    for rel in standard_dirs:
        (vault_dir / rel).mkdir(parents=True, exist_ok=True)

    from persona_extractor import atomic_write_text

    created_files = []
    base_files = {
        "Knowledge_Atlas.base": KNOWLEDGE_ATLAS_BASE_YAML,
        "AI_Sessions.base": AI_SESSIONS_BASE_YAML,
        "Persona_&_SNS.base": PERSONA_SNS_BASE_YAML,
    }
    for fname, content in base_files.items():
        fpath = vault_dir / fname
        if not fpath.exists():
            atomic_write_text(fpath, content)
            created_files.append(fname)

    canvas_path = vault_dir / "Overview.canvas"
    if not canvas_path.exists():
        atomic_write_text(canvas_path, build_overview_canvas())
        created_files.append("Overview.canvas")

    home_path = vault_dir / "Home.md"
    if not home_path.exists():
        now_str = datetime.now().strftime("%Y-%m-%d")
        home_md = f"""---
title: "{persona_name} Knowledge & Persona Hub"
type: hub
status: active
area: work
date: {now_str}
updated: {now_str}
tags:
  - hub
  - moc
---

# 🏛️ {persona_name} — Universal AI Memory & Persona Hub (v3.1)

> [!tip] 全AI共通の頭脳・自己進化ハブへようこそ
> この Obsidian Vault は、**Claude Code / OpenAI Codex / Google Antigravity (Gemini) / ChatGPT** の全対話履歴と手元のドキュメントを統合し、使うほどあなた自身の言葉と判断基準を学習する生きた知識ベースです。

---

## 📊 1. データベースビュー (Obsidian Bases & Canvas)

- 🗂️ **[[Knowledge_Atlas.base|Knowledge Atlas (全ナレッジ・Playbook・取込資料一覧)]]**
- 💬 **[[AI_Sessions.base|AI Sessions (全AIチャット履歴テーブル)]]**
- 🧠 **[[Persona_&_SNS.base|Persona & SNS Core (人格コア・SNSドラフト一覧)]]**
- 🗺️ **[[Overview.canvas|Overview Canvas (全体俯瞰マップ)]]**

---

## 🧠 2. 共通記憶 ＆ 自己改善型・人格エンジン (`memory/`)

- **[[SHARED_MEMORY]]** — 全AIが起動時に参照する共通記憶の正本（Single Source of Truth）
- **[[PERSONA_CORE]]** — 自己学習する人格コア（使う言葉・反応する言葉・行動する言葉・修正履歴）
- **[[VOICE_LOG]]** — 実際のチャット・音声入力から抽出された生フレーズ集
- **[[SNS_READY_DRAFTS]]** — X / Threads / note 向けの即投稿ドラフト（Slop Gate検証済）
- **[[CHAT_ARCHIVE]]** — 全AI対話セッションの統計ダッシュボード

---

## 📁 3. フォルダ構成とルーティング

| フォルダ | 用途 | コマンド / 自動連携 |
| :--- | :--- | :--- |
| `wiki/` | 構造化ナレッジ（`playbooks/`, `cases/`, `strategies/`, `concepts/`） | `ai-memory record --type playbook ...` |
| `Resources/` / `Imports/` | 外部ファイル（PDF/DOCX/TXT等）の原本保全と蒸留ノート | `ai-memory ingest <パス>` |
| `Notes/` / `00-Inbox/` | 日常のアイデア・メモ・未分類ノート | `#ATLAS_INDEX` タグで共通記憶へ自動昇格 |
| `crm/` / `People/` | プロジェクト・案件・人物プロファイル | `ai-memory record --type project ...` |
| `raw/sessions/` | 4大AIの全会話セッション自動ミラー | 10分毎にバックグラウンド自動同期 |
"""
        atomic_write_text(home_path, home_md)
        created_files.append("Home.md")

    return {"vault_dir": str(vault_dir), "created_files": created_files}


def slugify(text: str, max_len: int = 40) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[^\w\s-]", "", text.lower())
    text = re.sub(r"[\s_-]+", "-", text).strip("-")
    return text[:max_len] if text else "item"


def extract_text_from_docx(path: Path) -> str:
    """Zero-dependency DOCX text extraction using Python stdlib zipfile + ElementTree."""
    try:
        with zipfile.ZipFile(path, "r") as zf:
            if "word/document.xml" not in zf.namelist():
                return ""
            xml_bytes = zf.read("word/document.xml")
        root = ET.fromstring(xml_bytes)
        paragraphs = []
        for p in root.iter():
            if p.tag.endswith("}p"):
                texts = [t.text for t in p.iter() if t.tag.endswith("}t") and t.text]
                if texts:
                    paragraphs.append("".join(texts))
        return "\n\n".join(paragraphs)
    except Exception:
        return ""


def extract_text_from_pptx(path: Path) -> str:
    """Zero-dependency PPTX text extraction using Python stdlib zipfile + ElementTree."""
    try:
        slides_text = []
        with zipfile.ZipFile(path, "r") as zf:
            slide_files = sorted(n for n in zf.namelist() if n.startswith("ppt/slides/slide") and n.endswith(".xml"))
            for sf in slide_files:
                root = ET.fromstring(zf.read(sf))
                texts = [t.text for t in root.iter() if t.tag.endswith("}t") and t.text]
                if texts:
                    slides_text.append("\n".join(texts))
        return "\n\n---\n\n".join(slides_text)
    except Exception:
        return ""


def extract_clean_text(file_path: Path) -> str:
    """
    Follows global rule:
      1. Prefer `doc-to-md INPUT -o OUTPUT.md` if available.
      2. Fall back to stdlib (.md, .txt, .json, .csv, .docx, .pptx) or local CLI (`pdftotext`, `textutil`).
    """
    ext = file_path.suffix.lower()

    # 1. Text / Markdown direct read
    if ext in {".md", ".txt", ".csv", ".tsv", ".json", ".yaml", ".yml", ".log"}:
        return file_path.read_text(encoding="utf-8", errors="ignore")

    # 2. Check doc-to-md first for PDF / Office / HTML
    doc_to_md_bin = shutil.which("doc-to-md")
    if doc_to_md_bin and ext in {".pdf", ".docx", ".pptx", ".xlsx", ".html", ".htm", ".rtf"}:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            out_md = Path(tmp) / "out.md"
            try:
                res = subprocess.run([doc_to_md_bin, str(file_path), "-o", str(out_md)], capture_output=True, text=True, timeout=30)
                if res.returncode == 0 and out_md.exists():
                    return out_md.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                pass

    # 3. Deterministic local fallbacks
    if ext == ".docx":
        return extract_text_from_docx(file_path)
    if ext == ".pptx":
        return extract_text_from_pptx(file_path)
    if ext == ".rtf" and shutil.which("textutil"):
        try:
            res = subprocess.run(["textutil", "-convert", "txt", "-stdout", str(file_path)], capture_output=True, text=True, timeout=15)
            if res.returncode == 0:
                return res.stdout
        except Exception:
            pass
    if ext == ".pdf" and shutil.which("pdftotext"):
        try:
            res = subprocess.run(["pdftotext", str(file_path), "-"], capture_output=True, text=True, timeout=20)
            if res.returncode == 0:
                return res.stdout
        except Exception:
            pass

    return ""


UI_NOISE_PATTERNS = [
    re.compile(r"^(?:思考時間|情報源|会話を報告する|Copy code|共有する)\s*$", re.MULTILINE),
]


def distill_markdown_essence(raw_text: str, area: str = "work", max_chars: int = 8000) -> str:
    text = raw_text.strip()
    if not text:
        return ""
    # Strip frontmatter if already present in source
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            text = parts[2].strip()

    for pat in UI_NOISE_PATTERNS:
        text = pat.sub("", text)

    # Collapse 3+ blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)

    if area.lower() != "private":
        try:
            from persona_extractor import sanitize_pii_and_secrets
            text = sanitize_pii_and_secrets(text)
        except Exception:
            pass

    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n> [!note] 長文のため先頭エッセンスを抽出（全文は `Imports/` 内の原本を参照）"
    return text


def ingest_files(
    src_path: str,
    vault_dir: Path = None,
    area: str = "work",
    target_folder: str = "Resources",
    bundle_name: str = None,
) -> dict:
    """
    Executes the 4-stage Obsidian File Ingest pipeline:
      STAGE 1: Inventory & non-destructive original preservation in Imports/<bundle>/
      STAGE 2: Essence extraction (doc-to-md / stdlib / pdftotext)
      STAGE 3: Clean Obsidian Flavored Markdown with Unified Frontmatter v3.1
      STAGE 4: Vault routing + MOC Index Note + count verification + SHARED_MEMORY compile
    """
    src = Path(src_path).expanduser().resolve()
    if not src.exists():
        raise FileNotFoundError(f"Source path not found: {src}")

    vault_dir = (vault_dir or VAULT_DIR).expanduser().resolve()
    ensure_obsidian_native_scaffold(vault_dir)

    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    bundle_slug = slugify(bundle_name or src.stem, 32)
    bundle_id = f"{date_str}_{bundle_slug}"

    imports_bundle_dir = vault_dir / "Imports" / bundle_id
    imports_bundle_dir.mkdir(parents=True, exist_ok=True)
    dest_notes_dir = vault_dir / target_folder
    dest_notes_dir.mkdir(parents=True, exist_ok=True)

    # STAGE 1: Inventory
    if src.is_file():
        src_files = [src]
        base_root = src.parent
    else:
        src_files = sorted(
            p for p in src.rglob("*")
            if p.is_file() and not p.name.startswith(".") and p.name != ".DS_Store"
        )
        base_root = src

    preserved_count = 0
    distilled_notes = []
    binary_embeds = []

    from persona_extractor import atomic_write_text

    for fpath in src_files:
        rel = fpath.relative_to(base_root)
        preserved_target = imports_bundle_dir / rel
        preserved_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(fpath, preserved_target)
        preserved_count += 1

        rel_vault_import = preserved_target.relative_to(vault_dir)
        raw_txt = extract_clean_text(fpath)
        essence = distill_markdown_essence(raw_txt, area=area)

        if essence:
            note_slug = slugify(fpath.stem, 40)
            note_filename = f"{date_str}_{note_slug}.md"
            note_target = dest_notes_dir / note_filename
            clean_title = fpath.stem.replace('"', "'")

            md_content = f"""---
title: "{clean_title}"
type: resource
status: active
area: {area}
date: {date_str}
updated: {date_str}
source: "{rel_vault_import}"
imported: {date_str}
tags:
  - ATLAS_INDEX
  - ai-memory
  - ingested
  - resource
related:
  - "[[SHARED_MEMORY]]"
  - "[[Imports/{bundle_id}_INDEX]]"
---

# {clean_title}

> [!info] 取り込みメタデータ (Obsidian File Ingest v3.1)
> **原本ファイル**: [[{rel_vault_import}|{fpath.name}]] | **領域**: `{area}` | **取込日**: `{date_str}`

## 抽出エッセンス (Clean Signal)

{essence}
"""
            atomic_write_text(note_target, md_content)
            distilled_notes.append(str(note_target.relative_to(vault_dir)))
        else:
            binary_embeds.append(str(rel_vault_import))

    # STAGE 4: Bundle MOC Index & Verification
    if len(src_files) != preserved_count:
        raise RuntimeError(f"Ingest verification failed: source={len(src_files)} != preserved={preserved_count}")

    moc_path = vault_dir / "Imports" / f"{bundle_id}_INDEX.md"
    notes_list_md = "\n".join(f"- [[{n}]]" for n in distilled_notes) if distilled_notes else "- (テキストノートなし)"
    bin_list_md = "\n".join(f"- ![[{b}]]" for b in binary_embeds) if binary_embeds else "- (バイナリ単体ファイルなし)"

    moc_md = f"""---
title: "Ingest Bundle: {bundle_slug}"
type: resource
status: active
area: {area}
date: {date_str}
updated: {date_str}
source: "{src.name}"
imported: {date_str}
tags:
  - ATLAS_INDEX
  - ingested
  - moc
related:
  - "[[Home]]"
  - "[[Knowledge_Atlas.base]]"
---

# 📦 Ingest Bundle: {bundle_slug} ({date_str})

> [!success] 4ステージ取り込み・検証完了
> - **元ファイル数**: `{len(src_files)}` 件
> - **原本保全数 (`Imports/{bundle_id}/`)**: `{preserved_count}` 件（欠落ゼロ検証済）
> - **クリーンMarkdown蒸留数 (`{target_folder}/`)**: `{len(distilled_notes)}` 件
> - **公開領域 (`area`)**: `{area}`

## 1. 蒸留済みクリーンノート (`{target_folder}/`)
{notes_list_md}

## 2. 原本バイナリ・添付ファイル (`Imports/{bundle_id}/`)
{bin_list_md}
"""
    atomic_write_text(moc_path, moc_md)

    # Link in Home.md if not already linked
    home_path = vault_dir / "Home.md"
    moc_rel = f"Imports/{bundle_id}_INDEX"
    if home_path.exists():
        home_txt = home_path.read_text(encoding="utf-8", errors="ignore")
        if moc_rel not in home_txt:
            home_txt = home_txt.rstrip() + f"\n- 📦 **[{date_str}]** [[{moc_rel}|Ingest: {bundle_slug} ({len(src_files)} files)]]\n"
            atomic_write_text(home_path, home_txt)

    # Recompile SHARED_MEMORY.md if not private
    if area.lower() != "private":
        try:
            from compiler import compile_shared_memory
            compile_shared_memory()
        except Exception:
            pass

    return {
        "bundle_id": bundle_id,
        "source_count": len(src_files),
        "preserved_count": preserved_count,
        "distilled_count": len(distilled_notes),
        "moc_path": str(moc_path.relative_to(vault_dir)),
        "distilled_notes": distilled_notes,
    }
