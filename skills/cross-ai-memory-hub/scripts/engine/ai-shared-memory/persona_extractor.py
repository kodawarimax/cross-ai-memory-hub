#!/usr/bin/env python3
"""
persona_extractor.py - Closed-Loop Self-Improving Persona & SNS Engine.
1. Harvests authentic utterances (使う言葉・反応する言葉・行動する言葉) from all 4 AIs & voice dictations.
2. Mines user corrections / style feedback ("そうじゃなくて", "NG", "違和感", feedback_*.md) to evolve rules.
3. Discovers emerging high-frequency vocabulary & signature phrases dynamically.
4. Synthesizes dynamic SNS drafts (X / Threads / note) and grades them via a Deterministic Slop Gate.
"""

import glob
import json
import os
import re
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path
import tempfile

HOME_DIR = Path.home()
_default_vault = HOME_DIR / "Claude" / "knowledge-empire" if (HOME_DIR / "Claude").exists() else HOME_DIR / "knowledge-empire"
VAULT_DIR = Path(os.environ.get("OBSIDIAN_VAULT", str(_default_vault))).expanduser()
MEMORY_DIR = VAULT_DIR / "memory"
PERSONA_NAME = os.environ.get("PERSONA_NAME", "")
LOCAL_CONFIG_FILE = MEMORY_DIR / "LOCAL_PERSONA_CONFIG.json"


