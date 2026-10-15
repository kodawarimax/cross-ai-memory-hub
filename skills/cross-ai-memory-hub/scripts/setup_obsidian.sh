#!/usr/bin/env bash
# ==============================================================================
# setup_obsidian.sh — Universal One-Command Installer for Cross-AI Memory & Persona Hub
# Supports macOS, Linux, and Windows (WSL) across ANY user's environment
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_VAULT="${1:-${OBSIDIAN_VAULT:-}}"
TARGET_PERSONA="${2:-${PERSONA_NAME:-}}"

echo "=================================================================="
echo "🏛️  Universal Cross-AI Memory & Self-Improving Persona Hub Setup"
echo "=================================================================="

# 1. Check / Install Obsidian App
echo "📦 Step 1: Checking Obsidian App Installation..."
OS_TYPE="$(uname -s)"
case "${OS_TYPE}" in
  Darwin*)
    if [ -d "/Applications/Obsidian.app" ]; then
      echo "✅ Obsidian is installed at /Applications/Obsidian.app"
    elif command -v brew >/dev/null 2>&1; then
      echo "⬇️ Installing Obsidian via Homebrew Cask..."
      brew install --cask obsidian
    else
      echo "⚠️ Obsidian not found in /Applications. Download from https://obsidian.md/download if needed."
    fi
    ;;
  Linux*)
    if command -v obsidian >/dev/null 2>&1; then
      echo "✅ Obsidian is installed."
    elif command -v snap >/dev/null 2>&1; then
      sudo snap install obsidian --classic
    elif command -v flatpak >/dev/null 2>&1; then
      flatpak install -y flathub md.obsidian.Obsidian
    else
      echo "⚠️ Install Obsidian from https://obsidian.md/download if needed."
    fi
    ;;
esac

# 2. Run Universal Hub Installer (auto-discovers $HOME, Vault, AI subfolders, deploys engine & daemon)
echo ""
echo "🚀 Step 2: Running Universal Environment Scanner & Hub Bootstrapper..."
ARGS=("--sync-now" "--install-daemon")
if [ -n "${TARGET_VAULT}" ]; then
  ARGS+=("--vault" "${TARGET_VAULT}")
fi
if [ -n "${TARGET_PERSONA}" ]; then
  ARGS+=("--persona-name" "${TARGET_PERSONA}")
fi

python3 "${SCRIPT_DIR}/universal_hub_installer.py" "${ARGS[@]}"

echo ""
echo "🔍 Step 3: Running Deterministic Health Check..."
if [ -n "${TARGET_VAULT}" ]; then
  OBSIDIAN_VAULT="${TARGET_VAULT}" python3 "${SCRIPT_DIR}/health_check.py"
else
  python3 "${SCRIPT_DIR}/health_check.py"
fi
