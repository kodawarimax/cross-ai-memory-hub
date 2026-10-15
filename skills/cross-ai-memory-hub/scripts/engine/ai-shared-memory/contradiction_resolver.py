#!/usr/bin/env python3
"""
contradiction_resolver.py - Semantic Contradiction Detector & Daily User Resolution Engine.

Detects semantic contradictions across:
- Learned corrections & style rules (persona_learning_state.json)
- Claude/Codex feedback memories (feedback_*.md, user_*.md)
- Persona Core OS & Seeds (PERSONA_CORE.md / PERSONA_SEEDS.md)
- Recent user utterances across all 4 AIs (Codex, Claude, Antigravity, ChatGPT)

Surfaces unresolved contradictions once per day via:
1. Obsidian Vault `memory/CONTRADICTION_INBOX.md`
2. Built-in Agent Directive in `memory/SHARED_MEMORY.md` (so any AI asks the user)
3. Interactive CLI `ai-memory contradictions --ask` or agent CLI `--resolve <id> --choice <A|B|BOTH|DISMISS>`
"""

import argparse
import hashlib
import json
import os
import platform
import re
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

HOME_DIR = Path.home()
_default_vault = HOME_DIR / "Claude" / "knowledge-empire" if (HOME_DIR / "Claude").exists() else HOME_DIR / "knowledge-empire"
VAULT_DIR = Path(os.environ.get("OBSIDIAN_VAULT", str(_default_vault))).expanduser()
MEMORY_DIR = VAULT_DIR / "memory"
_default_archive_db = (
    (HOME_DIR / "Claude" / "dev" / "ai-chat-archive" / "archive.db")
    if (HOME_DIR / "Claude" / "dev" / "ai-chat-archive").exists()
    else (VAULT_DIR / ".ai-hub" / "archive.db")
)
ARCHIVE_DB = Path(os.environ.get("AI_ARCHIVE_DB", str(_default_archive_db))).expanduser()

CONTRADICTIONS_STATE_FILE = MEMORY_DIR / "contradictions_state.json"
CONTRADICTION_INBOX_FILE = MEMORY_DIR / "CONTRADICTION_INBOX.md"
LEARNING_STATE_FILE = MEMORY_DIR / "persona_learning_state.json"


def atomic_write_text(target: Path, content: str):
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(target.parent), prefix=f".{target.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, target)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


# ---------------------------------------------------------------------------
# Semantic Polarity Axes (Deterministic Tier-0 Semantic Contradiction Matrix)
# ---------------------------------------------------------------------------
SEMANTIC_AXES = [
    {
        "axis_id": "tone_register",
        "axis_name": "文体・語尾スタンス（敬体 vs 常体・タメ口）",
        "pole_a_label": "敬体・丁寧調（です・ます調）",
        "pole_a_patterns": [r"です[・/]?ます", r"敬語", r"丁寧な?(?:言葉|口調|文体|表現)", r"ですます調"],
        "pole_b_label": "常体・断定・フランク調（だ・である / タメ口）",
        "pole_b_patterns": [r"だ[・/]?である", r"タメ口", r"フランクな?(?:口調|文体|言葉|短文)", r"言い切(?:り|る)", r"敬語(?:は)?(?:禁止|不要|NG|やめ)"],
        "context_hint": "対外文書・礼節モードは『です・ます（敬語）』、Xや開発壁打ちは『フランク・短文』など場面分けが可能",
    },
    {
        "axis_id": "length_vs_explanation",
        "axis_name": "出力密度・解説スタンス（前置き全廃・1〜3行即答 vs 各パーツの丁寧な教育解説）",
        "pole_a_label": "Token-Zero・前置き全廃・1〜3行ダイレクト即答",
        "pole_a_patterns": [r"1〜3行", r"短く", r"短文で", r"一言で", r"結論だけ", r"前置き.*全廃", r"長文(?:は)?(?:禁止|NG|不要|やめ)", r"簡潔に"],
        "pole_b_label": "各パーツの仕組み・背景・ストーリーまで必ず教育解説",
        "pole_b_patterns": [r"長文で", r"詳しく解説", r"背景から丁寧に?", r"ストーリーを(?:交えて|入れて)", r"各パーツが何をしているかを.*必ず説明", r"育てる教育.*として行う", r"徹底的に解説"],
        "context_hint": "通常の実装・コマンド実行は『Token-Zero（前置き全廃・最小出力）』、新しい概念の相談時のみ『教育解説』など場面分けが可能",
    },
    {
        "axis_id": "structure_format",
        "axis_name": "文章構造（箇条書き・表による構造化 vs 箇条書き排除・連続散文）",
        "pole_a_label": "箇条書き・表・ステップ構造化を優先",
        "pole_a_patterns": [r"箇条書き[でや、]", r"テーブルで", r"表で整理", r"ステップごとに", r"構造化解説"],
        "pole_b_label": "箇条書き・太字・記号を排した連続散文（Prose / 手紙調）",
        "pole_b_patterns": [r"箇条書き.*(?:禁止|NG|使わない|やめ|排除|排し)", r"連続散文", r"手紙調", r"エッセイ調", r"太字.*(?:禁止|NG|使わない|排し)"],
        "context_hint": "技術設計・レビューは『箇条書き・表』、SNS発信・コラム・対外文書は『箇条書きを排した連続散文』など場面分けが可能",
    },
    {
        "axis_id": "autonomy_vs_l0_gate",
        "axis_name": "承認ゲートと自律実行の範囲（一度の承認で継続自律実行 vs 毎回人間承認必須）",
        "pole_a_label": "一度承認した同種アクションは以降の確認なしで自律実行",
        "pole_a_patterns": [r"一度の承認で以降の自律実行", r"バッチ承認", r"確認せず(?:に)?実行", r"自動で進めて"],
        "pole_b_label": "重要操作（force_l0：決済・契約・デプロイ・外部公開）は毎回必ず人間承認",
        "pole_b_patterns": [r"人間承認なしに実行しない", r"必ず人間の明示承認", r"都度承認を(?:求める|得る)"],
        "context_hint": "通常のローカル開発・リサーチは『一度の承認で自律完遂』、本番デプロイ・外部送信・課金（force_l0）のみ『都度人間承認』など明確化が可能",
    },
    {
        "axis_id": "emoji_decoration",
        "axis_name": "絵文字・感嘆符・装飾記号の使用ルール",
        "pole_a_label": "絵文字・記号を使う（親しみやすさ・視覚的フック重視）",
        "pole_a_patterns": [r"絵文字を(?:入れて|使って|追加)", r"親しみやすく絵文字", r"[🔥✨💡🚀]を(?:入れて|使う)"],
        "pole_b_label": "絵文字・感嘆符・AIっぽい装飾記号を禁止",
        "pole_b_patterns": [r"絵文字(?:は)?(?:禁止|NG|使わない|不要|やめ)", r"記号(?:は)?(?:禁止|NG|使わない|排し)", r"感嘆符(?:は)?(?:禁止|NG|使わない)"],
        "context_hint": "SNSやLINE配信と、硬派なコラム・コード規約のどちらに適用するか整理が必要",
    },
    {
        "axis_id": "stance_assertiveness",
        "axis_name": "読者・相手へのスタンス（強い断定・号令 vs 共感・問いかけ）",
        "pole_a_label": "強い断定・言い切り・リーダーシップ号令",
        "pole_a_patterns": [r"断言して", r"言い切って", r"強い言葉で", r"曖昧にしない", r"スパッと"],
        "pole_b_label": "断定を避けた共感・問いかけ・寄り添い重視",
        "pole_b_patterns": [r"断定(?:は)?(?:禁止|NG|しない|やめ)", r"押し付け(?:ない|ず)", r"寄り添(?:う|って)", r"選択に委ねて締める"],
        "context_hint": "問題提起は『強い断定』、結び（CTA）は『読者への問いかけ』などハイブリッド化が可能",
    },
    {
        "axis_id": "technical_granularity",
        "axis_name": "専門用語・抽象度レベル（専門的・厳密 vs 高校生/初心者向け平易表現）",
        "pole_a_label": "専門用語・フレームワーク・厳密な定義を使用",
        "pole_a_patterns": [r"専門用語で", r"技術的に厳密", r"アーキテクチャ用語", r"エキスパート・業界の権威"],
        "pole_b_label": "専門用語を排し、中学生・高校生でもわかる平易な比喩で説明",
        "pole_b_patterns": [r"専門用語(?:は)?(?:禁止|NG|使わない|やめ)", r"(?:中学生|高校生|小学生|初心者)(?:にも|でも)わかる", r"平易な言葉で", r"横文字(?:は)?(?:禁止|NG|使わない)"],
        "context_hint": "エンジニア向け設計と、一般読者・SNS・クライアント向け解説の使い分けルール化が可能",
    },
]

