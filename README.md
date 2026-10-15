# Cross-AI Memory & Self-Improving Persona Hub (v2.0 Universal Edition)

> **Obsidian-Centered Shared Memory, All-Subfolder Chat History (FTS5), Closed-Loop Self-Improving Persona & SNS Engine, and Built-in Onboarding Coach for OpenAI Codex CLI, Anthropic Claude Code, Google Antigravity (Gemini), and ChatGPT**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9+-green.svg)](https://www.python.org/)
[![Obsidian Ready](https://img.shields.io/badge/Obsidian-Vault%20Integration-purple.svg)](https://obsidian.md/)
[![Universal Skill](https://img.shields.io/badge/Skill-Codex%20%7C%20Claude%20%7C%20Antigravity-orange.svg)](#)

---

## 🌟 What's New in v2.0 (Universal Deep Obsidian Integration)

1. **4-AI + All-Subfolder Deep Harvesting**:
   - Indexes **OpenAI Codex CLI** (`~/.codex/sessions/**/*.jsonl` + `~/.codex/state_*.sqlite` + `~/.codex/memories/`), **Anthropic Claude Code** (`~/.claude/projects/*/*.jsonl` across all workspace subfolders + `~/.claude/projects/*/memory/*.md`), **Google Antigravity (Gemini)** (`~/.gemini/antigravity/brain/*/.system_generated/logs/transcript.jsonl`), and **ChatGPT Web Exports** (`conversations.json` or raw `.zip` archives dropped in `~/Downloads` / `~/Desktop` / `~/Documents`).
2. **Closed-Loop Self-Improving Persona & SNS Engine (`persona_extractor.py`)**:
   - Automatically extracts the user's authentic utterances across 3 axes: **使う言葉 (Philosophy)**, **反応する言葉 (Reaction)**, and **行動する言葉 (Action)** plus raw voice dictations (`~/.codex/transcription-history.jsonl`).
   - Learns from user corrections (`「そうじゃなくて」「〜はNG」「AIっぽい」`) and `feedback_*.md` notes, feeding dynamically learned banned words directly into a deterministic **Slop Gate** that grades and sanitizes X / Threads / note drafts (`SNS_READY_DRAFTS.md`).
3. **Built-in Agent Onboarding & Constraint Resolution Coach (`onboarding_coach.py`)**:
   - Automatically detects environment constraints (e.g., missing ChatGPT Web export, Cold-Start < 15 utterances, or Windows symlink/scheduler setup) and guides the user interactively via `ai-memory onboard` (`--diagnose`, `--interview`, `--open-chatgpt`).
4. **100% Environment-Agnostic Skill Package (`skills/cross-ai-memory-hub/`)**:
   - Zero hardcoded user paths. Drop-in installation for any macOS, Linux, or Windows/WSL user via `universal_hub_installer.py`.

---

## 🏛️ Architecture

```
                           ┌──────────────────────────────────────────────────┐
                           │   Obsidian Vault (Single Source of Truth)        │
                           │                                                  │
                           │ 📄 memory/SHARED_MEMORY.md    (4-AI Context)     │
                           │ 📄 memory/PERSONA_CORE.md     (Persona OS)       │
                           │ 📄 memory/VOICE_LOG.md        (Raw Utterances)   │
                           │ 📄 memory/SNS_READY_DRAFTS.md (Slop-Checked SNS) │
                           │ 📁 raw/sessions/              (Incremental Notes)│
                           │ 📁 linked/claude-workspaces/  (All Subfolders)   │
                           └────────────────────────┬─────────────────────────┘
                                                    │
         ┌──────────────────────────┬───────────────┴──────────┬──────────────────────────┐
         │                          │                          │                          │
┌────────▼────────┐        ┌────────▼────────┐        ┌────────▼────────┐        ┌────────▼────────┐
│    Codex CLI    │        │   Claude Code   │        │   Antigravity   │        │   ChatGPT Web   │
│ (JSONL+SQLite)  │        │ (All Subfolders)│        │ (Brain JSONL)   │        │ (Auto-ZIP Sync) │
└────────┬────────┘        └────────┬────────┘        └────────┬────────┘        └────────┬────────┘
         │                          │                          │                          │
         └──────────────────────────┴───────────────┬──────────┴──────────────────────────┘
                                                    │
                     ┌──────────────────────────────▼──────────────────────────────┐
                     │       Integrated CLI & Self-Improving Engine                │
                     │  ・chat-archive (FTS5 Search, Incremental Vault Exporter)   │
                     │  ・ai-memory (Shared Memory, Persona SNS, Onboarding Coach) │
                     └─────────────────────────────────────────────────────────────┘
```

---

## 📦 One-Command Universal Installer (Recommended)

Works on **any macOS, Linux, or Windows/WSL environment** with zero hardcoded paths:

```bash
git clone https://github.com/kodawarimax/cross-ai-memory-hub.git
cd cross-ai-memory-hub

# Auto-discover AI logs, create/link Obsidian Vault, install CLIs & 30-min auto-sync:
python3 scripts/universal_hub_installer.py --vault ~/knowledge-empire --persona-name "Your Name"
```

---

## 🚀 Key Commands

### 1. Built-in Agent Onboarding & Constraint Coach (`ai-memory onboard`)
Resolves ChatGPT Web export ingestion, Cold-Start Persona seeding (5-question interview), and OS-specific setup:

```bash
# Auto-diagnose environment constraints & unzip any ChatGPT export in ~/Downloads
ai-memory onboard --diagnose

# Open ChatGPT Data Controls in your browser with 3-click export instructions
ai-memory onboard --open-chatgpt

# Run the 5-minute interactive Persona Seed interview (solves Cold-Start immediately)
ai-memory onboard --interview
```

### 2. Daily Semantic Contradiction Detector & User Arbiter (`ai-memory contradictions`)
Automatically detects semantic contradictions across learned rules, feedback memories, and Persona Core (e.g., *Tone: Polite vs. Casual*, *Length: 1-3 line Token-Zero vs. Detailed Educational Explanation*, *Format: Bullet Points vs. Continuous Prose*, *Autonomy: Batch Approval vs. Strict L0 Gate*), and asks the user once per day to decide which rule is canonical or how to split them by context:

```bash
# Scan for semantic contradictions and update memory/CONTRADICTION_INBOX.md
ai-memory contradictions --scan

# Interactive Q&A to resolve pending contradictions (1=Keep A, 2=Keep B, 3=Keep Both with Context Split)
ai-memory contradictions --ask

# Resolve directly from any AI chat session
ai-memory contradictions --resolve <contra-id> --choice BOTH --note "Use bullet tables for engineering, continuous prose for SNS"
```

### 3. Self-Improving Persona & SNS Engine (`ai-memory persona`)
```bash
# Run closed-loop extraction, rule learning, and SNS draft generation
ai-memory persona --mode sync

# Inspect your Persona Core OS, Raw Voice Log, or Ready-to-Post SNS Drafts
ai-memory persona --mode core
ai-memory persona --mode voice
ai-memory persona --mode sns
```

### 4. Cross-AI Full-Text Search & Obsidian Mirror (`chat-archive`)
```bash
# Incremental sync of Codex, Claude (all subfolders), Antigravity & ChatGPT to SQLite FTS5 + Obsidian
chat-archive sync

# Millisecond full-text search across all 4 AIs
chat-archive search "architecture decision"

# Show full conversation transcript
chat-archive show <session_id>

# Launch zero-dependency Web UI at http://127.0.0.1:3333
chat-archive serve --port 3333
```

### 5. Shared Memory Read & Chronicler Record (`ai-memory`)
```bash
# View or search compiled 4-AI shared context
ai-memory get
ai-memory search "keyword"

# Record a lesson, project update, or strategy note with automatic YAML + [[wikilinks]]
ai-memory record --type lesson --title "Title" --content "Lesson details"
ai-memory sync
```

---

## 🧩 Installing as an Agent Skill (Claude Code / Codex / Antigravity)

This repository includes the full portable skill definition in [`skills/cross-ai-memory-hub/`](skills/cross-ai-memory-hub/SKILL.md):

```bash
mkdir -p ~/.claude/skills ~/.codex/skills
cp -R skills/cross-ai-memory-hub ~/.claude/skills/
cp -R skills/cross-ai-memory-hub ~/.codex/skills/
```

---

## 📖 License
MIT License. Created by [kodawarimax](https://github.com/kodawarimax).
