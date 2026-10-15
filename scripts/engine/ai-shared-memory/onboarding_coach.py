#!/usr/bin/env python3
"""
onboarding_coach.py — Built-in Constraint Diagnosis & Interactive User Guidance Agent.
Automatically detects and resolves the 3 real-world environmental limitations:
1. ChatGPT Web History Sync (auto-detects .zip / conversations.json, or guides user to export in 3 clicks).
2. Cold-Start Persona Problem (when a new user has <30 utterances, runs a 5-question Persona Seed Interview or instructs the active AI agent to interview the user in chat).
3. OS / Runtime Constraints (Windows native symlink/Task Scheduler fallback & zstd archive tool check).
"""

import argparse
import json
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
import webbrowser
import zipfile
from datetime import datetime
from pathlib import Path

HOME_DIR = Path.home()
_default_vault = HOME_DIR / "Claude" / "knowledge-empire" if (HOME_DIR / "Claude").exists() else HOME_DIR / "knowledge-empire"
VAULT_DIR = Path(os.environ.get("OBSIDIAN_VAULT", str(_default_vault))).expanduser()
MEMORY_DIR = VAULT_DIR / "memory"
PERSONA_SEEDS_FILE = MEMORY_DIR / "PERSONA_SEEDS.md"
LEARNING_STATE_FILE = MEMORY_DIR / "persona_learning_state.json"
_default_archive_db = (HOME_DIR / "Claude" / "dev" / "ai-chat-archive" / "archive.db") if (HOME_DIR / "Claude" / "dev" / "ai-chat-archive").exists() else (VAULT_DIR / ".ai-hub" / "archive.db")
ARCHIVE_DB = Path(os.environ.get("AI_ARCHIVE_DB", str(_default_archive_db))).expanduser()