AFFIRMATIVE_MARKERS = ("必ず", "使う", "使って", "入れる", "入れて", "推奨", "重視", "優先", "にする", "で書いて", "してほしい")
NEGATIVE_MARKERS = ("禁止", "NG", "使わない", "入れない", "やめて", "不要", "ダメ", "廃止", "控える", "避ける")


def load_contradictions_state() -> dict:
    if CONTRADICTIONS_STATE_FILE.exists():
        try:
            return json.loads(CONTRADICTIONS_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "last_daily_check": "",
        "last_scan_timestamp": "",
        "items": [],
        "resolved_rules": [],
    }


def save_contradictions_state(state: dict):
    atomic_write_text(CONTRADICTIONS_STATE_FILE, json.dumps(state, ensure_ascii=False, indent=2))


def collect_candidate_statements(vault_dir: Path = VAULT_DIR) -> list:
    """
    Collects normative rules, style feedback, persona seeds, and explicit correction utterances.
    Returns a list of dicts: {text, source, date, category}
    """
    statements = []
    seen_texts = set()

    def add_stmt(text: str, source: str, date_str: str, category: str = "rule"):
        clean = re.sub(r"\s+", " ", text).strip(" -*•「」『』")
        if len(clean) < 6 or len(clean) > 300:
            return
        key = clean[:80]
        if key in seen_texts:
            return
        seen_texts.add(key)
        statements.append({
            "text": clean,
            "source": source,
            "date": date_str or datetime.now().strftime("%Y-%m-%d"),
            "category": category,
        })

    # 1. From persona_learning_state.json
    l_file = vault_dir / "memory" / "persona_learning_state.json"
    if l_file.exists():
        try:
            l_data = json.loads(l_file.read_text(encoding="utf-8"))
            for c in l_data.get("learned_corrections", []):
                add_stmt(
                    c.get("rule", ""),
                    f"{c.get('provider', 'chat').upper()} ({c.get('session_id', '')})",
                    c.get("date", ""),
                    "correction",
                )
            for fb in l_data.get("feedback_memories", []):
                add_stmt(
                    fb.get("summary", ""),
                    f"Memory ({fb.get('file', '')})",
                    fb.get("date", ""),
                    "feedback",
                )
            for bp in l_data.get("dynamic_banned_phrases", []):
                if bp and len(bp) >= 2:
                    add_stmt(f"「{bp}」という表現は禁止（NGワード）", "Dynamic Slop Gate", datetime.now().strftime("%Y-%m-%d"), "banned_phrase")
        except Exception:
            pass

    # 2. From PERSONA_SEEDS.md
    seeds_file = vault_dir / "memory" / "PERSONA_SEEDS.md"
    if seeds_file.exists():
        try:
            s_date = datetime.fromtimestamp(seeds_file.stat().st_mtime).strftime("%Y-%m-%d")
            for line in seeds_file.read_text(encoding="utf-8", errors="ignore").splitlines():
                if line.strip().startswith("- "):
                    add_stmt(line.strip()[2:], "PERSONA_SEEDS.md", s_date, "seed")
        except Exception:
            pass

    # 3. From *PERSONA_CORE.md (bullet & numbered normative lines)
    normative_tokens = AFFIRMATIVE_MARKERS + NEGATIVE_MARKERS + (
        "調", "文体", "行", "箇条書き", "散文", "絵文字", "禁止", "のみ", "必須", "排除", "短文", "長文", "敬語", "タメ口", "構造化", "解説"
    )
    for c_file in sorted((vault_dir / "memory").glob("*PERSONA_CORE.md")):
        core_name = c_file.name
        if c_file.exists():
            try:
                c_date = datetime.fromtimestamp(c_file.stat().st_mtime).strftime("%Y-%m-%d")
                raw = c_file.read_text(encoding="utf-8", errors="ignore")
                main_part = raw.split("## 🔄 5.")[0]
                for line in main_part.splitlines():
                    s_line = re.sub(r"^(?:[-*•]|\d+\.)\s+", "", line.strip())
                    if s_line != line.strip() and any(m in s_line for m in normative_tokens):
                        add_stmt(s_line, core_name, c_date, "persona_core")
            except Exception:
                pass

    # 4. From AGENTS.md / CLAUDE.md in workspace if present
    for doc_p in (HOME_DIR / "Claude" / "AGENTS.md", HOME_DIR / "Claude" / "CLAUDE.md"):
        if doc_p.exists():
            try:
                d_date = datetime.fromtimestamp(doc_p.stat().st_mtime).strftime("%Y-%m-%d")
                for line in doc_p.read_text(encoding="utf-8", errors="ignore").splitlines():
                    s_line = re.sub(r"^(?:[-*•]|\d+\.)\s+", "", line.strip())
                    if s_line != line.strip() and any(m in s_line for m in normative_tokens):
                        add_stmt(s_line, doc_p.name, d_date, "agent_contract")
            except Exception:
                pass

    # 5. From Obsidian wiki/cases/, crm/, and Claude feedback_*.md full bodies
    extra_dirs = [
        ("wiki/cases", vault_dir / "wiki" / "cases"),
        ("crm", vault_dir / "crm"),
        ("claude-memory", HOME_DIR / ".claude" / "memory"),
    ]
    if (HOME_DIR / ".claude" / "projects").exists():
        for pm in sorted((HOME_DIR / ".claude" / "projects").glob("*/memory"), key=lambda p: p.stat().st_mtime, reverse=True)[:4]:
            extra_dirs.append((f"claude-proj/{pm.parent.name[-18:]}", pm))

    for label, d_path in extra_dirs:
        if d_path.exists():
            for md_p in sorted(d_path.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:15]:
                if md_p.name in ("MEMORY.md", "MEMORY_ARCHIVE.md", "index.md"):
                    continue
                try:
                    m_date = datetime.fromtimestamp(md_p.stat().st_mtime).strftime("%Y-%m-%d")
                    raw_md = re.sub(r"^---\n.*?\n---\n", "", md_p.read_text(encoding="utf-8", errors="ignore"), flags=re.DOTALL)
                    for line in raw_md.splitlines():
                        s_line = re.sub(r"^(?:[-*•]|\d+\.)\s+", "", line.strip())
                        if len(s_line) >= 12 and any(m in s_line for m in normative_tokens + ("稼働中", "停止中", "合意済", "未合意")):
                            add_stmt(s_line, f"{label}/{md_p.name}", m_date, "vault_note")
                except Exception:
                    pass

    return statements


