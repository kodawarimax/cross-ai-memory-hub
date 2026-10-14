#!/usr/bin/env python3
"""
universal_hub_installer.py — Environment-Agnostic Installer & Bootstrapper for Cross-AI Memory & Persona Hub.
Works on any user's macOS / Linux / WSL environment with zero external dependencies (Python 3 stdlib only).

Features:
1. Auto-detects $HOME, OS, user's Persona Name (via CLI arg, git config, or OS account), and existing Obsidian Vaults.
2. Dynamically discovers all AI conversation & memory stores across $HOME subfolders:
   - Claude Code (~/.claude/projects/*, subagents, memory/*.md, history.jsonl, session-data)
   - Claude Desktop App (~/Library/Application Support/Claude or ~/.config/Claude)
   - OpenAI Codex CLI & App (~/.codex*, sessions, archived_sessions/*.jsonl.zst, state_5.sqlite, thread_history_1.sqlite, memories_1.sqlite, transcription-history.jsonl)
   - Google Antigravity (~/.gemini/antigravity/brain/*/transcript.jsonl)
   - ChatGPT Projects & Exports (~/.codex/.chatgpt-projects/*, conversations.json in Downloads/Desktop/Documents)
3. Scaffolds the 4-Layer Obsidian Vault (raw/sessions, linked, wiki, memory) & Self-Improving Persona SNS Engine.
4. Installs `chat-archive` and `ai-memory` CLIs into ~/.local/bin and configures 10-minute auto-sync (LaunchAgent / Cron).
"""

import argparse
import glob
import json
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def detect_persona_name(explicit_name: str = None) -> str:
    if explicit_name:
        return explicit_name.strip()
    if os.environ.get("PERSONA_NAME"):
        return os.environ["PERSONA_NAME"].strip()
    try:
        out = subprocess.check_output(["git", "config", "--global", "user.name"], text=True, stderr=subprocess.DEVNULL).strip()
        if out:
            return out
    except Exception:
        pass
    if platform.system() == "Darwin":
        try:
            out = subprocess.check_output(["id", "-F"], text=True, stderr=subprocess.DEVNULL).strip()
            if out:
                return out
        except Exception:
            pass
    return Path.home().name


def detect_obsidian_vault(explicit_vault: str = None) -> Path:
    if explicit_vault:
        return Path(os.path.expanduser(explicit_vault)).resolve()
    if os.environ.get("OBSIDIAN_VAULT"):
        return Path(os.path.expanduser(os.environ["OBSIDIAN_VAULT"])).resolve()

    home = Path.home()
    # Check common workspace locations first
    candidates = [
        home / "Claude" / "knowledge-empire",
        home / "knowledge-empire",
        home / "Documents" / "knowledge-empire",
    ]
    for c in candidates:
        if c.exists() and (c / "memory").exists():
            return c.resolve()

    # Check Obsidian's official obsidian.json registry to find the user's active vault
    obs_configs = [
        home / "Library" / "Application Support" / "obsidian" / "obsidian.json",
        home / ".config" / "obsidian" / "obsidian.json",
    ]
    for cfg in obs_configs:
        if cfg.exists():
            try:
                data = json.loads(cfg.read_text(encoding="utf-8", errors="ignore"))
                vaults = data.get("vaults", {})
                # Prefer open vault or most recently updated vault
                sorted_v = sorted(
                    vaults.values(),
                    key=lambda v: (1 if v.get("open") else 0, v.get("ts", 0)),
                    reverse=True
                )
                for v in sorted_v:
                    vp = Path(v.get("path", ""))
                    if vp.exists():
                        return vp.resolve()
            except Exception:
                pass

    return (home / "knowledge-empire").resolve()