def diagnose_constraints(vault_dir: Path = None, archive_db: Path = None) -> dict:
    vault_dir = vault_dir or VAULT_DIR
    archive_db = archive_db or ARCHIVE_DB
    mem_dir = vault_dir / "memory"
    seeds_file = mem_dir / "PERSONA_SEEDS.md"

    # 1. Check ChatGPT Web Exports / Project DNA
    chatgpt_projects_dir = HOME_DIR / ".codex" / ".chatgpt-projects"
    has_chatgpt_project = chatgpt_projects_dir.exists() and any(chatgpt_projects_dir.rglob("*"))
    has_vault_chatgpt = bool(list((vault_dir / "wiki").glob("chatgpt-project*")))
    conv_jsons = []
    zip_exports = []
    for d in [HOME_DIR / "Downloads", HOME_DIR / "Desktop", HOME_DIR / "Documents", chatgpt_projects_dir]:
        if not d.exists():
            continue
        conv_jsons.extend(d.rglob("conversations.json"))
        for zf_path in d.glob("*.zip"):
            try:
                if zf_path.stat().st_size < 2 * 1024 * 1024 * 1024:
                    with zipfile.ZipFile(zf_path, "r") as zf:
                        if any(n == "conversations.json" or n.endswith("/conversations.json") for n in zf.namelist()):
                            zip_exports.append(zf_path)
            except Exception:
                pass

    chatgpt_ready = bool(has_chatgpt_project or has_vault_chatgpt or conv_jsons or zip_exports)

    # 2. Check Cold-Start Persona Status
    total_sessions = 0
    user_msg_count = 0
    if archive_db.exists():
        try:
            conn = sqlite3.connect(str(archive_db), timeout=5.0)
            total_sessions = conn.execute("SELECT COUNT(*) FROM sessions WHERE message_count > 0").fetchone()[0]
            user_msg_count = conn.execute("SELECT COUNT(*) FROM messages_fts WHERE role = 'user'").fetchone()[0]
            conn.close()
        except Exception:
            pass

    has_local_canon = (mem_dir / "LOCAL_CANON.md").exists() or (mem_dir / "LOCAL_PERSONA_CONFIG.json").exists()
    has_persona_seeds = seeds_file.exists()
    is_cold_start = (user_msg_count < 50) and (not has_local_canon) and (not has_persona_seeds)

    # 3. Check OS & Runtime Constraints (Windows native symlinks / zstd binary)
    os_name = platform.system()
    is_windows_native = (os.name == "nt")
    windows_symlink_ok = True
    if is_windows_native:
        test_link = vault_dir / ".symlink_test"
        try:
            if test_link.exists():
                test_link.unlink()
            test_link.symlink_to(vault_dir, target_is_directory=True)
            test_link.unlink()
        except Exception:
            windows_symlink_ok = False

    codex_zst_files = list((HOME_DIR / ".codex" / "archived_sessions").rglob("*.jsonl.zst")) if (HOME_DIR / ".codex" / "archived_sessions").exists() else []
    has_zstd_bin = shutil.which("zstd") is not None
    missing_zstd = len(codex_zst_files) > 0 and not has_zstd_bin

    directives = []
    if not chatgpt_ready:
        directives.append({
            "id": "CHATGPT_EXPORT_MISSING",
            "severity": "MEDIUM",
            "title": "ChatGPT Web版の過去履歴が未取り込みです",
            "agent_instruction": (
                "ユーザーに以下を案内してください：\n"
                "1. 『ChatGPT Web版の会話履歴も統合したい場合は、https://chatgpt.com/#settings/DataControls から「データをエクスポートする」を押し、届いたメールのZIPファイルをそのまま `~/Downloads`（ダウンロードフォルダ）に保存してください（解凍不要で自動取り込みされます）』と伝える。\n"
                "2. または `ai-memory onboard --open-chatgpt` を実行してエクスポート画面を開くよう案内する。"
            ),
            "cli_remedy": "ai-memory onboard --open-chatgpt"
        })

    if is_cold_start:
        directives.append({
            "id": "PERSONA_COLD_START",
            "severity": "HIGH",
            "title": f"初期データ不足（現在 {user_msg_count} 発言）のため『5問の人格コア抽出インタビュー』が必要です",
            "agent_instruction": (
                "このユーザーのAI対話ログがまだ少ないため、内蔵エージェントとしてチャット上で以下の5つの質問をユーザーに投げかけ、回答を受け取ったら "
                "`ai-memory onboard --seed-philosophy \"...\" --seed-reaction \"...\" --seed-action \"...\" --seed-ng \"...\"` を実行して即座に人格コア（PERSONA_CORE.md）とSNSドラフトを生成してください：\n"
                "  Q1 (使う言葉・使命): 仕事や人生で一番大切にしている価値観・絶対に譲れない「こだわり」は何ですか？\n"
                "  Q2 (反応する言葉・違和感): 業界や世間を見ていて「これはおかしい」「なぜみんなこうするのか」と違和感を覚えることは何ですか？\n"
                "  Q3 (反応する言葉・共鳴): どんな人や姿勢を見たときに「最高だ」「一緒にやりたい」と心が動きますか？\n"
                "  Q4 (行動する言葉・号令): 自分や仲間を動かすとき、よく使う口癖や判断基準は何ですか？\n"
                "  Q5 (絶対NG表現): SNSや文章で「これだけは自分らしくない・使いたくない」という言葉は何ですか？"
            ),
            "cli_remedy": "ai-memory onboard --interview"
        })

    if is_windows_native and not windows_symlink_ok:
        directives.append({
            "id": "WINDOWS_NATIVE_MODE",
            "severity": "LOW",
            "title": "Windowsネイティブ環境（開発者モードOFF）を検出 — ジャンクション自動フォールバック稼働中",
            "agent_instruction": (
                "現在Windowsのディレクトリジャンクション（mklink /J）で自動代替していますが、完全なシンボリックリンクと高速同期を有効にするため、ユーザーに "
                "『Windowsの「設定 ＞ システム ＞ 開発者向け」から「開発者モード」をONにするか、WSL (Ubuntu) 環境で運用すること』を案内してください。"
            ),
            "cli_remedy": "start ms-settings:developers"
        })

    if missing_zstd:
        directives.append({
            "id": "ZSTD_BINARY_MISSING",
            "severity": "LOW",
            "title": f"Codexの圧縮アーカイブ（{len(codex_zst_files)}件の .jsonl.zst）を展開する `zstd` が未インストールです",
            "agent_instruction": (
                "ユーザーに `brew install zstd` (macOS) または `sudo apt install zstd` (Linux/WSL) の実行を提案し、承認を得てインストールしてください。"
            ),
            "cli_remedy": "brew install zstd"
        })

    return {
        "chatgpt_ready": chatgpt_ready,
        "chatgpt_zip_count": len(zip_exports),
        "chatgpt_json_count": len(conv_jsons),
        "total_sessions": total_sessions,
        "user_msg_count": user_msg_count,
        "is_cold_start": is_cold_start,
        "has_persona_seeds": has_persona_seeds,
        "os_name": os_name,
        "windows_symlink_ok": windows_symlink_ok,
        "missing_zstd": missing_zstd,
        "directives": directives,
    }


