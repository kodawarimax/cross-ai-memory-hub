# Obsidian Native Skills Reference (v3.1 Unified Edition)

This reference consolidates the 7 Obsidian skills (**Vault Setup**, **4-Stage File Ingest**, **Auto-Capture**, **Obsidian Flavored Markdown**, **Obsidian Bases `.base`**, **Obsidian CLI**, and **Session Knowledge Archive**) into a single, environment-independent specification that works out of the box with `ai-memory` and `chat-archive`.

---

## 1. Unified Frontmatter Schema (v3.1)

Every Markdown note created by `ai-memory record`, `ai-memory ingest`, or AI agents directly inside the Obsidian Vault MUST follow this unified YAML property schema so that `Knowledge_Atlas.base`, `AI_Sessions.base`, and `compiler.py` (`SHARED_MEMORY.md`) remain 100% synchronized:

```yaml
---
title: "Note Title"
type: playbook | case | concept | entity | strategy | adr | project | resource | note | session
status: active | draft | archived
area: work | personal | private
date: YYYY-MM-DD
updated: YYYY-MM-DD
author: "AI"
tags:
  - ATLAS_INDEX
  - ai-memory
  - <type>
related:
  - "[[SHARED_MEMORY]]"
  - "[[PERSONA_CORE]]"
---
```

### Privacy Isolation Rule (`area: private`)
- Any note with `area: private` in its YAML frontmatter is stored safely in your local Obsidian Vault, but is **deterministically excluded** by `compiler.py` from `SHARED_MEMORY.md` and SNS drafts.
- All notes with `area: work` or `area: personal` are automatically passed through `sanitize_pii_and_secrets()` (masking API keys `sk-*`/`ghp_*`/`AIza*`, emails, phone numbers, and query-token URLs) before being compiled into `SHARED_MEMORY.md`.

---

## 2. Obsidian Flavored Markdown & Callouts

When writing or editing notes in the Vault:
- **Internal Links**: Always use `[[Note Name]]` or `[[Folder/Note Name|Display Text]]` for internal Vault links so Obsidian automatically tracks renames and Graph View edges.
- **Embeds**: Use `![[Imports/bundle/file.pdf]]` or `![[Attachments/image.png]]` to embed preserved binary assets.
- **Callouts**: Use standard Obsidian callouts to highlight structured sections:
  - `> [!info]` for metadata headers
  - `> [!abstract]` for distilled essence / executive summaries
  - `> [!tip]` for cross-AI action items and playbooks
  - `> [!warning]` for constraints, risks, or edge cases
- **Dataview (Playbooks)**: Playbooks recorded via `ai-memory record --type playbook` automatically include a `dataview` block listing all related `#ATLAS_INDEX` notes.

---

## 3. 4-Stage Non-Destructive File Ingest (`ai-memory ingest`)

When the user asks to import or distill files/folders ("Vaultに取り込んで", "ファイルを整理してObsidianに入れて", "PDFや資料を蒸留して保存して"):

```bash
# Deterministic 4-Stage Ingest CLI
ai-memory ingest "/path/to/folder_or_file" --area work --folder Resources
```

1. **STAGE 1 (Inventory & Raw Preservation)**:
   - Scans source files and copies all original files/binaries non-destructively into `<Vault>/Imports/<YYYY-MM-DD_bundle>/`.
2. **STAGE 2 (Essence Extraction)**:
   - Uses `doc-to-md INPUT -o OUTPUT.md` first if available, with zero-dependency local fallbacks for `.md`, `.txt`, `.docx`, `.pptx`, `.pdf` (`pdftotext`), and `.rtf` (`textutil`).
3. **STAGE 3 (Clean Markdown & PII Sanitization)**:
   - Strips UI noise, applies `sanitize_pii_and_secrets()`, and formats notes with Unified Frontmatter v3.1 (`#ATLAS_INDEX`, `#ingested`).
4. **STAGE 4 (Routing & Verification)**:
   - Routes clean Markdown notes to `Resources/` (or custom `--folder`), generates `Imports/<bundle>_INDEX.md` (MOC), links it in `Home.md`, verifies `source_count == preserved_count`, and recompiles `SHARED_MEMORY.md`.

---

## 4. Obsidian Bases (`.base` Database Views) & JSON Canvas

Running `ai-memory scaffold` (or `universal_hub_installer.py`) automatically creates three `.base` database files and `Overview.canvas` in the Vault root:

1. **`Knowledge_Atlas.base`**:
   - Table & Card views of all `#ATLAS_INDEX` notes grouped by `type` (`playbook`, `strategy`, `case`, `project`, `resource`).
2. **`AI_Sessions.base`**:
   - Scoped table view (`file.inFolder("raw/sessions")`, `limit: 100`) displaying recent sessions across Claude Code, Codex CLI, Antigravity, and ChatGPT.
3. **`Persona_&_SNS.base`**:
   - Card view of `memory/` files (`SHARED_MEMORY.md`, `PERSONA_CORE.md`, `VOICE_LOG.md`, `SNS_READY_DRAFTS.md`).
4. **`Overview.canvas`**:
   - JSON Canvas 1.0 visual architecture map connecting `Home.md`, `.base` views, and the Persona Engine.

---

## 5. Unified 7-Question Onboarding (`ai-memory onboard --interview`)

Combines **Obsidian Vault Setup (4 multiple-choice questions)** with **Cold-Start Persona Seed Extraction (3 core questions)** in a single 5-minute flow:
- **Part A (Vault Structure — 4 Questions)**:
  1. Work role (Founder/Executive, Employee/Specialist, Creator/Freelancer, Student/Researcher)
  2. Focus areas (Tasks, Ideas, Reading, People/CRM)
  3. Scope (Work + Personal, or Work only)
  4. Existing files path to ingest immediately (`ai-memory ingest`)
- **Part B (Persona Core — 3 Questions)**:
  5. Philosophy words (`使う言葉・使命・価値観`)
  6. Reaction triggers (`反応する言葉・違和感・共鳴`)
  7. Action commands & banned AI expressions (`行動する言葉・絶対NG表現`)