def make_contradiction_id(axis_or_topic: str, text_a: str, text_b: str) -> str:
    pair = sorted([text_a[:60], text_b[:60]])
    raw = f"{axis_or_topic}::{pair[0]}::{pair[1]}"
    return "contra-" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]


STATUS_CONFLICT_PAIRS = [
    ("稼働中・有効", (r"稼働中", r"有効化済", r"アクティブ", r"本番稼働"), "停止中・無効", (r"停止中", r"無効化", r"廃止済", r"凍結中")),
    ("合意済・締結済", (r"合意済", r"契約締結済", r"確定済", r"承認済"), "未合意・未決", (r"未合意", r"未決", r"要確認", r"未締結")),
    ("自動化・無人運用", (r"完全自動", r"全自動", r"無人運用"), "手動・人間承認必須", (r"手動で", r"人間承認なしに.*しない", r"手動操作が必要")),
]


def detect_semantic_contradictions(vault_dir: Path = VAULT_DIR) -> list:
    """
    Detects semantic contradictions across collected normative statements:
    1. Semantic Axis Polarity Contradictions (6 core axes)
    2. Direct Topic Affirmative vs. Negative Collisions (shared 2-6 kanji/katakana subject with opposite polarity)
    3. Entity / Project Status Polarity Contradictions (e.g. active vs stopped, agreed vs unagreed on same subject)
    """
    statements = collect_candidate_statements(vault_dir=vault_dir)
    detected = []
    seen_ids = set()

    # Pass 1: Check 6 Semantic Polarity Axes
    for axis in SEMANTIC_AXES:
        pole_a_hits = []
        pole_b_hits = []
        for st in statements:
            txt = st["text"]
            matched_a = any(re.search(pat, txt) for pat in axis["pole_a_patterns"])
            matched_b = any(re.search(pat, txt) for pat in axis["pole_b_patterns"])
            if matched_a and matched_b:
                continue
            if matched_a:
                pole_a_hits.append(st)
            elif matched_b:
                pole_b_hits.append(st)

        if pole_a_hits and pole_b_hits:
            st_a = pole_a_hits[0]
            st_b = pole_b_hits[0]
            cid = make_contradiction_id(axis["axis_id"], st_a["text"], st_b["text"])
            if cid not in seen_ids:
                seen_ids.add(cid)
                detected.append({
                    "id": cid,
                    "type": "semantic_axis",
                    "axis_id": axis["axis_id"],
                    "title": axis["axis_name"],
                    "statement_a": {
                        "pole": axis["pole_a_label"],
                        "text": st_a["text"],
                        "source": st_a["source"],
                        "date": st_a["date"],
                    },
                    "statement_b": {
                        "pole": axis["pole_b_label"],
                        "text": st_b["text"],
                        "source": st_b["source"],
                        "date": st_b["date"],
                    },
                    "reason": f"「{axis['pole_a_label']}」を求める指示と、「{axis['pole_b_label']}」を求める指示が両方存在しており、AIが出力時に迷う原因になります。",
                    "context_hint": axis["context_hint"],
                })

    # Pass 2: Direct Topic Polarity Collisions (Affirmative vs. Negative on the same concept)
    stop_subjects = {
        "ファイル", "フォルダ", "プロジェクト", "エラー", "コード", "スクリプト", "システム",
        "確認", "実行", "修正", "作成", "追加", "変更", "設定", "対応", "必要", "現在", "今回",
        "表現", "言葉", "文章", "ルール", "場合", "内容", "すべて", "これ", "それ", "判断", "理由"
    }
    topic_affirmative = {}
    topic_negative = {}

    for st in statements:
        txt = st["text"]
        is_neg = any(neg in txt for neg in NEGATIVE_MARKERS)
        is_aff = any(aff in txt for aff in AFFIRMATIVE_MARKERS) and not is_neg
        if not (is_neg or is_aff):
            continue
        subjects = re.findall(r"[「『]([^「」『』]{2,16})[」』]", txt)
        if not subjects:
            subjects = [w for w in re.findall(r"[一-龥]{2,6}|[ァ-ヴー]{3,8}", txt) if w not in stop_subjects]
        for subj in subjects[:3]:
            subj = subj.strip()
            if len(subj) < 2 or subj in stop_subjects:
                continue
            if is_aff and subj not in topic_affirmative:
                topic_affirmative[subj] = st
            elif is_neg and subj not in topic_negative:
                topic_negative[subj] = st

    for subj, st_a in topic_affirmative.items():
        if subj in topic_negative:
            st_b = topic_negative[subj]
            if st_a["text"] == st_b["text"] or st_a["source"] == st_b["source"]:
                continue
            cid = make_contradiction_id(f"topic_{subj}", st_a["text"], st_b["text"])
            if cid not in seen_ids:
                seen_ids.add(cid)
                detected.append({
                    "id": cid,
                    "type": "topic_polarity",
                    "axis_id": f"topic_{subj}",
                    "title": f"「{subj}」に関する肯定ルールと禁止ルールの衝突",
                    "statement_a": {
                        "pole": f"「{subj}」を肯定・推奨",
                        "text": st_a["text"],
                        "source": st_a["source"],
                        "date": st_a["date"],
                    },
                    "statement_b": {
                        "pole": f"「{subj}」を禁止・否定",
                        "text": st_b["text"],
                        "source": st_b["source"],
                        "date": st_b["date"],
                    },
                    "reason": f"同一テーマ「{subj}」に対して、使うべきとする指示と禁止する指示が衝突しています。",
                    "context_hint": f"「{subj}」を全面採用するか、全面禁止にするか、または特定の媒体のみ許可するかを選択してください。",
                })

    # Pass 3: Entity / Project Status Polarity Contradictions
    for label_a, pats_a, label_b, pats_b in STATUS_CONFLICT_PAIRS:
        subj_a = {}
        subj_b = {}
        for st in statements:
            txt = st["text"]
            has_a = any(re.search(p, txt) for p in pats_a)
            has_b = any(re.search(p, txt) for p in pats_b)
            if has_a and has_b:
                continue
            entities = [w for w in re.findall(r"[一-龥]{2,6}|[ァ-ヴー]{3,8}|[A-Za-z0-9_-]{3,15}", txt) if w not in stop_subjects]
            for ent in entities[:2]:
                if has_a and ent not in subj_a:
                    subj_a[ent] = st
                elif has_b and ent not in subj_b:
                    subj_b[ent] = st
        for ent, st_a in subj_a.items():
            if ent in subj_b:
                st_b = subj_b[ent]
                if st_a["text"] == st_b["text"] or st_a["source"] == st_b["source"]:
                    continue
                cid = make_contradiction_id(f"status_{ent}", st_a["text"], st_b["text"])
                if cid not in seen_ids:
                    seen_ids.add(cid)
                    detected.append({
                        "id": cid,
                        "type": "status_conflict",
                        "axis_id": f"status_{ent}",
                        "title": f"「{ent}」のステータス・状態に関する記憶の矛盾（{label_a} vs {label_b}）",
                        "statement_a": {
                            "pole": label_a,
                            "text": st_a["text"],
                            "source": st_a["source"],
                            "date": st_a["date"],
                        },
                        "statement_b": {
                            "pole": label_b,
                            "text": st_b["text"],
                            "source": st_b["source"],
                            "date": st_b["date"],
                        },
                        "reason": f"「{ent}」について、「{label_a}」とする記録と「{label_b}」とする記録が混在しています。",
                        "context_hint": f"最新の正しい状態（{label_a} または {label_b}）を選択してください。",
                    })

    return detected