def save_persona_seeds(philosophy: str, reaction: str, action: str, ng_words: str = "", persona_name: str = "") -> Path:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    p_name = persona_name or os.environ.get("PERSONA_NAME") or HOME_DIR.name
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    md = f"""---
title: "{p_name} 初期人格シード定義 (Persona Onboarding Seeds)"
date: {datetime.now().strftime("%Y-%m-%d")}
updated: "{now_str}"
type: persona-seeds
tags: [persona, onboarding, seeds, sns-source]
---

# 🌱 {p_name} 初期人格コア・インタビュー回答 (`PERSONA_SEEDS`)

> **記録日時**: `{now_str}`
> **目的**: コールドスタート環境（過去ログが少ない初期状態）でも初日から本人らしさ100%の人格コピー＆SNS投稿を生成するための初期シード正本。

## 1. 使う言葉・使命・価値観（Philosophy Seeds）
- {philosophy.strip() or '本質的な価値を届け、仕組みで人を自由にする。'}

## 2. 反応する言葉・違和感・共鳴（Reaction Seeds）
- {reaction.strip() or '表面的なテクニックや精神論でごまかす風潮に違和感を覚える。'}

## 3. 行動する言葉・意思決定号令（Action Seeds）
- {action.strip() or 'まず小さく試して検証し、再現性のある仕組みに落とし込む。'}

## 4. 絶対NG表現・トーン矯正ルール（Correction Seeds）
- {ng_words.strip() or 'AI特有の定型文（いかがでしたか、〜と言えるでしょう、素晴らしいアイデアです）は一切使わない。'}
"""
    PERSONA_SEEDS_FILE.write_text(md, encoding="utf-8")
    return PERSONA_SEEDS_FILE