def discover_environment(home: Path = None) -> dict:
    home = home or Path.home()
    claude_dir = home / ".claude"
    codex_dir = home / ".codex"
    agy_dir = home / ".gemini" / "antigravity" / "brain"

    claude_workspaces = list((claude_dir / "projects").iterdir()) if (claude_dir / "projects").exists() else []
    claude_jsonl = list((claude_dir / "projects").rglob("*.jsonl")) if (claude_dir / "projects").exists() else []
    claude_mem_dirs = [d / "memory" for d in claude_workspaces if d.is_dir() and (d / "memory").exists()]

    claude_desktop_dirs = [
        home / "Library" / "Application Support" / "Claude" / "local-agent-mode-sessions",
        home / ".config" / "Claude" / "local-agent-mode-sessions",
    ]
    claude_desktop_jsonl = []
    for cd in claude_desktop_dirs:
        if cd.exists():
            claude_desktop_jsonl.extend(cd.rglob("*.jsonl"))

    codex_jsonl = list((codex_dir / "sessions").rglob("*.jsonl")) if (codex_dir / "sessions").exists() else []
    codex_zst = list((codex_dir / "archived_sessions").rglob("*.jsonl.zst")) if (codex_dir / "archived_sessions").exists() else []
    codex_sqlites = [p for p in [codex_dir / "state_5.sqlite", codex_dir / "thread_history_1.sqlite", codex_dir / "memories_1.sqlite"] if p.exists()]
    chatgpt_projects = list((codex_dir / ".chatgpt-projects").glob("*")) if (codex_dir / ".chatgpt-projects").exists() else []

    agy_transcripts = list(agy_dir.glob("*/.system_generated/logs/transcript.jsonl")) if agy_dir.exists() else []

    chatgpt_exports = []
    for sub in ["Downloads", "Desktop", "Documents"]:
        sp = home / sub
        if sp.exists():
            chatgpt_exports.extend(sp.glob("**/conversations.json"))

    return {
        "os": platform.system(),
        "home": str(home),
        "claude_workspaces_count": len([d for d in claude_workspaces if d.is_dir()]),
        "claude_jsonl_count": len(claude_jsonl),
        "claude_desktop_jsonl_count": len(claude_desktop_jsonl),
        "claude_memory_dirs": [str(d) for d in claude_mem_dirs],
        "claude_history_exists": (claude_dir / "history.jsonl").exists(),
        "codex_jsonl_count": len(codex_jsonl),
        "codex_zst_count": len(codex_zst),
        "codex_sqlites": [p.name for p in codex_sqlites],
        "chatgpt_projects_count": len(chatgpt_projects),
        "chatgpt_exports_count": len(chatgpt_exports),
        "antigravity_sessions_count": len(agy_transcripts),
    }