# ---------------------------------------------------------------------------
# Value Priority & Trade-Off Alignment Axes (Daily Value Hierarchy Builder)
# ---------------------------------------------------------------------------
VALUE_PRIORITY_AXES = [
    {
        "id": "val-vision-vs-cashflow",
        "axis_id": "val_vision_vs_cashflow",
        "type": "value_priority",
        "title": "【価値観の優先順位 #1】長期の大義・物語 vs 今日の一点突破・足元の売上",
        "statement_a": {
            "pole": "大義・長期ビジョン・心が震える物語の構築を最優先",
            "text": "日本と日本人が失った誇りと絆を取り戻す大義・世界観・生まれ変わりの旅などの長期構想に時間と熱量を注ぐ。",
            "source": "Value Axis (Vision)",
            "date": "Core Value",
        },
        "statement_b": {
            "pole": "足元のキャッシュフロー・1日1テーマの一点突破を最優先",
            "text": "大義は後でいい、まず今日の売上と目の前の1打（キャッシュフロー直結の1タスク完遂）を最優先で片付ける。",
            "source": "Value Axis (Execution)",
            "date": "Core Value",
        },
        "reason": "両方とも大切な価値観ですが、1日の限られた時間・エネルギーが衝突したとき、AIがどちらを優先してスケジュールやタスクを提案すべきかの基準になります。",
        "context_hint": "例：午前中（または最初の2時間）は必ず『B（キャッシュフロー直結の一点突破）』を完遂し、その後に『A（長期ビジョン・大義）』へ時間を使う、など順序・比率で定義可能",
    },
    {
        "id": "val-automation-vs-process",
        "axis_id": "val_automation_vs_process",
        "type": "value_priority",
        "title": "【価値観の優先順位 #2】AIによる0秒の自動化・効率 vs 人間が歩む泥臭いプロセス・体温",
        "statement_a": {
            "pole": "AIによる徹底自動化・最速の仕組み化（手作業ゼロ）",
            "text": "反復作業や2〜8の実務は徹底的にAIと仕組みに任せ、最短・最小コストで結果を出す。",
            "source": "Value Axis (Automation)",
            "date": "Core Value",
        },
        "statement_b": {
            "pole": "人間が自分の足で悩み・歩むプロセスと体温の聖域化",
            "text": "結果が0秒で出る時代だからこそ、仲間と歩む道中（プロセス）や生の言葉・体温を何より大切にする。",
            "source": "Value Axis (Human Process)",
            "date": "Core Value",
        },
        "reason": "AI化を進めすぎると人間の体温やプロセス体験が消え、逆に手作業を残しすぎると2〜8に忙殺されるトレードオフがあります。",
        "context_hint": "例：『1（火を灯す構想・原体験・対話）』と『9（最後の魂込め・思想統合）』はB（人間の聖域）として絶対に手放さず、間の『2〜8（集計・下書き・配線）』はA（100%自動化）を最優先する",
    },
    {
        "id": "val-tolerance-vs-boundary",
        "axis_id": "val_tolerance_vs_boundary",
        "type": "value_priority",
        "title": "【価値観の優先順位 #3】寛容・寄り添う愛 vs 甘えを許さない厳格な境界線（力愛不二）",
        "statement_a": {
            "pole": "寛容・受容・相手の傷や背景に寄り添う慈愛を優先",
            "text": "人の弱さや挫折を包み込み、相手が自分の足で立ち上がるまで寛容に信じて待つ。",
            "source": "Value Axis (Tolerance / Love)",
            "date": "Core Value",
        },
        "statement_b": {
            "pole": "厳格な境界線・精神論を排した仕組みと責任の徹底を優先",
            "text": "「頑張ります」等の精神論や不誠実・契約違反には曖昧な妥協を許さず、冷徹に構造と境界線を引く。",
            "source": "Value Axis (Boundary / Power)",
            "date": "Core Value",
        },
        "reason": "対人コミュニケーションやSNS発信、クライアント対応において、優しさ（寛容）と厳しさ（境界線）のどちらを第一順位に置くかの判断基準になります。",
        "context_hint": "例：挑戦して傷ついた人や誠実な仲間には『A（100%の寛容と伴走）』、精神論での言い訳や不誠実・搾取構造には『B（即座に境界線を引き仕組みで正す）』と相手・状況で優先順位を切り替える",
    },
    {
        "id": "val-speed-vs-perfection",
        "axis_id": "val_speed_vs_perfection",
        "type": "value_priority",
        "title": "【価値観の優先順位 #4】圧倒的スピード（まず世に出す） vs 証拠主義・100%の品質検証",
        "statement_a": {
            "pole": "スピード・即実装・今日中に形にして回す突破力を優先",
            "text": "完璧主義で止まるくらいなら、最小構成（MVP）で今日中に動かして現場で改善する。",
            "source": "Value Axis (Speed)",
            "date": "Core Value",
        },
        "statement_b": {
            "pole": "証拠主義・テスト合格・抜け漏れゼロの品質保証を優先",
            "text": "「動くはず」での完了宣言を禁じ、必ず検証ログとエッジケース確認が揃うまで世に出さない。",
            "source": "Value Axis (Evidence & Quality)",
            "date": "Core Value",
        },
        "reason": "開発やコンテンツ制作で「まず速く出す」か「徹底検証してから出す」かのトレードオフ判断に直結します。",
        "context_hint": "例：社内プロトタイプ・SNS下書き・壁打ちは『A（スピード最優先）』、顧客納品・決済・本番デプロイ・契約関連は『B（100%の証拠と検証完了が絶対条件）』とする",
    },
    {
        "id": "val-authenticity-vs-reach",
        "axis_id": "val_authenticity_vs_reach",
        "type": "value_priority",
        "title": "【価値観の優先順位 #5】本質・こだわりの純度（深さ） vs 初心者にも伝わる平易さ（広さ）",
        "statement_a": {
            "pole": "自分の言葉の純度・哲学の深さ・本質へのこだわりを最優先",
            "text": "大衆ウケやバズのために言葉を薄めず、本当に届けたい誇り高き仲間に深く刺さる純度を保つ。",
            "source": "Value Axis (Authenticity)",
            "date": "Core Value",
        },
        "statement_b": {
            "pole": "高校生・初心者にも一読で伝わるわかりやすさ・入り口の広さを最優先",
            "text": "専門用語や抽象的な概念を噛み砕き、誰でも直感的に理解できる比喩と平易な言葉に変換する。",
            "source": "Value Axis (Accessibility)",
            "date": "Core Value",
        },
        "reason": "SNS発信やLP・講座作成で、「思想の深さ」と「わかりやすさ」のどちらを優先して表現を調整すべきかの基準になります。",
        "context_hint": "例：『核となる思想・ミッション（何を言うか）』はA（純度100%で一切妥協しない）、『伝える表現・比喩（どう言うか）』はB（高校生でもわかる具体例・物語で包む）とする",
    },
]


