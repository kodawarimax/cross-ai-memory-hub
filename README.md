# Cross-AI Memory & Chat Archive Hub

> **Obsidian-Centered Shared Memory & Cross-Agent Full-Text Chat History for OpenAI Codex CLI, Anthropic Claude Code, and Google Antigravity (Gemini)**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9+-green.svg)](https://www.python.org/)
[![Obsidian Ready](https://img.shields.io/badge/Obsidian-Vault%20Integration-purple.svg)](https://obsidian.md/)

---

## 🌟 Overview

When working with multiple cutting-edge AI coding tools simultaneously (**OpenAI Codex CLI**, **Anthropic Claude Code**, and **Google Antigravity**), developers face two major hurdles:

1. **Siloed Chat Histories**: Conversations, debugging transcripts, and decisions are scattered across gigabytes of proprietary JSONL logs (`~/.codex/` and `~/.claude/projects/`).
2. **Context Amnesia**: Each AI operates in isolation without knowing what the other decided or solved.

**Cross-AI Memory Hub** solves this by:
- **Instant Full-Text Search (FTS5)** across thousands of Codex and Claude conversations (millisecond responses).
- **A Zero-Dependency Web Viewer** for comfortable timeline browsing and one-click Markdown copy.
- **Obsidian as the Single Source of Truth (SSOT)**: Compiling organization doctrines, active projects, and past lessons into a shared memory format automatically loaded by all three AI agents.

---

## 🏛️ Architecture

```
                           ┌─────────────────────────────────┐
                           │   Obsidian Vault                │
                           │   (Markdown Knowledge Base)     │
                           │                                 │
                           │ 📄 memory/SHARED_MEMORY.md      │ <--- Canonical Shared Context
                           │ 📁 wiki/ (Cases, Playbooks)     │ <--- Knowledge Graph
                           │ 📄 memory/CHAT_ARCHIVE.md       │ <--- Archive Portal
                           └───────────────┬─────────────────┘
                                           │
         ┌─────────────────────────────────┼─────────────────────────────────┐
         │                                 │                                 │
┌────────▼────────┐               ┌────────▼────────┐               ┌────────▼────────┐
│    Codex CLI    │               │   Claude Code   │               │   Antigravity   │
│   (OpenAI)      │               │   (Anthropic)   │               │     (Gemini)    │
│                 │               │                 │               │                 │
│ AGENTS.md bound │               │ CLAUDE.md bound │               │ Skill / Prompt  │
└────────┬────────┘               └────────┬────────┘               └────────┬────────┘
         │                                 │                                 │
         └─────────────────────────────────┼─────────────────────────────────┘
                                           │
                    ┌──────────────────────▼──────────────────────┐
                    │       Integrated CLI Tools                  │
                    │  ・chat-archive (Search & Web UI)           │
                    │  ・ai-memory (Read & Record to Obsidian)    │
                    └─────────────────────────────────────────────┘
```

---

## 📦 Quick Setup

### Step 0: Obsidian Download & Vault Setup (Automated)
If you do not have Obsidian installed or need to initialize a fresh Cross-AI Vault:

```bash
# Automated setup for macOS, Linux, and Windows:
./scripts/setup_obsidian.sh [optional_vault_path]
```

This automated script will:
1. **Detect & Download Obsidian**:
   - **macOS**: `brew install --cask obsidian` or direct DMG download
   - **Linux**: `snap install obsidian --classic` / Flatpak
   - **Windows**: `winget install Obsidian.Obsidian`
2. **Scaffold the Cross-AI Vault Directory**:
   - Creates `memory/`, `wiki/cases/`, `wiki/playbooks/`, `wiki/concepts/`, `wiki/strategies/`, `crm/`, `.obsidian/`
   - Generates initial `index.md`, `log.md`, and default Wikilink configurations.
3. **Compile Initial Shared Memory**:
   - Automatically bootstraps `memory/SHARED_MEMORY.md` and `memory/CHAT_ARCHIVE.md`.

*Once setup finishes, open Obsidian.app, click **"Open folder as vault"**, and select your vault directory!*

---

### Step 1: Clone & Link CLI Tools
```bash
git clone https://github.com/kodawarimax/cross-ai-memory-hub.git
cd cross-ai-memory-hub

# Create symlinks to your PATH (~/.local/bin)
mkdir -p ~/.local/bin
ln -sf $(pwd)/chat_archive_cli.py ~/.local/bin/chat-archive
ln -sf $(pwd)/ai_memory_cli.py ~/.local/bin/ai-memory
chmod +x ~/.local/bin/chat-archive ~/.local/bin/ai-memory
```

---

### Step 2: Index Chats & Sync Memory
```bash
# Build chat history index across Codex & Claude (~30s for 3,500+ sessions)
chat-archive sync

# Compile Obsidian shared memory (customize vault path via env if needed)
export OBSIDIAN_VAULT=~/path/to/your/obsidian-vault
ai-memory sync
```

---

### Step 3: Run Automated Health Check
```bash
python3 scripts/health_check.py
```

Expected output:
```
==================================================
🩺 Cross-AI Memory Hub — Health Diagnosis Report
==================================================
✅ Archive DB:      Healthy (118.4 MB)
   - Codex:         2,757 sessions
   - Claude:        889 sessions
   - Total:         3,646 indexed sessions
✅ Web Viewer:      Active at http://127.0.0.1:3333
✅ Shared Memory:   Ready (79 lines, updated)
✅ CLI Tools:       chat-archive (OK), ai-memory (OK)
✅ Agent Contracts: AGENTS.md (Bound), CLAUDE.md (Bound)
==================================================
🎉 Diagnosis Complete: All 3 AIs and Obsidian are fully synchronized.
```

---

## 🚀 Key Features & Commands

### 1. Chat Archive (`chat-archive`)
- **FTS5 Indexer**: Parses Codex (`~/.codex/sessions/**/*.jsonl`) and Claude (`~/.claude/projects/**/*.jsonl`) into an optimized SQLite FTS5 database (~100MB for 3,500+ sessions).
- **Deduplication & Hygiene**: Strips redundant system prompt injections to preserve clean user/assistant dialogue.
- **Local Web Viewer**: Responsive web UI (`http://localhost:3333`) powered purely by Python's built-in `http.server` (zero extra pip packages required!).

```bash
# Full-text search across Codex & Claude
chat-archive search "authentication refactor"

# Filter by provider
chat-archive search "payment webhook" --provider claude

# Show formatted markdown conversation
chat-archive show <session_id> --thinking --tools

# Launch Local Web UI
chat-archive serve --port 3333
```

### 2. Obsidian Shared Memory Bridge (`ai-memory`)
- **Automatic Compiler**: Compiles high-density `SHARED_MEMORY.md` from your Obsidian notes, doctrine, and recent lessons.
- **Chronicler Rules Compliance**: Writes new lessons, case studies, or decisions into Obsidian with YAML frontmatter, automatic tags, and at least two `[[wikilinks]]`.
- **Cross-Agent Auto-Binding**: Injected into `AGENTS.md`, `CLAUDE.md`, and Antigravity system prompts.

```bash
# Read shared context
ai-memory get
ai-memory get "Active Projects"

# Record a new lesson directly to Obsidian from any terminal or AI session
ai-memory record --type lesson --title "WebSocket Heartbeat Fix" --content "Implemented 30s ping-pong..." --author "Claude"

# Re-sync memory
ai-memory sync
```

---

## 📖 License
MIT License. Created by [kodawarimax](https://github.com/kodawarimax).
