#!/usr/bin/env bash
# auto-sync-obsidian.sh
# Incrementally syncs all 4 AIs (Codex JSONL+SQLite+zst, Claude Code+Desktop, Antigravity, ChatGPT)
# into archive.db + Obsidian raw/sessions/, and recompiles SHARED_MEMORY.md + Persona SNS drafts.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARCHIVE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DEV_DIR="$(cd "$ARCHIVE_DIR/.." && pwd)"

if [ -f "$ARCHIVE_DIR/indexer.py" ]; then
  python3 "$ARCHIVE_DIR/indexer.py" >/dev/null 2>&1
fi
if [ -f "$DEV_DIR/ai-shared-memory/contradiction_resolver.py" ]; then
  python3 "$DEV_DIR/ai-shared-memory/contradiction_resolver.py" --daily-cron >/dev/null 2>&1 || true
elif [ -f "$ARCHIVE_DIR/contradiction_resolver.py" ]; then
  python3 "$ARCHIVE_DIR/contradiction_resolver.py" --daily-cron >/dev/null 2>&1 || true
fi
if [ -f "$DEV_DIR/ai-shared-memory/compiler.py" ]; then
  python3 "$DEV_DIR/ai-shared-memory/compiler.py" >/dev/null 2>&1
elif [ -f "$ARCHIVE_DIR/compiler.py" ]; then
  python3 "$ARCHIVE_DIR/compiler.py" >/dev/null 2>&1
fi