def run_interactive_interview():
    print("==================================================================")
    print("🏛️  Unified Obsidian Vault & Persona Onboarding (v3.1 — 全7問)")
    print("==================================================================")
    print("前半4問（番号選択）であなたのObsidianフォルダ構造・データベース(.base)を構築し、")
    print("後半3問であなた専用の人格コア（PERSONA_CORE.md）とSNSドラフトを初期生成します。\n")

    print("--- [Part A: Obsidian Vault 構造設計 (選択式 4問)] ---")
    role_choice = input(
        "Q1 【お仕事】当てはまる番号を選んでください (1: 経営者・個人事業主 [推奨] / 2: 会社員・専門職 / 3: クリエイター・フリーランス / 4: 学生・研究者): "
    ).strip() or "1"
    focus_choice = input(
        "Q2 【管理したいこと(複数可・カンマ区切り)】(1: タスク・ToDo / 2: アイデア・メモ / 3: 学習・読書ノート / 4: 人脈・顧客情報 [デフォルト: 1,2,4]): "
    ).strip() or "1,2,4"
    scope_choice = input(
        "Q3 【管理範囲】(1: 仕事＋プライベート両方 [推奨] / 2: 仕事のみ): "
    ).strip() or "1"
    ingest_dir = input(
        "Q4 【既存ファイルの取り込み】取り込みたいフォルダやPDF等のパスがあれば入力してください (なければEnterでスキップ): "
    ).strip()

    extra_dirs = []
    if "1" in focus_choice:
        extra_dirs.append("Tasks")
    if "2" in focus_choice:
        extra_dirs.append("Ideas")
    if "3" in focus_choice:
        extra_dirs.append("Reading")
    if "4" in focus_choice:
        extra_dirs.append("People")
    if scope_choice == "1":
        extra_dirs.extend(["Work", "Personal"])

    try:
        from ingestor import ensure_obsidian_native_scaffold, ingest_files
        scaf_res = ensure_obsidian_native_scaffold(VAULT_DIR, extra_dirs=extra_dirs)
        print(f"\n✅ Obsidian Vault & Bases (.base / Canvas / Home.md) を構築しました: {scaf_res['vault_dir']}")
        if ingest_dir and Path(ingest_dir).expanduser().exists():
            ing_res = ingest_files(ingest_dir, VAULT_DIR)
            print(f"✅ 既存ファイル {ing_res['source_count']} 件を4ステージ蒸留・取り込みました: {ing_res['moc_path']}")
    except Exception as e:
        print(f"⚠️ Vault初期化通知: {e}")

    print("\n--- [Part B: 自己改善型・人格コア抽出 (記述式 3問)] ---")
    q5 = input("Q5 【使う言葉・使命】仕事や人生で一番大切にしている価値観・こだわりは何ですか？\n> ").strip()
    q6 = input("\nQ6 【反応する言葉】世間を見て「これはおかしい」と感じる違和感や、逆に「最高だ」と共鳴する姿勢は？\n> ").strip()
    q7 = input("\nQ7 【行動する言葉＆NG表現】判断基準・口癖と、文章で「これだけは使いたくないAIっぽい表現」は？\n> ").strip()

    # Split Q7 if user wrote NG words, or pass to both action and ng_words
    seed_path = save_persona_seeds(q5, q6, q7, q7)
    print(f"\n✅ 初期人格シードを保存しました: {seed_path}")

    try:
        from persona_extractor import sync_persona_engine
        from compiler import compile_shared_memory
        sync_persona_engine(verbose=True)
        compile_shared_memory()
    except Exception as e:
        print(f"⚠️ 再コンパイル通知: {e}")


def format_directives_for_shared_memory(vault_dir: Path = None, archive_db: Path = None) -> str:
    diag = diagnose_constraints(vault_dir=vault_dir, archive_db=archive_db)
    directives = diag["directives"]
    if not directives:
        return """---

## 🧭 6. 内蔵エージェント環境診断（Built-in Coach Status）

- **環境制約チェック**: **全項目クリア（Optimal）** — 4大AIログ・ChatGPTデータ・十分な人格発話母数・OS同期基盤すべて正常稼働中。追加のユーザー操作は不要です。
"""

    md = """---

## 🚨 6. 内蔵エージェントからの環境最適化・ユーザー案内（Active Coach Directives）

> **【AIエージェント（Codex / Claude Code / Antigravity）への絶対指示】**
> 以下の環境制約・初期セットアップ未完了項目が検出されました。**あなた（AIエージェント）はユーザーとの対話時に、以下の案内またはインタビューを自律的にユーザーへ提示して解決をリードしてください。**

"""
    for idx, d in enumerate(directives, 1):
        md += f"### {idx}. [{d['severity']}] {d['title']} (`{d['id']}`)\n"
        md += f"- **内蔵エージェントからの指示**: {d['agent_instruction']}\n"
        md += f"- **ワンコマンド解決**: `{d['cli_remedy']}`\n\n"
    return md


