---
name: cross-ai-memory-hub
description: Codex, Claude Code, and Antigravity cross-agent shared memory & full chat archive setup, maintenance, and synchronization protocol via Obsidian. Use when setting up, repairing, or syncing cross-AI unified memory hubs, chat history archives, or Obsidian-centered knowledge synchronization.
tags: [cross-ai, memory, obsidian, codex, claude, antigravity, archive, knowledge-management]
priority: high
---

# Cross-AI Memory & Chat Archive Hub — 構築・運用・同期プロトコル

Codex CLI（OpenAI）、Claude Code（Anthropic）、Antigravity（Google Gemini）の3大AIが混在する環境において、
1. **全チャット履歴（数千セッション・数GB）のFTS5全文検索＆Webビューア基盤**
2. **Obsidian Vaultを正本（Single Source of Truth）とした3大AI共通記憶同期基盤**
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

## 2. 実行フェーズ（5段階プロトコル）

### Phase 1: データソース検出（Discovery）
対象環境のログストレージとObsidian Vaultを検出する：
- **Codex ログ**: `~/.codex/sessions/**/*.jsonl`（セッション）、`~/.codex/session_index.jsonl`（タイトル一覧）
- **Claude ログ**: `~/.claude/projects/**/*.jsonl`（プロジェクト別セッション）、`~/.claude/history.jsonl`
- **Obsidian Vault**: `~/Claude/knowledge-empire`（現在開かれているVaultを `~/Library/Application Support/obsidian/obsidian.json` より特定）

### Phase 2: チャットアーカイブ基盤の構築（Chat Archive Engine）
`dev/ai-chat-archive/` 配下に以下を設置・稼働：
1. **FTS5インデクサー (`indexer.py`)**:
   - SQLite FTS5 (`messages_fts`) 仮想テーブルを初期化（`unicode61` トークナイザ）。
   - Codex/Claude の生ログから、システム注入命令（`# AGENTS.md instructions...` 等）を除去し、純粋な会話（User発言、Assistantテキスト回答、Thinking、Tool実行）を抽出。
   - `mtime` に基づく高速差分インデックス（3,000セッション以上でも初回数十秒、差分は瞬時）。
2. **会話復元エンジン (`reader.py`)**:
   - セッションIDから該当JSONLをストリームし、綺麗なMarkdown（思考プロセス・ツール実行は折りたたみ表示）として出力。
3. **ゼロ依存ローカル Web ビューア (`server.py` & `web/index.html`)**:
   - Python標準 `http.server` で動作（追加pip不要）。
   - 左サイドバーにセッション一覧・検索・スニペット、右ペインにタイムライン表示。
   - ポート `3333` 等で常駐。
4. **グローバルCLI配備**:
   - `~/.local/bin/chat-archive` にシンボリックリンク作成。

### Phase 3: Obsidian 共通記憶ハブの構築（Shared Memory Hub）
`knowledge-empire/memory/` 配下に以下を設置・同期：
1. **共通記憶正本 (`SHARED_MEMORY.md`) のコンパイル (`compiler.py`)**:
   - 創業者・CEO（[[坂本淳悟_正典]]）の価値観、[[真の王]]、各部長エージェントの役割。
   - アクティブ案件（アガスティアDX、AIクローン、賃REVO、U-AI等）の最新ステータス表。
   - 全社共通規律（`force_l0` 人間承認必須領域、証拠主義、機密防衛、コーディング規約）。
   - 直近30日の最新教訓（`wiki/cases/` および `~/.claude/memory/` から自動抽出）。
2. **書記官規約に準拠した記録エンジン (`recorder.py`)**:
   - 新規知見を記録する際、Obsidian書記官規律を強制適用：
     - YAMLフロントマター（`title`, `date`, `type`, `tags`, `author`）
     - 最低2つのwikilink（例: `[[坂本淳悟_正典]]`, `[[IT部_正典]]`）
     - 日本語本文
     - `knowledge-empire/log.md` の先頭に監査ログを自動追記
     - `SHARED_MEMORY.md` の教訓セクションを即時再同期
3. **グローバルCLI配備**:
   - `~/.local/bin/ai-memory` にシンボリックリンク作成。

### Phase 4: 各AIへの指示書 & ルーティング自動配備
全AIが同じ共通記憶とアーカイブツールを使うよう、各設定ファイルを更新：
- **Codex**: `/Users/jungosakamoto/Claude/AGENTS.md` に共通記憶 `SHARED_MEMORY.md` と `chat-archive` コマンドを明記。
- **Claude Code**: `/Users/jungosakamoto/Claude/CLAUDE.md` に共通記憶とアーカイブ参照指示を明記。
- **Antigravity**: `.agent/skills/chat-archive/SKILL.md` および `.agent/skills/shared-memory/SKILL.md` を設置。
- **Obsidian**: `knowledge-empire/index.md` の正典Hubに `[[memory/SHARED_MEMORY]]` と `[[memory/CHAT_ARCHIVE]]` を追加。

### Phase 5: 検証・ヘルスチェック（Verification）
以下の実機チェックを実行して合格証拠を確認する：
```bash
# 1. チャット検索テスト (ミリ秒応答確認)
chat-archive search "アガスティア" --limit 1

# 2. 共通記憶取得テスト
ai-memory get "Active Projects"

# 3. 書記官自動記録テスト
ai-memory record --type lesson --title "テスト知見" --content "検証テスト内容" --author "Tester"

# 4. Webビューア死活確認
curl -s http://127.0.0.1:3333/api/sessions?limit=1
```

---

## 3. 日常の運用・同期コマンドリファレンス

| タスク | 実行コマンド |
|---|---|
| 過去チャットの全文検索 | `chat-archive search "<キーワード>"` |
| プロバイダ絞り込み検索 | `chat-archive search "<キーワード>" --provider codex` |
| 特定セッションの全文閲覧 | `chat-archive show <session_id>` |
| 思考ログも含めた閲覧 | `chat-archive show <session_id> --thinking` |
| 新規チャットの差分同期 | `chat-archive sync` |
| Webビューアの起動 | `chat-archive serve --port 3333` |
| 共通記憶の確認 | `ai-memory get [キーワード]` |
| 新たな教訓・決定の記録 | `ai-memory record --type <lesson|project|playbook> --title "..." --content "..."` |
| 共通記憶の再コンパイル | `ai-memory sync` |
| ハブ全体の稼働状況確認 | `ai-memory status` |

---

## 4. トラブルシューティング

- **Q: 新しいセッションが検索に出てこない**
  - A: `chat-archive sync` を実行してください。新しく生成されたJSONLファイルを走査して数秒でインデックスに追記されます。
- **Q: Webビューアにアクセスできない**
  - A: `chat-archive serve` でローカルサーバーを起動してください。バックグラウンド実行したい場合は `nohup python3 /Users/jungosakamoto/Claude/dev/ai-chat-archive/server.py >/dev/null 2>&1 &` で起動します。
- **Q: Obsidianのノート生成でエラーが出る**
  - A: `/Users/jungosakamoto/Claude/knowledge-empire` Vaultが存在すること、および書き込み権限があるかを確認してください。