def load_local_persona_config() -> dict:
    if LOCAL_CONFIG_FILE.exists() and not PERSONA_NAME:
        try:
            return json.loads(LOCAL_CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def has_local_canon() -> bool:
    return bool(load_local_persona_config()) or ((MEMORY_DIR / "LOCAL_CANON.md").exists() and not PERSONA_NAME)


def resolve_owner_name() -> str:
    if PERSONA_NAME:
        return PERSONA_NAME
    cfg = load_local_persona_config()
    if cfg.get("owner_name"):
        return cfg["owner_name"]
    return HOME_DIR.name


def resolve_persona_files() -> tuple[Path, Path]:
    cfg = load_local_persona_config()
    c_name = cfg.get("core_filename", "PERSONA_CORE.md")
    v_name = cfg.get("voice_filename", "VOICE_LOG.md")
    return MEMORY_DIR / c_name, MEMORY_DIR / v_name


PERSONA_CORE_FILE, VOICE_LOG_FILE = resolve_persona_files()
SNS_DRAFTS_FILE = MEMORY_DIR / "SNS_READY_DRAFTS.md"
LEARNING_STATE_FILE = MEMORY_DIR / "persona_learning_state.json"
HASSHIN_DRAFTS_FILE = HOME_DIR / "Claude" / "dots" / "hasshin" / "briefs" / "obsidian_persona_drafts.md"
_default_archive_db = (HOME_DIR / "Claude" / "dev" / "ai-chat-archive" / "archive.db") if (HOME_DIR / "Claude" / "dev" / "ai-chat-archive").exists() else (VAULT_DIR / ".ai-hub" / "archive.db")
ARCHIVE_DB = Path(os.environ.get("AI_ARCHIVE_DB", str(_default_archive_db))).expanduser()


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


SKIP_PREFIXES = (
    "#", "<", "Invoke ", "Read ", "You are ", "[CODEX", "System:", "{",
    "Continue", " output", "File Path:", "Created At:", "Traceback", "http://", "https://",
    "Base directory", "This session is being continued", "[Request interrupted"
)

UNIVERSAL_PHILOSOPHY_KEYWORDS = [
    "誇り", "絆", "プロセス", "ブランド", "人格", "クローン", "使命", "本質",
    "価値観", "理念", "こだわり", "哲学", "信頼", "原則", "ビジョン", "生き方"
]

BASE_PHILOSOPHY_KEYWORDS = UNIVERSAL_PHILOSOPHY_KEYWORDS + load_local_persona_config().get("philosophy_keywords", [])

BASE_REACTION_KEYWORDS = [
    "なぜ", "どうして", "抜け漏れ", "原因", "問題", "違う", "違和感", "おかしい",
    "最高", "面白い", "いい感じ", "依存", "煽", "ダメ", "弱い", "限界"
]

BASE_ACTION_KEYWORDS = [
    "作って", "実装して", "統合して", "リサーチして", "検証して", "直して",
    "進めて", "集約", "落とし込", "使えるように", "自動化", "設計", "導入して", "仕上げて", "仕組み"
]

CORRECTION_PATTERNS = [
    r"(?:そうじゃなくて|そうではなく|ではなくて)([^。\n]{6,120})",
    r"(?:AIっぽ|機械的|テンプレ感|一般的すぎ|浅い|抽象的)([^。\n]{0,100})",
    r"([^。\n]{4,60})(?:は禁止|はNG|はやめて|は使わないで|は入れないで)",
    r"(?:もっと|必ず)([^。\n]{6,90})(?:ようにして|にしてほしい|に統一して|で書いて)",
]

BANNED_EXTRACT_RE = re.compile(r"[「『]?([^「」『』。\n、]{2,24})[」』]?(?:は禁止|はNG|はやめて|は使わないで|は入れないで)")

TASK_NOISE_WORDS = (
    "引数", "関数", "行目", "ディレクトリ", "ファイルパス", "インポート", "変数",
    "カラム", "ポート番号", "構文エラー", "スタックトレース", "git ", "npm ", "pip "
)

SECRET_AND_PII_PATTERNS = [
    re.compile(r"\b(?:sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_-]{30,}|xox[baprs]-[A-Za-z0-9-]{10,})\b"),
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    re.compile(r"\b0\d{1,4}-\d{1,4}-\d{3,4}\b"),
    re.compile(r"(?i)\b(?:api[_-]?key|secret[_-]?key|password|passwd|bearer)\s*[:=]\s*\S+"),
]

AI_SLOP_WORDS = [
    "いかがでしたか", "と言えるでしょう", "まず第一に", "素晴らしいアイデア",
    "徹底解説", "今回は〜について", "〜とは？", "まとめると"
]


def sanitize_pii_and_secrets(text: str) -> str:
    s = text
    for pat in SECRET_AND_PII_PATTERNS:
        s = pat.sub("[REDACTED]", s)
    return s


def is_authentic_utterance(text: str) -> bool:
    t = text.strip()
    if len(t) < 18 or len(t) > 450:
        return False
    if any(t.startswith(p) for p in SKIP_PREFIXES):
        return False
    if t.count("\n") > 8 or "```" in t or "def " in t or "import " in t or "SELECT " in t:
        return False
    if not re.search(r"[ぁ-んァ-ン一-龥]", t):
        return False
    if any(pat.search(t) for pat in SECRET_AND_PII_PATTERNS):
        return False
    return True


def load_learning_state() -> dict:
    if LEARNING_STATE_FILE.exists():
        try:
            return json.loads(LEARNING_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "evolution_count": 0,
        "last_updated": "",
        "discovered_keywords": [],
        "learned_corrections": [],
        "dynamic_banned_phrases": [],
        "feedback_memories": [],
        "slop_gate_pass_rate": 100.0,
    }


def mine_corrections_and_evolving_lexicon(rows: list, prev_state: dict) -> dict:
    """
    Closed-Loop Self-Improvement Engine (v3.0):
    1. Filters out low-level coding task noise from style/persona corrections.
    2. Rolling FIFO + recency prioritization (never freezes at 30 items).
    3. Dynamically extracts banned phrases to feed directly into the Slop Gate.
    4. Extracts high-frequency recurring 2-6 kanji/katakana compounds.
    """
    existing_corrections = list(prev_state.get("learned_corrections", []))
    dynamic_banned = list(prev_state.get("dynamic_banned_phrases", []))
    new_corrections = []
    seen_corr = set()

    concept_counter = Counter()
    stop_concepts = {
        "ファイル", "フォルダ", "プロジェクト", "エラー", "コード", "スクリプト", "システム",
        "確認", "実行", "修正", "作成", "追加", "変更", "設定", "対応", "必要", "現在", "今回",
        "情報", "内容", "データ", "ページ", "リンク", "ディレクトリ", "コマンド", "テスト"
    }

    for prov, content, ts, sid in rows:
        clean = sanitize_pii_and_secrets(re.sub(r"\s+", " ", content).strip())
        if not is_authentic_utterance(clean):
            continue

        # 1. Check correction patterns (excluding pure coding-task noise)
        if not any(nw in clean for nw in TASK_NOISE_WORDS):
            for pat in CORRECTION_PATTERNS:
                if re.search(pat, clean):
                    snippet = clean[:140]
                    if snippet not in seen_corr:
                        seen_corr.add(snippet)
                        new_corrections.append({
                            "date": (ts or "")[:10] or "2026",
                            "provider": prov,
                            "rule": snippet,
                            "session_id": sid[:8],
                        })
                    for bm in BANNED_EXTRACT_RE.finditer(clean):
                        bp = bm.group(1).strip()
                        if 2 <= len(bp) <= 20 and bp not in dynamic_banned and bp not in ("これ", "それ", "あれ", "ここ"):
                            dynamic_banned.insert(0, bp)
                    break

        # 2. Count recurring conceptual compounds
        for term in re.findall(r"[一-龥]{2,5}|[ァ-ヴー]{3,8}", clean):
            if term not in stop_concepts and len(term) >= 2:
                concept_counter[term] += 1

    # Merge new corrections at the front, preserving existing ones without freezing
    for old_c in existing_corrections:
        r_txt = old_c.get("rule", "")
        if r_txt and r_txt not in seen_corr and not any(nw in r_txt for nw in TASK_NOISE_WORDS):
            seen_corr.add(r_txt)
            new_corrections.append(old_c)

    # 3. Harvest feedback_*.md from Claude project & root memories (with tenant isolation guard)
    feedback_items = []
    is_custom_isolated_vault = bool(os.environ.get("OBSIDIAN_VAULT")) and not has_local_canon() and VAULT_DIR != _default_vault
    if not is_custom_isolated_vault:
        mem_globs = [
            str(HOME_DIR / ".claude/projects/*/memory/feedback_*.md"),
            str(HOME_DIR / ".claude/projects/*/memory/user_*.md"),
            str(HOME_DIR / ".claude/memory/feedback_*.md"),
        ]
    else:
        mem_globs = [
            str(VAULT_DIR / "linked/**/feedback_*.md"),
            str(VAULT_DIR / "linked/**/user_*.md"),
        ]
    seen_fb = set()
    for g in mem_globs:
        for fp_str in sorted(glob.glob(g, recursive=True), key=os.path.getmtime, reverse=True)[:25]:
            fp = Path(fp_str)
            if fp.name in seen_fb:
                continue
            seen_fb.add(fp.name)
            try:
                raw = fp.read_text(encoding="utf-8", errors="ignore")
                body = re.sub(r"^---\n.*?\n---\n", "", raw, flags=re.DOTALL).strip()
                first_line = next((l.strip("- #*") for l in body.splitlines() if l.strip()), "")
                if first_line:
                    feedback_items.append({
                        "file": fp.name,
                        "date": datetime.fromtimestamp(fp.stat().st_mtime).strftime("%Y-%m-%d"),
                        "summary": sanitize_pii_and_secrets(first_line[:140])
                    })
            except Exception:
                pass

    discovered = [w for w, cnt in concept_counter.most_common(35) if cnt >= 3][:20]

    return {
        "evolution_count": prev_state.get("evolution_count", 0) + 1,
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "discovered_keywords": discovered,
        "learned_corrections": new_corrections[:30],
        "dynamic_banned_phrases": dynamic_banned[:25],
        "feedback_memories": feedback_items[:15],
        "concept_frequencies": dict(concept_counter.most_common(25)),
    }


def extract_utterances(limit_per_cat: int = 25) -> tuple:
    categories = {
        "philosophy": [],
        "reaction": [],
        "action": [],
        "voice_dictation": [],
    }
    rows = []
    if ARCHIVE_DB.exists():
        # Also read raw voice dictation history if available
        trans_file = HOME_DIR / ".codex" / "transcription-history.jsonl"
        if trans_file.exists():
            for line in trans_file.read_text(encoding="utf-8", errors="ignore").splitlines():
                if not line.strip():
                    continue
                try:
                    d = json.loads(line)
                    txt = str(d.get("text") or "").strip()
                    ts_ms = d.get("createdAtMs")
                    d_str = datetime.fromtimestamp(ts_ms / 1000.0).strftime("%Y-%m-%d") if ts_ms else "2026"
                    if txt:
                        categories["voice_dictation"].append({
                            "provider": "voice",
                            "date": d_str,
                            "text": txt,
                            "session_id": str(d.get("id", "voice"))[:8]
                        })
                except Exception:
                    pass

        try:
            conn = sqlite3.connect(str(ARCHIVE_DB), timeout=5.0)
            rows = conn.execute("""
                SELECT m.provider, m.content, COALESCE(NULLIF(m.timestamp, ''), s.updated_at), m.session_id
                FROM messages_fts m
                JOIN sessions s ON m.session_id = s.session_id
                WHERE m.role = 'user'
                ORDER BY s.updated_at DESC
                LIMIT 4500
            """).fetchall()
            conn.close()
        except Exception:
            rows = []

    prev_state = load_learning_state()
    new_state = mine_corrections_and_evolving_lexicon(rows, prev_state)

    # Dynamically merge discovered keywords with base keywords
    phil_kw = set(BASE_PHILOSOPHY_KEYWORDS + [w for w in new_state["discovered_keywords"] if len(w) >= 2])
    react_kw = set(BASE_REACTION_KEYWORDS)
    act_kw = set(BASE_ACTION_KEYWORDS)

    seen = set()
    for prov, content, ts, sid in rows:
        clean = sanitize_pii_and_secrets(re.sub(r"\s+", " ", content).strip())
        if not is_authentic_utterance(clean):
            continue
        norm_key = clean[:60]
        if norm_key in seen:
            continue
        seen.add(norm_key)

        date_str = (ts or "")[:10] if ts else "2026"
        item = {"provider": prov, "date": date_str, "text": clean, "session_id": sid}

        if any(k in clean for k in BASE_PHILOSOPHY_KEYWORDS) and len(categories["philosophy"]) < limit_per_cat:
            categories["philosophy"].append(item)
        elif any(k in clean for k in react_kw) and len(categories["reaction"]) < limit_per_cat:
            categories["reaction"].append(item)
        elif any(k in clean for k in act_kw) and len(categories["action"]) < limit_per_cat:
            categories["action"].append(item)
        elif any(k in clean for k in phil_kw) and len(categories["philosophy"]) < limit_per_cat:
            categories["philosophy"].append(item)

    # Ingest PERSONA_SEEDS.md if present (resolves Cold-Start problem for new users)
    seeds_file = MEMORY_DIR / "PERSONA_SEEDS.md"
    if seeds_file.exists():
        try:
            s_txt = seeds_file.read_text(encoding="utf-8", errors="ignore")
            today_d = datetime.now().strftime("%Y-%m-%d")
            m_phil = re.search(r"## 1\..*?\n-\s*(.+)", s_txt)
            m_reac = re.search(r"## 2\..*?\n-\s*(.+)", s_txt)
            m_act = re.search(r"## 3\..*?\n-\s*(.+)", s_txt)
            m_ng = re.search(r"## 4\..*?\n-\s*(.+)", s_txt)
            if m_phil and m_phil.group(1).strip():
                categories["philosophy"].insert(0, {"provider": "seed", "date": today_d, "text": m_phil.group(1).strip(), "session_id": "onboard-seed"})
            if m_reac and m_reac.group(1).strip():
                categories["reaction"].insert(0, {"provider": "seed", "date": today_d, "text": m_reac.group(1).strip(), "session_id": "onboard-seed"})
            if m_act and m_act.group(1).strip():
                categories["action"].insert(0, {"provider": "seed", "date": today_d, "text": m_act.group(1).strip(), "session_id": "onboard-seed"})
            if m_ng and m_ng.group(1).strip():
                ng_rule = m_ng.group(1).strip()
                if not any(c.get("rule") == ng_rule for c in new_state.get("learned_corrections", [])):
                    new_state.setdefault("learned_corrections", []).insert(0, {"date": today_d, "provider": "seed", "rule": ng_rule, "session_id": "onboard-seed"})
                for token in re.split(r"[、,／/・\s「」『』（）()]+", ng_rule):
                    tok = token.strip()
                    if 2 <= len(tok) <= 18 and tok not in ("AI特有の定型文", "一切使わない", "使わない", "禁止", "表現"):
                        if tok not in new_state.setdefault("dynamic_banned_phrases", []):
                            new_state["dynamic_banned_phrases"].insert(0, tok)
        except Exception:
            pass

    atomic_write_text(LEARNING_STATE_FILE, json.dumps(new_state, ensure_ascii=False, indent=2))
    return categories, new_state


def apply_closed_loop_constraints(draft_text: str, dynamic_banned: list = None) -> str:
    """Actively enforces learned banned phrases and Slop rules on generated drafts (Closed-Loop)."""
    out = sanitize_pii_and_secrets(draft_text)
    all_banned = list(AI_SLOP_WORDS) + list(dynamic_banned or [])
    for bw in all_banned:
        if bw and len(bw) >= 2 and bw in out:
            out = out.replace(bw, "")
    return re.sub(r"\n{3,}", "\n\n", out).strip()


def evaluate_draft_quality(draft_text: str, dynamic_banned: list = None) -> dict:
    """Deterministic Slop & Dynamic Persona Compliance Gate."""
    active_slop_list = list(dict.fromkeys(list(AI_SLOP_WORDS) + list(dynamic_banned or [])))
    slop_hits = [w for w in active_slop_list if w and w in draft_text]
    lines = [l.strip() for l in draft_text.strip().splitlines() if l.strip()]
    avg_line_len = sum(len(l) for l in lines) / max(len(lines), 1)
    has_question = "？" in draft_text or "?" in draft_text
    score = 100
    if slop_hits:
        score -= 25 * len(slop_hits)
    if avg_line_len > 65:
        score -= 10
    if not has_question:
        score -= 5
    return {
        "score": max(0, score),
        "slop_hits": slop_hits,
        "active_rules_checked": len(active_slop_list),
        "avg_line_len": round(avg_line_len, 1),
        "passed": len(slop_hits) == 0 and score >= 85
    }


def update_persona_core_self_improvement_section(state: dict):
    """Updates the self-improvement section at the bottom of PERSONA_CORE_FILE."""
    core_file, _ = resolve_persona_files()
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    p_name = resolve_owner_name()
    if not core_file.exists():
        init_core = f"""---
title: "{p_name} 完全人格コピー＆SNS言語エンジン正本 (Persona Core OS)"
date: {datetime.now().strftime("%Y-%m-%d")}
type: persona-core
tags: [persona, sns-engine, self-improving]
---

# 🧬 {p_name} 完全人格コピー＆SNS言語エンジン (`{core_file.stem}`)

> **役割**: 全AI（Codex / Claude Code / Antigravity / ChatGPT）の対話履歴・音声入力から、`{p_name}` の「使う言葉」「反応する言葉」「行動する言葉」を自動抽出・自己学習する正本。
"""
        atomic_write_text(core_file, init_core)
    raw = core_file.read_text(encoding="utf-8")
    marker = "\n## 🔄 5. 自己改善フィードバックループ（Auto-Evolving Persona Ledger）"
    if marker in raw:
        raw = raw.split(marker)[0].rstrip() + "\n"

    freq_top = ", ".join(f"`{k}`({v})" for k, v in list(state.get("concept_frequencies", {}).items())[:12])
    dyn_banned = ", ".join(f"`{w}`" for w in state.get("dynamic_banned_phrases", [])[:12]) or "標準AI Slop辞書のみ"
    section = f"""{marker}

> **自律学習世代 (Evolution Generation)**: `Gen #{state.get('evolution_count', 1)}` | **最終自己更新**: `{state.get('last_updated', '')}`
> **閉ループ検閲ゲート (Active Slop Gate)**: 標準NG `{len(AI_SLOP_WORDS)}語` ＋ 動的学習NG `{len(state.get('dynamic_banned_phrases', []))}語` ({dyn_banned})

### 5.1 直近の対話から自動検出された高頻度コア概念（Dynamic Lexicon）
- {freq_top or '集計中'}

### 5.2 過去のAI対話・記憶から自動学習した「判断・表現矯正ルール」（Feedback Memory）
"""
    for fb in state.get("feedback_memories", [])[:8]:
        section += f"- **`[{fb['date']}]`** ({fb['file']}): {fb['summary']}\n"

    if state.get("learned_corrections"):
        section += "\n### 5.3 チャット内の直接ダメ出し・軌道修正ログ（Correction Triggers）\n"
        for c in state["learned_corrections"][:10]:
            section += f"- **`[{c['date']} | {c['provider'].upper()}]`** 「{c['rule']}」 (`{c['session_id']}`)\n"

    atomic_write_text(core_file, raw + section)


def build_voice_log(cats: dict, state: dict) -> Path:
    core_file, voice_file = resolve_persona_files()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    p_name = resolve_owner_name()
    md = f"""---
title: "{p_name} リアル発話ログ (使う言葉・反応する言葉・行動する言葉)"
date: {datetime.now().strftime("%Y-%m-%d")}
updated: "{now_str}"
evolution_gen: {state.get('evolution_count', 1)}
type: voice-log
tags: [persona, voice-log, sns-source, self-improving]
---

# 🗣️ {p_name} リアル発話＆自己改善抽出ログ (`{voice_file.stem}`)

> **自動更新日時**: `{now_str}` | **自己学習世代**: `Gen #{state.get('evolution_count', 1)}`
> **抽出元**: Codex CLI / Claude Code (全サブフォルダ) / Antigravity / ChatGPT Project / 音声ディクテーション (PII検閲済)
> **連携先**: [[{core_file.stem}]] | [[SNS_READY_DRAFTS]] | [[SHARED_MEMORY]]

---
"""
    if cats.get("voice_dictation"):
        md += "## 0. 【生の音声ディクテーション】声で直接吹き込まれた言葉\n\n"
        for v in cats["voice_dictation"]:
            md += f"- **`[{v['date']} | VOICE]`** 「{sanitize_pii_and_secrets(v['text'])}」\n"
        md += "\n---\n\n"

    md += "## 1. 【使う言葉・思想】世界観・ミッション・概念定義（生の発話）\n\n"
    for u in cats["philosophy"]:
        md += f"- **`[{u['date']} | {u['provider'].upper()}]`** 「{u['text']}」 (`{u['session_id'][:8]}`)\n"

    md += "\n---\n\n## 2. 【反応する言葉】問題意識・違和感・本質への問い（生の発話）\n\n"
    for u in cats["reaction"]:
        md += f"- **`[{u['date']} | {u['provider'].upper()}]`** 「{u['text']}」 (`{u['session_id'][:8]}`)\n"

    md += "\n---\n\n## 3. 【行動する言葉】意思決定・仕組み化・一点突破の号令（生の発話）\n\n"
    for u in cats["action"]:
        md += f"- **`[{u['date']} | {u['provider'].upper()}]`** 「{u['text']}」 (`{u['session_id'][:8]}`)\n"

    if state.get("learned_corrections"):
        md += f"\n---\n\n## 4. 【自己改善ログ】{p_name}の軌道修正・ダメ出しから自動学習したルール\n\n"
        for c in state["learned_corrections"][:10]:
            md += f"- **`[{c['date']} | {c['provider'].upper()}]`** 「{c['rule']}」 (`{c['session_id']}`)\n"

    atomic_write_text(voice_file, md)
    return voice_file


def build_sns_drafts(cats: dict, state: dict) -> Path:
    core_file, voice_file = resolve_persona_files()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    today_str = datetime.now().strftime("%Y-%m-%d")
    local_cfg = load_local_persona_config()
    p_name = resolve_owner_name()
    dyn_banned = state.get("dynamic_banned_phrases", [])

    phil_list = cats["philosophy"] or [{"text": "AIの時代にこそ、人が人としての心と誇りを取り戻すプロセスが必要だ。", "date": today_str}]
    react_list = cats["reaction"] or [{"text": "表面的な効率化だけでは、本当の課題は解決しない。", "date": today_str}]
    act_list = cats["action"] or [{"text": "散らばった知識と経験を一つに統合し、いつでも使える仕組みにする。", "date": today_str}]
    voice_quote = sanitize_pii_and_secrets(cats["voice_dictation"][-1]["text"]) if cats.get("voice_dictation") else phil_list[0]["text"][:80]

    custom_drafts = local_cfg.get("custom_drafts", [])
    if len(custom_drafts) >= 3:
        draft1 = custom_drafts[0].replace("{voice_quote}", voice_quote)
        draft2 = custom_drafts[1]
        draft3 = custom_drafts[2]
    else:
        top_concepts = ", ".join(list(state.get("concept_frequencies", {}).keys())[:4]) or "本質・仕組み化"
        draft1 = f"""「{phil_list[0]['text'][:100]}」

日々AIと対話しながら仕事を進める中で、改めて強く感じることがあります。
どれだけツールが進化しても、最後に価値を決めるのは「どんな問いを立てるか」という人間側の視点です。

重点テーマ（{top_concepts}）を軸に、単なる作業の効率化ではなく、
本当に届けるべき価値に集中できる環境を整えていく。

あなたは今日、どんな問いから一日を始めますか？"""

        draft2 = f"""「{react_list[0]['text'][:100]}」

現場でこうした違和感に出会ったとき、個人の頑張りや気合で解決しようとしてはいけない。
問題の本質は人ではなく、常に「構造」と「仕組み」にあります。

「{act_list[0]['text'][:90]}」
一つひとつの違和感をそのままにせず、再現性のあるシステムへ昇華させていくこと。

今日、あなたの現場で「仕組み」に変えられる手作業は何ですか？"""

        draft3 = f"""「{voice_quote[:100]}」

散らばっていた思考や対話のログを一つの知識基盤（Obsidian）に集約すると、
自分が何に反応し、何を大切にしているのかが驚くほど鮮明に見えてきます。

借り物の言葉ではなく、自分が現場で積み重ねてきた生の言葉から発信をつくること。
あなた自身の経験と言葉を、今日から資産として積み上げてみませんか？"""

    draft1 = apply_closed_loop_constraints(draft1, dyn_banned)
    draft2 = apply_closed_loop_constraints(draft2, dyn_banned)
    draft3 = apply_closed_loop_constraints(draft3, dyn_banned)

    eval1 = evaluate_draft_quality(draft1, dyn_banned)
    eval2 = evaluate_draft_quality(draft2, dyn_banned)
    eval3 = evaluate_draft_quality(draft3, dyn_banned)

    md = f"""---
title: "{p_name} SNS直結ドラフト集 (X / Threads / note)"
date: {today_str}
updated: "{now_str}"
evolution_gen: {state.get('evolution_count', 1)}
type: sns-drafts
tags: [sns, x, threads, note, self-improving]
---

# 📱 {p_name} SNS直結投稿ドラフト集 (`SNS_READY_DRAFTS`)

> **生成日時**: `{now_str}` | **自己改善世代**: `Gen #{state.get('evolution_count', 1)}`
> **ベース正本**: [[{core_file.stem}]] × [[{voice_file.stem}]]（直近のAI壁打ち生ログ＆音声入力から自動生成）
> **決定論的品質ゲート (Closed-Loop Slop Gate)**: 全ドラフト検閲済（検査ルール数: `{eval1['active_rules_checked']}件` | Score: ①`{eval1['score']}点` / ②`{eval2['score']}点` / ③`{eval3['score']}点`）

---

## 🔥 今すぐ投稿できる X / Threads ドラフト（3パターン）

### パターン①：【思想・世界観】使う言葉（Philosophy）からの展開
- **着想元となった最新発話**: *「{phil_list[0]['text'][:100]}」* ＋ 音声入力 *「{voice_quote}」*
- **品質自己採点**: `{eval1['score']}/100` (平均1行文字数: `{eval1['avg_line_len']}字` / Slop検出: `{len(eval1['slop_hits'])}件`)

```text
{draft1}
```

---

### パターン②：【実践・仕組み化】行動する言葉（Action）からの展開
- **着想元となった最新発話**: *「{act_list[0]['text'][:100]}」*
- **品質自己採点**: `{eval2['score']}/100` (平均1行文字数: `{eval2['avg_line_len']}字` / Slop検出: `{len(eval2['slop_hits'])}件`)

```text
{draft2}
```

---

### パターン③：【問題提起・誇り】反応する言葉（Reaction）からの展開
- **着想元となった最新発話**: *「{react_list[0]['text'][:100]}」*
- **品質自己採点**: `{eval3['score']}/100` (平均1行文字数: `{eval3['avg_line_len']}字` / Slop検出: `{len(eval3['slop_hits'])}件`)

```text
{draft3}
```

---

## 🧠 直近の対話から自動抽出された「次のSNSネタの種（Raw Seeds）」

日々のAI壁打ちで発した最新の問い・違和感・号令（ここからも即座に新規投稿を展開可能）：

1. **最新の思想フレーズ**: 「{phil_list[0]['text'][:130]}」
2. **最新の違和感・問い**: 「{react_list[0]['text'][:130]}」
3. **最新の行動・仕組み化号令**: 「{act_list[0]['text'][:130]}」

---

## 🚀 自動更新コマンド

```bash
# 最新チャットから人格ログ・自己改善ルール・SNSドラフトを再生成
ai-memory persona --mode sync
```
"""

    atomic_write_text(SNS_DRAFTS_FILE, md)
    if bool(local_cfg) and HASSHIN_DRAFTS_FILE.parent.parent.exists():
        try:
            atomic_write_text(HASSHIN_DRAFTS_FILE, md)
        except Exception:
            pass
    return SNS_DRAFTS_FILE


def sync_persona_engine(verbose: bool = True):
    cats, state = extract_utterances(limit_per_cat=25)
    update_persona_core_self_improvement_section(state)
    v_path = build_voice_log(cats, state)
    s_path = build_sns_drafts(cats, state)
    if verbose:
        print(f"✅ Self-Improving Persona Engine updated (Gen #{state.get('evolution_count', 1)}):")
        print(f"   - Discovered Concepts: {len(state.get('discovered_keywords', []))} | Feedback Rules: {len(state.get('feedback_memories', []))} | Corrections: {len(state.get('learned_corrections', []))}")
        print(f"   - Voice Log:  {v_path} (Philosophy: {len(cats['philosophy'])}, Reaction: {len(cats['reaction'])}, Action: {len(cats['action'])})")
        print(f"   - SNS Drafts: {s_path}")
    return {"voice_log": str(v_path), "sns_drafts": str(s_path), "state": state}


if __name__ == "__main__":
    sync_persona_engine(verbose=True)