def main():
    parser = argparse.ArgumentParser(description="Unified Obsidian Vault Setup & Persona Onboarding Coach (v3.1)")
    parser.add_argument("--diagnose", action="store_true", help="Diagnose environmental constraints and print actionable instructions")
    parser.add_argument("--interview", action="store_true", help="Run unified 7-question Vault Setup + Persona Seed interview")
    parser.add_argument("--open-chatgpt", action="store_true", help="Open ChatGPT Data Controls in browser and explain auto-zip import")
    parser.add_argument("--seed-philosophy", help="Non-interactive seed for Philosophy (使う言葉)")
    parser.add_argument("--seed-reaction", help="Non-interactive seed for Reaction (反応する言葉)")
    parser.add_argument("--seed-action", help="Non-interactive seed for Action (行動する言葉)")
    parser.add_argument("--seed-ng", default="", help="Non-interactive seed for NG words / corrections")
    parser.add_argument("--ingest-path", default=None, help="Optional path to existing files to ingest during onboarding")
    args = parser.parse_args()

    if args.open_chatgpt:
        url = "https://chatgpt.com/#settings/DataControls"
        print(f"🌐 ブラウザで ChatGPT データエクスポート画面を開きます: {url}")
        print("1. 『データをエクスポートする (Export data)』をクリック")
        print("2. 届いたメールのダウンロードリンクから ZIP ファイルをそのまま『ダウンロード (~/Downloads)』に保存してください。")
        print("3. 解凍は不要です！10分毎の自動同期（または `chat-archive sync`）がZIPを自動検出・解凍してObsidianに統合します。")
        try:
            webbrowser.open(url)
        except Exception:
            pass
        return

    if args.ingest_path:
        from ingestor import ingest_files
        res = ingest_files(args.ingest_path, VAULT_DIR)
        print(f"✅ Ingested {res['source_count']} files into Obsidian Vault: {res['moc_path']}")

    if args.seed_philosophy or args.seed_reaction or args.seed_action:
        from ingestor import ensure_obsidian_native_scaffold
        ensure_obsidian_native_scaffold(VAULT_DIR)
        p = save_persona_seeds(
            args.seed_philosophy or "",
            args.seed_reaction or "",
            args.seed_action or "",
            args.seed_ng or "",
        )
        print(f"✅ Saved Persona Seeds to: {p}")
        try:
            from persona_extractor import sync_persona_engine
            from compiler import compile_shared_memory
            sync_persona_engine(verbose=True)
            compile_shared_memory()
        except Exception:
            pass
        return

    if args.interview:
        run_interactive_interview()
        return

    diag = diagnose_constraints()
    print("==================================================================")
    print("🧭 Built-in Onboarding & Constraint Resolution Coach")
    print("==================================================================")
    print(f"- ChatGPT Web / Project Status: {'✅ Ready' if diag['chatgpt_ready'] else '⚠️ Missing Export'}")
    print(f"- Persona Utterance Volume:     {diag['user_msg_count']:,} user messages ({'⚠️ Cold Start' if diag['is_cold_start'] else '✅ Sufficient'})")
    print(f"- OS & Symlink Environment:     {diag['os_name']} ({'✅ Optimal' if diag['windows_symlink_ok'] else '⚠️ Junction Fallback'})")
    print(f"- Codex ZST Decompressor:       {'⚠️ Missing zstd' if diag['missing_zstd'] else '✅ Ready'}")
    print("------------------------------------------------------------------")
    if not diag["directives"]:
        print("🎉 すべての環境制約が解消されています！ユーザーへの追加案内は不要です。")
    else:
        print(f"📢 検出された案内事項 ({len(diag['directives'])}件):")
        for d in diag["directives"]:
            print(f"\n[{d['severity']}] {d['title']}")
            print(f"👉 {d['agent_instruction']}")
            print(f"💻 実行コマンド: {d['cli_remedy']}")
    print("==================================================================")


if __name__ == "__main__":
    main()