def ensure_daily_value_priority_question(state: dict, vault_dir: Path = VAULT_DIR) -> int:
    """
    Ensures that at least 1 unranked Value Priority trade-off question is active in `state["items"]`
    so the daily task asks the user about their value hierarchy alongside any contradictions.
    Returns number of newly queued value questions (0 or 1).
    """
    items = state.setdefault("items", [])
    pending_values = [i for i in items if i.get("type") == "value_priority" and i.get("status") == "pending"]
    if pending_values:
        return 0

    existing_ids = {i.get("id") for i in items}
    existing_axes = {i.get("axis_id") for i in items}
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for v_axis in VALUE_PRIORITY_AXES:
        if v_axis["id"] not in existing_ids and v_axis["axis_id"] not in existing_axes:
            q_item = dict(v_axis)
            q_item["status"] = "pending"
            q_item["detected_at"] = now_str
            q_item["resolution_choice"] = None
            q_item["resolution_note"] = ""
            items.append(q_item)
            return 1

    # If all 5 core value axes have been answered, dynamically synthesize a new trade-off pair from top discovered concepts
    l_file = vault_dir / "memory" / "persona_learning_state.json"
    if l_file.exists():
        try:
            l_data = json.loads(l_file.read_text(encoding="utf-8"))
            concepts = [k for k in l_data.get("concept_frequencies", {}).keys() if len(k) >= 2]
            for i in range(0, len(concepts) - 1, 2):
                c1, c2 = concepts[i], concepts[i + 1]
                dyn_id = f"val-dyn-{hashlib.sha1(f'{c1}:{c2}'.encode('utf-8')).hexdigest()[:6]}"
                if dyn_id not in existing_ids:
                    items.append({
                        "id": dyn_id,
                        "axis_id": dyn_id,
                        "type": "value_priority",
                        "title": f"【価値観の優先順位】「{c1}」 vs 「{c2}」のトレードオフ判断基準",
                        "statement_a": {
                            "pole": f"「{c1}」を最優先",
                            "text": f"判断に迷ったときは「{c1}」を第一優先として意思決定・時間配分を行う。",
                            "source": "Dynamic Lexicon",
                            "date": now_str[:10],
                        },
                        "statement_b": {
                            "pole": f"「{c2}」を最優先",
                            "text": f"判断に迷ったときは「{c2}」を第一優先として意思決定・時間配分を行う。",
                            "source": "Dynamic Lexicon",
                            "date": now_str[:10],
                        },
                        "reason": f"対話ログで高頻度に登場する「{c1}」と「{c2}」が競合した際、どちらを上位概念として扱うかの確認です。",
                        "context_hint": f"「{c1}」と「{c2}」の優先順位または役割分担を教えてください。",
                        "status": "pending",
                        "detected_at": now_str,
                        "resolution_choice": None,
                        "resolution_note": "",
                    })
                    return 1
        except Exception:
            pass

    return 0


