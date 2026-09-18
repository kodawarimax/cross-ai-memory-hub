---
name: cross-ai-memory-hub
description: Codex, Claude Code, and Antigravity cross-agent shared memory & full chat archive setup, maintenance, and synchronization protocol via Obsidian. Use when setting up, repairing, or syncing cross-AI unified memory hubs, chat history archives, or Obsidian-centered knowledge synchronization.
tags: [cross-ai, memory, obsidian, codex, claude, antigravity, archive, knowledge-management]
priority: high
---

# Cross-AI Memory & Chat Archive Hub — 構築・運用・同期プロトコル

Codex CLI（OpenAI）、Claude Code（Anthropic）、Antigravity（Google Gemini）の3大AIが混在する環境において、
1. **Obsidianの自動インストールとVault初期化**
2. **全チャット履歴（数千セッション・数GB）のFTS5全文検索＆Webビューア基盤**
3. **Obsidian Vaultを正本（Single Source of Truth）とした3大AI共通記憶同期基盤**
をゼロから構築・保守・同期するための完全手順書です。

---

## 1. システム全体図

```
                           ┌─────────────────────────────────┐
                           │   Obsidian (Knowledge Empire)   │
                           │   /knowledge-empire/            │
                           │                                 │
                           │ 📄 memory/SHARED_MEMORY.md      │ <--- 常時参照コア記憶
                           │ 📁 wiki/ (正典, strategies等)    │ <--- 2,300+の知識グラフ
                           │ 📄 memory/CHAT_ARCHIVE.md       │ <--- 全履歴ポータル
                           └───────────────┬─────────────────┘
                                           │
         ┌─────────────────────────────────┼─────────────────────────────────┐
         │                                 │                                 │
┌────────▼────────┐               ┌────────▼────────┐               ┌────────▼────────┐
│    Codex CLI    │               │   Claude Code   │               │   Antigravity   │
│                 │               │                 │               │                 │
│ AGENTS.md指示書 │               │ CLAUDE.md指示書 │               │ .agent/skills/  │
└────────┬────────┘               └────────┬────────┘               └────────┬────────┘
         │                                 │                                 │
         └─────────────────────────────────┼─────────────────────────────────┘
                                           │
                    ┌──────────────────────▼──────────────────────┐
                    │  統合 CLI ツール群 (~/.local/bin)            │
                    │  ・chat-archive (FTS5全文検索 & Web表示)    │
                    │  ・ai-memory (共通記憶取得 & 書記官記録)    │
                    └─────────────────────────────────────────────┘
```

---

## 2. 実行フェーズ（6段階プロトコル）

### Phase 0: Obsidianの自動ダウンロード & Vault初期化（Setup）
新しい環境でObsidian未インストールの場合はワンコマンドでセットアップを実行：
```bash
./scripts/setup_obsidian.sh [vault_path]
```
- **OS別自動ダウンロード**:
  - macOS: `brew install --cask obsidian` または公式DMG
  - Linux: `snap install obsidian --classic` / Flatpak
  - Windows: `winget install Obsidian.Obsidian`
- **Vaultスキャフォールディング**:
  - `memory/`, `wiki/cases/`, `wiki/playbooks/`, `wiki/concepts/`, `wiki/strategies/`, `crm/`, `.obsidian/` を自動生成
  - 初期 `index.md`, `log.md`, wikilink設定（`.obsidian/app.json`）を構成

### Phase 1: データソース検出（Discovery）
- **Codex ログ**: `~/.codex/sessions/**/*.jsonl`、`~/.codex/session_index.jsonl`
- **Claude ログ**: `~/.claude/projects/**/*.jsonl`、`~/.claude/history.jsonl`
- **Obsidian Vault**: `~/knowledge-empire`（環境変数 `OBSIDIAN_VAULT` でオーバーライド可能）

### Phase 2: チャットアーカイブ基盤の構築（Chat Archive Engine）
- `indexer.py`: SQLite FTS5 (`messages_fts`) 仮想テーブル初期化、差分更新
- `reader.py`: 会話復元エンジン（思考プロセス・ツール実行折りたたみ）
- `server.py` & `web/index.html`: Python標準ライブラリ依存ゼロのWebビューア
- `chat-archive` CLI 配備（`~/.local/bin/chat-archive`）

### Phase 3: Obsidian 共通記憶ハブの構築（Shared Memory Hub）
- `compiler.py`: Vault内の正典・案件ステータス・最新教訓から `SHARED_MEMORY.md` を高密度コンパイル
- `recorder.py`: 書記官規約（YAMLフロントマター、2つ以上のwikilink、`log.md` 追記）に沿って新規知見を保存
- `ai-memory` CLI 配備（`~/.local/bin/ai-memory`）

### Phase 4: 各AIへの指示書 & ルーティング自動配備
- Codex: `AGENTS.md` に `SHARED_MEMORY.md` および `chat-archive` をバインド
- Claude Code: `CLAUDE.md` に同様にバインド
- Antigravity: 専用スキル配備
- Obsidian: `index.md` の正典Hubにリンク配置

### Phase 5: 検証・ヘルスチェック（Verification）
```bash
python3 scripts/health_check.py
```
DB状態、Webサーバー死活、共有記憶の行数・タイムスタンプ、CLIコマンドの健全性をワンショット診断。