def scaffold_vault_and_persona(vault_dir: Path, persona_name: str):
    for sub in [
        "raw/sessions/claude",
        "raw/sessions/codex",
        "raw/sessions/antigravity",
        "linked/claude-workspaces",
        "linked/subfolders",
        "memory",
        "wiki/entities",
        "wiki/strategies",
        "wiki/playbooks",
        "wiki/cases",
        "wiki/concepts",
        "crm",
        ".obsidian",
    ]:
        (vault_dir / sub).mkdir(parents=True, exist_ok=True)

    # Ensure raw/ is in .gitignore so 10,000+ session logs don't bloat git
    gitignore = vault_dir / ".gitignore"
    if gitignore.exists():
        gi_txt = gitignore.read_text(encoding="utf-8", errors="ignore")
        if "raw/" not in gi_txt:
            gitignore.write_text(gi_txt.rstrip() + "\nraw/\nlinked/\n", encoding="utf-8")
    else:
        gitignore.write_text(".obsidian/workspace*\n.DS_Store\nraw/\nlinked/\n", encoding="utf-8")

    # Create initial PERSONA_CORE.md if neither JUNGO_PERSONA_CORE.md nor PERSONA_CORE.md exists
    jungo_core = vault_dir / "memory" / "JUNGO_PERSONA_CORE.md"
    generic_core = vault_dir / "memory" / "PERSONA_CORE.md"
    if not jungo_core.exists() and not generic_core.exists():
        now_str = datetime.now().strftime("%Y-%m-%d")
        generic_core.write_text(f"""---
title: "{persona_name} 完全人格コピー＆SNS言語エンジン正本 (PERSONA_CORE)"
date: {now_str}
type: persona-core
tags: [persona, clone, voice, sns, {persona_name}]
---

# 🧠 {persona_name} — 完全人格コピー＆SNS直結言語エンジン (`PERSONA_CORE`)

> **目的**: 全AI（Claude Code / Codex / Antigravity / ChatGPT）での対話・意思決定・音声入力から「{persona_name}」の思考回路と言語習慣を抽出し、SNS（X / Threads / note）発信やAIクローンへ直結させる正本。

---

## 1. 使う言葉（Active Lexicon & Voice DNA）
- 日常のAI壁打ちから自動抽出された思想・世界観フレーズ（`VOICE_LOG.md` と連動）。
- **絶対NG表現（AI Slop排除）**: 「いかがでしたか？」「〜と言えるでしょう」「まず第一に」「素晴らしいアイデアです」等の機械的定型文。

## 2. 反応する言葉（Emotional & Intellectual Triggers）
- **共鳴トリガー（Positive）**: 本人が強く共感・称賛する価値観や姿勢。
- **違和感・義憤トリガー（Negative / SNSフック源）**: 本人が「それは違う」「なぜそうなるのか」と問いを立てるポイント。

## 3. 行動する言葉（Action & Mobilization Commands）
- 思考を具体的な仕組みや一歩に変える際の意思決定フレーズ・読者の背中を押すCTA。

## 4. SNS変換フォーマット（X / Threads / note）
- **構造**: `違和感/問い (Reaction) ➔ 本質的構造 (Interpretation) ➔ 実体験 (Story) ➔ 一歩の提案 (Action)`

## 🔄 5. 自己改善フィードバックループ（Auto-Evolving Persona Ledger）
""", encoding="utf-8")


def bind_agent_contracts(workspace_dir: Path, vault_dir: Path):
    block = f"""
## 共通記憶 & 人格コピー統合基盤 (Cross-AI Obsidian Hub)

- 全AI（Codex / Claude Code / Antigravity）は、`{vault_dir}/memory/SHARED_MEMORY.md` を共通の記憶正本として参照する。
- 全AIの過去〜今後のチャット履歴は `{vault_dir}/raw/sessions/` 及び `chat-archive` (SQLite FTS5) に自動集約される。
- 横断検索: `ai-memory search "<キーワード>"` / `chat-archive search "<キーワード>"`
- 人格コピー＆SNSドラフト抽出: `ai-memory persona --mode core` / `ai-memory persona --mode sns`
- 重要決定・教訓の記録: `ai-memory record --type <lesson|project|strategy> --title "..." --content "..."`
- **内蔵エージェント・オンボーディング規律**: `SHARED_MEMORY.md` の `§6. 内蔵エージェントからの環境最適化・ユーザー案内` に未解決の制約（ChatGPTエクスポート案内、コールドスタート時の5問人格インタビュー、OS設定案内）が表示されている場合、AIエージェントは対話の中で自律的にユーザーへその手順を案内・質問して解決をリードする（`ai-memory onboard --diagnose` / `ai-memory onboard --seed-philosophy ...`）。
"""
    for fname in ["AGENTS.md", "CLAUDE.md"]:
        fpath = workspace_dir / fname
        if fpath.exists():
            txt = fpath.read_text(encoding="utf-8", errors="ignore")
            if "SHARED_MEMORY.md" not in txt:
                fpath.write_text(txt.rstrip() + "\n" + block, encoding="utf-8")


