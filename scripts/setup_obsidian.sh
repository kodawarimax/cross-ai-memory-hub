#!/usr/bin/env bash
# ==============================================================================
# setup_obsidian.sh — Automated Download & Setup for Obsidian + Cross-AI Vault
# Supports macOS, Linux, and Windows (via winget/WSL)
# ==============================================================================

set -euo pipefail

DEFAULT_VAULT="${HOME}/knowledge-empire"
TARGET_VAULT="${1:-${OBSIDIAN_VAULT:-$DEFAULT_VAULT}}"

echo "========================================================"
echo "🏛️  Obsidian Download & Cross-AI Vault Setup"
echo "========================================================"
echo "Target Vault Path: ${TARGET_VAULT}"
echo ""

# ------------------------------------------------------------------------------
# 1. Download & Install Obsidian App
# ------------------------------------------------------------------------------
echo "📦 Step 1: Checking Obsidian App Installation..."

OS_TYPE="$(uname -s)"
case "${OS_TYPE}" in
  Darwin*)
    if [ -d "/Applications/Obsidian.app" ]; then
      echo "✅ Obsidian is already installed at /Applications/Obsidian.app"
    else
      echo "⬇️ Installing Obsidian via Homebrew Cask..."
      if command -v brew >/dev/null 2>&1; then
        brew install --cask obsidian
        echo "✅ Obsidian installed successfully via Homebrew."
      else
        echo "⚠️ Homebrew not found. Opening official download page..."
        open "https://obsidian.md/download"
        echo "Please download and drag Obsidian to your /Applications folder, then press Enter."
        read -r
      fi
    fi
    ;;

  Linux*)
    if command -v obsidian >/dev/null 2>&1; then
      echo "✅ Obsidian is already installed."
    elif command -v snap >/dev/null 2>&1; then
      echo "⬇️ Installing Obsidian via Snap..."
      sudo snap install obsidian --classic
      echo "✅ Obsidian installed via Snap."
    elif command -v flatpak >/dev/null 2>&1; then
      echo "⬇️ Installing Obsidian via Flatpak..."
      flatpak install -y flathub md.obsidian.Obsidian
      echo "✅ Obsidian installed via Flatpak."
    else
      echo "⚠️ Please install Obsidian from: https://obsidian.md/download"
    fi
    ;;

  MINGW*|MSYS*|CYGWIN*)
    if command -v winget.exe >/dev/null 2>&1; then
      echo "⬇️ Installing Obsidian via winget..."
      winget.exe install Obsidian.Obsidian --silent --accept-source-agreements --accept-package-agreements
      echo "✅ Obsidian installed via winget."
    else
      echo "⚠️ Please install Obsidian from: https://obsidian.md/download"
    fi
    ;;

  *)
    echo "⚠️ Unknown OS: ${OS_TYPE}. Please install Obsidian manually from https://obsidian.md/download"
    ;;
esac

echo ""

# ------------------------------------------------------------------------------
# 2. Scaffolding Vault Structure
# ------------------------------------------------------------------------------
echo "📂 Step 2: Scaffolding Cross-AI Vault Structure at '${TARGET_VAULT}'..."

mkdir -p "${TARGET_VAULT}/memory"
mkdir -p "${TARGET_VAULT}/wiki/cases"
mkdir -p "${TARGET_VAULT}/wiki/playbooks"
mkdir -p "${TARGET_VAULT}/wiki/concepts"
mkdir -p "${TARGET_VAULT}/wiki/strategies"
mkdir -p "${TARGET_VAULT}/wiki/entities"
mkdir -p "${TARGET_VAULT}/crm"
mkdir -p "${TARGET_VAULT}/.obsidian"

# Create minimal index.md if it doesn't exist
if [ ! -f "${TARGET_VAULT}/index.md" ]; then
  cat << 'INDEX_EOF' > "${TARGET_VAULT}/index.md"
# Knowledge Empire — Index

> 3大AI（Codex / Claude Code / Antigravity）統合ナレッジベース & 記憶の正典。

## 正典 Hub（Source of Truth）
- [[memory/SHARED_MEMORY|AI共通記憶（3大AI共通正本）]]
- [[memory/CHAT_ARCHIVE|全チャット履歴アーカイブ（Codex & Claude）]]

## 型別 Index
- [[wiki/cases/|Cases (事例・トラブルシューティング)]]
- [[wiki/playbooks/|Playbooks (実行手順書)]]
- [[wiki/concepts/|Concepts (独自概念・ドクトリン)]]
- [[wiki/strategies/|Strategies (戦略方針)]]
- [[wiki/entities/|Entities (人物・組織・プロダクト)]]
INDEX_EOF
  echo "✅ Created initial index.md"
fi

# Create minimal log.md if it doesn't exist
if [ ! -f "${TARGET_VAULT}/log.md" ]; then
  cat << 'LOG_EOF' > "${TARGET_VAULT}/log.md"
# Knowledge Empire — 監査ログ

- Initialized Cross-AI Memory Hub.
LOG_EOF
  echo "✅ Created initial log.md"
fi

# Configure Obsidian app.json if missing
if [ ! -f "${TARGET_VAULT}/.obsidian/app.json" ]; then
  cat << 'APP_EOF' > "${TARGET_VAULT}/.obsidian/app.json"
{
  "attachmentFolderPath": "memory",
  "newFileFolderPath": "wiki/cases",
  "useMarkdownLinks": false,
  "livePreview": true
}
APP_EOF
  echo "✅ Configured .obsidian/app.json (Wikilinks & Markdown defaults)"
fi

echo ""

# ------------------------------------------------------------------------------
# 3. Initial Shared Memory Compilation
# ------------------------------------------------------------------------------
echo "🧠 Step 3: Compiling Initial Shared Memory & Portals..."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export OBSIDIAN_VAULT="${TARGET_VAULT}"

if [ -f "${SCRIPT_DIR}/compiler.py" ]; then
  python3 "${SCRIPT_DIR}/compiler.py"
  echo "✅ Initialized memory/SHARED_MEMORY.md"
fi

if [ ! -f "${TARGET_VAULT}/memory/CHAT_ARCHIVE.md" ]; then
  cat << 'CHAT_EOF' > "${TARGET_VAULT}/memory/CHAT_ARCHIVE.md"
---
title: "AI Chat Archive — 全チャット履歴ハブ"
type: hub
tags: [chat-archive, codex, claude, antigravity, memory]
---

# AI Chat Archive — Codex & Claude 全チャット履歴ハブ

## 概要
OpenAI Codex CLI および Anthropic Claude Code の全チャット履歴を統合インデックス化し、Obsidian・各AI・ブラウザから横断検索・全文閲覧できるようにしたアーカイブ基盤です。

## アクセス方法
- **ブラウザ Web ビューア**: [http://127.0.0.1:3333](http://127.0.0.1:3333)
- **ターミナル CLI**: `chat-archive search "<キーワード>"` / `chat-archive show <session_id>`
CHAT_EOF
  echo "✅ Created memory/CHAT_ARCHIVE.md"
fi

echo ""
echo "========================================================"
echo "🎉 Setup Complete!"
echo "========================================================"
echo "Next steps:"
echo "1. Open Obsidian.app"
echo "2. Click 'Open folder as vault' -> Select '${TARGET_VAULT}'"
echo "3. Run 'python3 scripts/health_check.py' to verify synchronization!"
echo "========================================================"