def scan_and_update_contradictions(vault_dir: Path = VAULT_DIR, notify_macos: bool = False) -> dict:
    """
    Runs semantic contradiction detection + ensures 1 daily Value Priority question is queued,
    writes `memory/CONTRADICTION_INBOX.md`, and optionally fires a daily macOS notification.
    """
    state = load_contradictions_state()
    existing_by_id = {item["id"]: item for item in state.get("items", [])}
    existing_axes = {
        item.get("axis_id"): item
        for item in state.get("items", [])
        if item.get("status") in ("resolved", "dismissed") and item.get("axis_id")
    }

    newly_detected = detect_semantic_contradictions(vault_dir=vault_dir)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    today_str = datetime.now().strftime("%Y-%m-%d")

    merged_items = list(state.get("items", []))
    new_pending_count = 0

    for det in newly_detected:
        cid = det["id"]
        axis_id = det.get("axis_id")
        if cid in existing_by_id:
            continue
        if axis_id and axis_id in existing_axes:
            continue
        det["status"] = "pending"
        det["detected_at"] = now_str
        det["resolution_choice"] = None
        det["resolution_note"] = ""
        merged_items.insert(0, det)
        new_pending_count += 1

    state["last_scan_timestamp"] = now_str
    state["items"] = merged_items
    new_val_count = ensure_daily_value_priority_question(state, vault_dir=vault_dir)
    new_pending_count += new_val_count

    save_contradictions_state(state)
    write_contradiction_inbox_markdown(state, vault_dir=vault_dir)

    pending_items = [i for i in state["items"] if i.get("status") == "pending"]
    pending_contra = [i for i in pending_items if i.get("type") != "value_priority"]
    pending_values = [i for i in pending_items if i.get("type") == "value_priority"]

    if notify_macos and pending_items and state.get("last_daily_check") != today_str:
        state["last_daily_check"] = today_str
        save_contradictions_state(state)
        if platform.system() == "Darwin":
            try:
                msg = f"本日の確認事項（矛盾: {len(pending_contra)}件 / 価値観の優先順位: {len(pending_values)}件）があります。Obsidianまたはチャットで判断を教えてください。"
                subprocess.run(
                    ["osascript", "-e", f'display notification "{msg}" with title "🧠 Cross-AI Memory 日次アライメント"'],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception:
                pass

    return {
        "total_items": len(state["items"]),
        "pending_count": len(pending_items),
        "pending_contra_count": len(pending_contra),
        "pending_value_count": len(pending_values),
        "new_pending_count": new_pending_count,
        "pending_items": pending_items,
        "inbox_path": str(vault_dir / "memory" / "CONTRADICTION_INBOX.md"),
    }


def write_contradiction_inbox_markdown(state: dict, vault_dir: Path = VAULT_DIR) -> Path:
    inbox_path = vault_dir / "memory" / "CONTRADICTION_INBOX.md"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    pending = [i for i in state.get("items", []) if i.get("status") == "pending"]
    pending_contra = [i for i in pending if i.get("type") != "value_priority"]
    pending_values = [i for i in pending if i.get("type") == "value_priority"]
    resolved = [i for i in state.get("items", []) if i.get("status") == "resolved"]

    md = f"""---
title: "意味上の矛盾 ＆ 価値観の優先順位インボックス (Contradiction & Value Hierarchy Inbox)"
updated: "{now_str}"
pending_contradictions: {len(pending_contra)}
pending_value_questions: {len(pending_values)}
resolved_count: {len(resolved)}
tags: [memory, contradiction-check, value-hierarchy, governance, self-improving]
---

# ⚖️ 意味上の矛盾 ＆ 👑 価値観の優先順位インボックス (`CONTRADICTION_INBOX`)

> **最終スキャン日時**: `{now_str}`
> **未解決の矛盾**: **`{len(pending_contra)} 件`** ｜ **本日の価値観・優先順位クエスチョン**: **`{len(pending_values)} 件`** ｜ **確定済み判断軸**: `{len(resolved)} 件`
> **連携先**: [[SHARED_MEMORY]] | [[PERSONA_CORE]] | [[Knowledge_Atlas.base]]

---

## 🔔 1. いま判断を仰ぎたい「意味上の矛盾 ＆ 価値観の優先順位」（未回答: {len(pending)}件）

"""
    if not pending:
        md += "✅ **現在、未解決の矛盾および未回答の価値観クエスチョンはありません。すべての記憶・価値観ヒエラルキーが整合しています。**\n\n"
    else:
        md += "以下の項目について、**Aを最優先にするか・Bを最優先にするか・または順序/場面分け（BOTH）で統合するか** を教えてください。\n"
        md += "ターミナルで `ai-memory contradictions --ask` を実行するか、普段のAIチャットでそのまま回答するだけで自動反映されます。\n\n"
        for idx, item in enumerate(pending, 1):
            sa = item["statement_a"]
            sb = item["statement_b"]
            badge = "👑 [価値観の優先順位]" if item.get("type") == "value_priority" else "❓ [意味上の矛盾]"
            md += f"""### {badge} #{idx}: {item['title']} (`ID: {item['id']}`)
- **背景・問いの理由**: {item['reason']}
- **🅰️ 選択肢A（{sa['pole']}）**
  - 内容: 「{sa['text']}」
- **🅱️ 選択肢B（{sb['pole']}）**
  - 内容: 「{sb['text']}」
- **💡 統合・優先順位づけのヒント**: {item.get('context_hint', '')}
- **解決コマンド**:
  - Aを最優先にする: `ai-memory contradictions --resolve {item['id']} --choice A`
  - Bを最優先にする: `ai-memory contradictions --resolve {item['id']} --choice B`
  - 順序・場面分けで統合する: `ai-memory contradictions --resolve {item['id']} --choice BOTH --note "{item.get('context_hint', '')}"`

---

"""

    val_resolved = [r for r in resolved if r.get("type") == "value_priority"]
    con_resolved = [r for r in resolved if r.get("type") != "value_priority"]

    md += f"## 👑 2. 確定した「価値観の優先順位・トレードオフ判断基準」（{len(val_resolved)}件）\n\n"
    if not val_resolved:
        md += "- まだ確定した価値観優先順位はありません（上のクエスチョンに回答するとここに刻印されます）。\n\n"
    else:
        for r in val_resolved:
            md += f"- **`[{r.get('resolved_at', '')[:10]}]`** **{r['title']}** (`{r['id']}`)\n"
            md += f"  - **確定優先順位**: {r.get('resolution_summary', '')}\n"
        md += "\n"

    md += f"## ✅ 3. 解決済みの「意味上の矛盾」判断ログ（直近 {min(len(con_resolved), 15)}件）\n\n"
    if not con_resolved:
        md += "- まだ解決済みの履歴はありません。\n"
    else:
        for r in con_resolved[:15]:
            md += f"- **`[{r.get('resolved_at', '')[:10]}]`** **{r['title']}** (`{r['id']}`)\n"
            md += f"  - **確定判断**: `{r.get('resolution_choice')}` — {r.get('resolution_summary', '')}\n"

    atomic_write_text(inbox_path, md)
    return inbox_path


def resolve_contradiction(
    contra_id: str,
    choice: str,
    custom_note: str = "",
    vault_dir: Path = VAULT_DIR,
) -> dict:
    """
    Applies the user's judgment (`A`, `B`, `BOTH`, or `DISMISS`) for a contradiction or value-priority ID:
    1. Marks the item as resolved in `contradictions_state.json`.
    2. Updates `persona_learning_state.json`, `CONTRADICTION_INBOX.md`, `PERSONA_CORE.md`, and `SHARED_MEMORY.md`.
    """
    state = load_contradictions_state()
    choice_up = choice.upper().strip()
    target = None
    for item in state.get("items", []):
        if item["id"] == contra_id or item["id"].endswith(contra_id):
            target = item
            break

    if not target:
        raise ValueError(f"ID '{contra_id}' not found.")

    sa = target["statement_a"]
    sb = target["statement_b"]
    is_val = target.get("type") == "value_priority"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if choice_up == "A":
        if is_val:
            summary = f"【Aを最優先】「{sa['pole']}」＞「{sb['pole']}」の優先順位で意思決定する。"
            discard_text = None
        else:
            summary = f"【Aを採用】「{sa['pole']}」（{sa['text'][:60]}）を正本とし、B（「{sb['text'][:40]}」）を無効化。"
            discard_text = sb["text"]
    elif choice_up == "B":
        if is_val:
            summary = f"【Bを最優先】「{sb['pole']}」＞「{sa['pole']}」の優先順位で意思決定する。"
            discard_text = None
        else:
            summary = f"【Bを採用】「{sb['pole']}」（{sb['text'][:60]}）を正本とし、A（「{sa['text'][:40]}」）を無効化。"
            discard_text = sa["text"]
    elif choice_up == "BOTH":
        note_txt = custom_note.strip() or target.get("context_hint", "文脈・順序に応じて両立")
        label_prefix = "【順序・役割分担で統合】" if is_val else "【場面分けで両方維持】"
        summary = f"{label_prefix}{note_txt}（A: {sa['pole']} ／ B: {sb['pole']}）"
        discard_text = None
    elif choice_up == "DISMISS":
        summary = "【対象外として除外】ユーザー判断によりスキップ。"
        discard_text = None
    else:
        raise ValueError(f"Invalid choice '{choice}'. Must be A, B, BOTH, or DISMISS.")

    if custom_note and choice_up in ("A", "B"):
        summary += f" (補足基準: {custom_note.strip()})"

    target["status"] = "dismissed" if choice_up == "DISMISS" else "resolved"
    target["resolution_choice"] = choice_up
    target["resolution_note"] = custom_note.strip()
    target["resolution_summary"] = summary
    target["resolved_at"] = now_str

    entry_record = {
        "id": target["id"],
        "type": target.get("type", "semantic_axis"),
        "title": target["title"],
        "choice": choice_up,
        "summary": summary,
        "date": now_str[:10],
    }
    if is_val:
        state.setdefault("value_hierarchy", []).insert(0, entry_record)
    else:
        state.setdefault("resolved_rules", []).insert(0, entry_record)

    save_contradictions_state(state)

    # Update persona_learning_state.json
    l_file = vault_dir / "memory" / "persona_learning_state.json"
    if l_file.exists():
        try:
            l_data = json.loads(l_file.read_text(encoding="utf-8"))
            if discard_text:
                l_data["learned_corrections"] = [
                    c for c in l_data.get("learned_corrections", [])
                    if discard_text[:30] not in c.get("rule", "")
                ]
                l_data["feedback_memories"] = [
                    f for f in l_data.get("feedback_memories", [])
                    if discard_text[:30] not in f.get("summary", "")
                ]
            if choice_up in ("A", "B", "BOTH"):
                l_data.setdefault("learned_corrections", []).insert(0, {
                    "date": now_str[:10],
                    "provider": "value-hierarchy" if is_val else "user-verified",
                    "rule": f"{target['title']}: {summary}",
                    "session_id": target["id"],
                })
            atomic_write_text(l_file, json.dumps(l_data, ensure_ascii=False, indent=2))
        except Exception:
            pass

    write_contradiction_inbox_markdown(state, vault_dir=vault_dir)

    # Re-sync Persona Core & Shared Memory
    try:
        from persona_extractor import sync_persona_engine
        sync_persona_engine(verbose=False)
    except Exception:
        pass
    try:
        from compiler import compile_shared_memory
        compile_shared_memory()
    except Exception:
        pass

    return target


def format_contradictions_for_shared_memory(vault_dir: Path = VAULT_DIR) -> str:
    """
    Returns a Markdown block for `SHARED_MEMORY.md`.
    Includes both pending contradictions AND today's Value Priority question, plus resolved hierarchies.
    """
    state = load_contradictions_state()
    pending = [i for i in state.get("items", []) if i.get("status") == "pending"]
    val_hierarchy = state.get("value_hierarchy", [])[:7]
    resolved = state.get("resolved_rules", [])[:5]

    lines = [
        "\n---",
        "\n## 7. ⚖️ 意味上の矛盾チェック ＆ 👑 価値観の優先順位ゲート（Daily Alignment Gate）\n",
    ]
    if pending:
        lines.append(
            f"> 🚨 **【AIへの日次必須指示】現在、ユーザーに確認すべき項目（意味上の矛盾 または 価値観の優先順位クエスチョン）が `{len(pending)}件` あります。**\n"
            "> 1日1回、会話の冒頭または区切りでユーザーに以下の問いを提示し、**「Aを最優先にするか・Bを最優先にするか・順序や場面分け（BOTH）で統合するか」**判断を仰いでください。\n"
            "> ユーザーが回答したら、直ちに `ai-memory contradictions --resolve <ID> --choice <A|B|BOTH> --note \"...\"` を実行して正本へ刻印してください。\n"
        )
        for idx, item in enumerate(pending[:3], 1):
            sa = item["statement_a"]
            sb = item["statement_b"]
            tag = "👑 [価値観の優先順位]" if item.get("type") == "value_priority" else "❓ [意味上の矛盾]"
            lines.append(
                f"{idx}. **{tag} `[{item['id']}]` {item['title']}**\n"
                f"   - **🅰️ A ({sa['pole']})**: 「{sa['text']}」\n"
                f"   - **🅱️ B ({sb['pole']})**: 「{sb['text']}」\n"
                f"   - **💡 ヒント**: {item.get('context_hint', '')}"
            )
        lines.append("\n- 詳細ノート: [[CONTRADICTION_INBOX]] (`memory/CONTRADICTION_INBOX.md`)\n")
    else:
        lines.append("- ✅ **未解決の矛盾・未回答の価値観クエスチョン**: `0件`（日次スキャン正常・全ルール整合済 -> [[CONTRADICTION_INBOX]]）\n")

    if val_hierarchy:
        lines.append("### 👑 確定した価値観の優先順位（Value Hierarchy & Trade-Off Rules）")
        for v in val_hierarchy:
            lines.append(f"- **`[{v['date']}]` {v['title']}**: {v['summary']}")
        lines.append("")

    if resolved:
        lines.append("### ⚖️ ユーザー裁定済みの確定優先ルール（Resolved Contradictions）")
        for r in resolved:
            lines.append(f"- **`[{r['date']}]` {r['title']}**: {r['summary']}")
        lines.append("")

    return "\n".join(lines) + "\n"


def run_interactive_ask(vault_dir: Path = VAULT_DIR):
    scan_res = scan_and_update_contradictions(vault_dir=vault_dir, notify_macos=False)
    pending = scan_res["pending_items"]

    print("=" * 72)
    print("⚖️  Cross-AI Memory Hub — 意味上の矛盾 ＆ 👑 価値観の優先順位インタビュー")
    print("=" * 72)
    if not pending:
        print("✅ 現在、未解決の矛盾・未回答の価値観クエスチョンは 0 件です！")
        print(f"📄 確認ノート: {scan_res['inbox_path']}")
        return

    print(f"現在、判断を仰ぎたい項目が {len(pending)} 件（矛盾: {scan_res['pending_contra_count']}件 / 価値観の優先順位: {scan_res['pending_value_count']}件）あります。\n")

    for idx, item in enumerate(pending, 1):
        sa = item["statement_a"]
        sb = item["statement_b"]
        badge = "👑 [価値観の優先順位]" if item.get("type") == "value_priority" else "❓ [意味上の矛盾]"
        print(f"------------------------------------------------------------------------")
        print(f"{badge} [{idx}/{len(pending)}] {item['title']} (ID: {item['id']})")
        print(f"   背景: {item['reason']}")
        print(f"   🅰️ [1] Aを最優先 ({sa['pole']}):")
        print(f"          「{sa['text']}」")
        print(f"   🅱️ [2] Bを最優先 ({sb['pole']}):")
        print(f"          「{sb['text']}」")
        print(f"   🔄 [3] 順序・場面分けで両方統合 ({item.get('context_hint', '文脈に応じて使い分け')})")
        print(f"   ⏭️ [4] スキップ（今は判断しない） / [5] 対象外として除外")
        print(f"------------------------------------------------------------------------")
        try:
            ans = input("👉 番号を選んでください [1=A優先 / 2=B優先 / 3=順序・場面分け / 4=スキップ / 5=除外]: ").strip()
        except EOFError:
            print("\n⚠️ 非対話環境のため中断しました。`ai-memory contradictions --resolve <ID> --choice <A|B|BOTH>` で回答できます。")
            break

        if ans == "1":
            resolve_contradiction(item["id"], "A", vault_dir=vault_dir)
            print("   ✅ Aを最優先ルールとして確定し、Obsidianへ反映しました！\n")
        elif ans == "2":
            resolve_contradiction(item["id"], "B", vault_dir=vault_dir)
            print("   ✅ Bを最優先ルールとして確定し、Obsidianへ反映しました！\n")
        elif ans == "3":
            try:
                note = input(f"   📝 優先順序・使い分けルール（Enterで既定: 『{item.get('context_hint', '')}』）: ").strip()
            except EOFError:
                note = ""
            resolve_contradiction(item["id"], "BOTH", custom_note=note, vault_dir=vault_dir)
            print("   ✅ 順序・場面分けルールとして確定し、Obsidianへ反映しました！\n")
        elif ans == "5":
            resolve_contradiction(item["id"], "DISMISS", vault_dir=vault_dir)
            print("   ⏭️ 対象外として除外しました。\n")
        else:
            print("   ⏭️ スキップしました。\n")


def main():
    parser = argparse.ArgumentParser(description="Semantic Contradiction & Daily Value Priority Resolution Engine")
    parser.add_argument("--scan", action="store_true", help="Scan for semantic contradictions + queue daily value priority question")
    parser.add_argument("--daily-cron", action="store_true", help="Run daily scheduled check with macOS notification")
    parser.add_argument("--ask", action="store_true", help="Interactive Q&A to resolve pending contradictions and value priorities")
    parser.add_argument("--next-value", action="store_true", help="Queue the next unranked Value Priority question immediately")
    parser.add_argument("--resolve", metavar="ID", help="Resolve a specific contradiction or value-priority question by ID")
    parser.add_argument("--choice", choices=["A", "B", "BOTH", "DISMISS", "a", "b", "both", "dismiss"], help="Resolution choice for --resolve")
    parser.add_argument("--note", default="", help="Optional context/priority note when resolving")
    args = parser.parse_args()

    if args.resolve:
        if not args.choice:
            print("❌ Error: --resolve requires --choice <A|B|BOTH|DISMISS>", file=sys.stderr)
            sys.exit(1)
        resolved = resolve_contradiction(args.resolve, args.choice, custom_note=args.note)
        print(f"✅ [{resolved['id']}] ({resolved['title']}) を確定しました！")
        print(f"   確定基準: {resolved['resolution_summary']}")
        return

    if args.next_value:
        state = load_contradictions_state()
        added = ensure_daily_value_priority_question(state, vault_dir=VAULT_DIR)
        save_contradictions_state(state)
        write_contradiction_inbox_markdown(state, vault_dir=VAULT_DIR)
        print(f"👑 新しい価値観・優先順位クエスチョンを {added} 件キューに追加しました。")

    if args.ask:
        run_interactive_ask()
        return

    res = scan_and_update_contradictions(notify_macos=args.daily_cron)
    print(f"⚖️  Daily Contradiction & Value Priority Scan Complete:")
    print(f"   - Pending Contradictions:   {res['pending_contra_count']}")
    print(f"   - Pending Value Questions:  {res['pending_value_count']}")
    print(f"   - Obsidian Inbox Note:      {res['inbox_path']}")
    for item in res["pending_items"]:
        badge = "👑 [価値観の優先順位]" if item.get("type") == "value_priority" else "❓ [意味上の矛盾]"
        print(f"\n   {badge} [{item['id']}] {item['title']}")
        print(f"      🅰️ A ({item['statement_a']['pole']}): 「{item['statement_a']['text']}」")
        print(f"      🅱️ B ({item['statement_b']['pole']}): 「{item['statement_b']['text']}」")
        print(f"      💡 ヒント: {item.get('context_hint', '')}")
        print(f"      👉 回答コマンド: ai-memory contradictions --resolve {item['id']} --choice <A|B|BOTH> --note \"...\"")


if __name__ == "__main__":
    main()