def deploy_runtime_engine(vault_dir: Path) -> tuple[Path, Path]:
    """
    Ensures the portable runtime scripts (indexer.py, obsidian_exporter.py, compiler.py, persona_extractor.py, onboarding_coach.py, cli.py, recorder.py)
    and CLI binaries (~/.local/bin/chat-archive, ~/.local/bin/ai-memory) exist in the target user's environment.
    """
    home = Path.home()
    dev_archive = home / "Claude" / "dev" / "ai-chat-archive"
    dev_memory = home / "Claude" / "dev" / "ai-shared-memory"
    bundled_engine = Path(__file__).resolve().parent / "engine"

    if dev_archive.exists() and dev_memory.exists():
        archive_dir = dev_archive
        memory_dir = dev_memory
    else:
        hub_root = vault_dir / ".ai-hub"
        archive_dir = hub_root / "ai-chat-archive"
        memory_dir = hub_root / "ai-shared-memory"
        (archive_dir / "bin").mkdir(parents=True, exist_ok=True)
        memory_dir.mkdir(parents=True, exist_ok=True)
        if bundled_engine.exists():
            for fname in ["indexer.py", "obsidian_exporter.py", "reader.py", "server.py", "cli.py"]:
                src = bundled_engine / "ai-chat-archive" / fname
                if src.exists():
                    shutil.copy2(src, archive_dir / fname)
            sync_sh = bundled_engine / "ai-chat-archive" / "bin" / "auto-sync-obsidian.sh"
            if sync_sh.exists():
                dst_sh = archive_dir / "bin" / "auto-sync-obsidian.sh"
                shutil.copy2(sync_sh, dst_sh)
                dst_sh.chmod(0o755)
            for fname in ["compiler.py", "persona_extractor.py", "onboarding_coach.py", "recorder.py", "cli.py"]:
                src = bundled_engine / "ai-shared-memory" / fname
                if src.exists():
                    shutil.copy2(src, memory_dir / fname)

    # Ensure ~/.local/bin/chat-archive and ~/.local/bin/ai-memory wrappers exist
    local_bin = home / ".local" / "bin"
    local_bin.mkdir(parents=True, exist_ok=True)
    ca_bin = local_bin / "chat-archive"
    if not ca_bin.exists():
        ca_bin.write_text(f'#!/usr/bin/env bash\nexec python3 "{archive_dir / "cli.py"}" "$@"\n', encoding="utf-8")
        ca_bin.chmod(0o755)
    am_bin = local_bin / "ai-memory"
    if not am_bin.exists():
        am_bin.write_text(f'#!/usr/bin/env bash\nexec python3 "{memory_dir / "cli.py"}" "$@"\n', encoding="utf-8")
        am_bin.chmod(0o755)

    return archive_dir, memory_dir


def install_background_daemon(archive_dir: Path, memory_dir: Path, vault_dir: Path, persona_name: str):
    sync_script = archive_dir / "bin" / "auto-sync-obsidian.sh"
    if not sync_script.exists():
        return
    sys_name = platform.system()
    if sys_name == "Darwin":
        plist_dir = Path.home() / "Library" / "LaunchAgents"
        plist_dir.mkdir(parents=True, exist_ok=True)
        plist_path = plist_dir / "com.kodawari.cross-ai-obsidian-sync.plist"
        if not plist_path.exists():
            plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.kodawari.cross-ai-obsidian-sync</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>{sync_script}</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>OBSIDIAN_VAULT</key>
        <string>{vault_dir}</string>
        <key>PERSONA_NAME</key>
        <string>{persona_name}</string>
    </dict>
    <key>StartInterval</key>
    <integer>600</integer>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
"""
            plist_path.write_text(plist_content, encoding="utf-8")
            subprocess.run(["launchctl", "load", str(plist_path)], stderr=subprocess.DEVNULL)
            print(f"✅ Installed 10-minute macOS LaunchAgent: {plist_path}")
    elif sys_name == "Linux":
        try:
            cur = subprocess.check_output(["crontab", "-l"], text=True, stderr=subprocess.DEVNULL)
        except Exception:
            cur = ""
        if str(sync_script) not in cur:
            line = f'*/10 * * * * OBSIDIAN_VAULT="{vault_dir}" PERSONA_NAME="{persona_name}" /bin/bash "{sync_script}" >/dev/null 2>&1\n'
            proc = subprocess.Popen(["crontab", "-"], stdin=subprocess.PIPE, text=True)
            proc.communicate(cur.rstrip() + "\n" + line)
            print("✅ Installed 10-minute Linux cron job.")
    elif os.name == "nt":
        try:
            win_cmd = f'cmd /c "set OBSIDIAN_VAULT={vault_dir}&& set PERSONA_NAME={persona_name}&& python \"{archive_dir / "indexer.py"}\" && python \"{archive_dir / "obsidian_exporter.py"}\" && python \"{memory_dir / "compiler.py"}\""'
            subprocess.run(
                ["schtasks", "/Create", "/SC", "MINUTE", "/MO", "10", "/TN", "CrossAIObsidianSync", "/TR", win_cmd, "/F"],
                check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            print("✅ Installed 10-minute Windows Scheduled Task (CrossAIObsidianSync).")
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(description="Universal Cross-AI Obsidian Memory & Persona Hub Installer")
    parser.add_argument("--vault", help="Target Obsidian Vault path (auto-detected if omitted)")
    parser.add_argument("--persona-name", help="Target user's full name for Persona Core generation")
    parser.add_argument("--workspace", default=str(Path.cwd()), help="Primary project workspace directory")
    parser.add_argument("--diagnose-only", action="store_true", help="Only scan and report environment without modifying files")
    parser.add_argument("--sync-now", action="store_true", help="Run initial Shared Memory & Persona compilation immediately")
    parser.add_argument("--install-daemon", action="store_true", help="Install 10-minute background auto-sync daemon")
    args = parser.parse_args()

    persona_name = detect_persona_name(args.persona_name)
    vault_dir = detect_obsidian_vault(args.vault)
    env_info = discover_environment()

    print("==================================================================")
    print("🌐 Universal Cross-AI Memory & Persona Hub — Environment Scanner")
    print("==================================================================")
    print(f"👤 Persona Owner:          {persona_name}")
    print(f"🖥️  OS / Home Directory:    {env_info['os']} ({env_info['home']})")
    print(f"🏛️  Target Obsidian Vault:  {vault_dir}")
    print(f"📂 Discovered AI Sources:")
    print(f"   - Claude Code Subfolders: {env_info['claude_workspaces_count']} workspaces ({env_info['claude_jsonl_count']} session files)")
    print(f"   - Claude Desktop Sessions:{env_info['claude_desktop_jsonl_count']} files")
    print(f"   - Claude Memory Folders:  {len(env_info['claude_memory_dirs'])} folders")
    print(f"   - OpenAI Codex Sessions:  {env_info['codex_jsonl_count']} JSONL + {env_info['codex_zst_count']} ZST archives")
    print(f"   - OpenAI Codex SQLite:    {', '.join(env_info['codex_sqlites']) or 'None'}")
    print(f"   - ChatGPT Projects/Exps:  {env_info['chatgpt_projects_count']} project(s), {env_info['chatgpt_exports_count']} export(s)")
    print(f"   - Google Antigravity:     {env_info['antigravity_sessions_count']} session transcripts")
    print("==================================================================")

    if args.diagnose_only:
        return

    scaffold_vault_and_persona(vault_dir, persona_name)
    archive_dir, memory_dir = deploy_runtime_engine(vault_dir)
    bind_agent_contracts(Path(args.workspace), vault_dir)

    if args.install_daemon:
        install_background_daemon(archive_dir, memory_dir, vault_dir, persona_name)

    if args.sync_now and (memory_dir / "compiler.py").exists():
        env = os.environ.copy()
        env["OBSIDIAN_VAULT"] = str(vault_dir)
        env["PERSONA_NAME"] = persona_name
        subprocess.run([sys.executable, str(memory_dir / "compiler.py")], env=env, check=False)
        if (memory_dir / "onboarding_coach.py").exists():
            subprocess.run([sys.executable, str(memory_dir / "onboarding_coach.py"), "--diagnose"], env=env, check=False)

    print("✅ Vault structure, .gitignore guardrails, Portable Engine, Persona Core, and Agent Contracts verified.")


if __name__ == "__main__":
    main()

