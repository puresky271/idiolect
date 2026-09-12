"""五人台词集量化分析：打印角色风格画像 + 两两区分度 + 词级签名 + 两语言对照。

输入 bench/raw/hf/{jp,cn}.jsonl（金标准）；如 Bestdori 已爬完则一并纳入。
产出 bench/report/quant_report.md 与 profile_<lang>.json。
"""
from __future__ import annotations

# ── idiolect 路径引导（可移植）：仓库根 + 各 tools 子目录上 sys.path ──
import sys as _sys
from pathlib import Path as _Path
_ROOT = _Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "tools",
           *(_ROOT / "tools" / _d for _d in ("corpus", "distill", "probe", "score", "gates"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))
from _paths import CORPUS_DIR, DATA, REPORT, ROOT, require_corpus  # noqa: E402,F401

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import style_features as S  # noqa: E402

CHARS = ["tomori", "anon", "rana", "soyo", "taki"]
CN_NAME = {"tomori": "灯", "anon": "爱音", "rana": "乐奈", "soyo": "爽世", "taki": "立希"}
JP_NAME = {"tomori": "燈", "anon": "愛音", "rana": "楽奈", "soyo": "そよ", "taki": "立希"}


def load(lang: str, include_bestdori: bool) -> dict[str, list[str]]:
    """优先读 build_gold.py 产出的去重金标准；缺失时回落到原始分源文件。"""
    out: dict[str, list[str]] = {c: [] for c in CHARS}
    gold = CORPUS_DIR / f"{lang}.jsonl"
    if gold.exists():
        for line in gold.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            out.setdefault(r["character"], []).append(r["text"])
        return out
    hf = HERE / "raw" / "hf" / f"{lang}.jsonl"
    if hf.exists():
        for line in hf.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            out.setdefault(r["character"], []).append(r["text"])
    if include_bestdori:
        bd = HERE / "raw" / "bestdori" / f"{lang}.jsonl"
        if bd.exists():
            from bd_api import MYGO
            rev = {v: k for k, v in MYGO.items()}
            for line in bd.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                r = json.loads(line)
                ch = rev.get(str(r["character_id"]))
                if ch:
                    out.setdefault(ch, []).append(r["text"])
    return out


def bar(v: float, vmax: float, width: int = 28) -> str:
    if vmax <= 0:
        return ""
    return "█" * max(1, int(round(v / vmax * width)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bestdori", action="store_true", help="把 bestdori 语料一并纳入")
    ap.add_argument("--langs", default="jp,cn")
    args = ap.parse_args()

    report_dir = REPORT
    report_dir.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    all_profiles: dict = {}
    empty: list[str] = []

    for lang in args.langs.split(","):
        lang = lang.strip()
        corpus = load(lang, args.bestdori)
        total = sum(len(v) for v in corpus.values())
        if total == 0:
            print(f"[{lang}] no data")
            empty.append(lang)
            continue
        name = JP_NAME if lang == "jp" else CN_NAME

        lines.append(f"\n{'=' * 78}\n## {lang.upper()}  语料 {total} 条\n{'=' * 78}\n")
        lines.append(f"{'角色':<6}{'条数':>6}{'均长':>8}{'中位':>7}{'p90':>7}{'句数':>7}{'小句':>7}{'沉默%':>8}")
        lines.append("-" * 62)

        profiles: dict[str, dict] = {}
        for ch in CHARS:
            texts = corpus[ch]
            prof = S.profile_from_texts(texts, lang)
            if prof.get("n", 0) == 0:
                continue
            profiles[ch] = prof
            sil = len(S.silent_turns(texts))
            L = prof["length"]
            lines.append(
                f"{name[ch]:<6}{prof['n']:>6}{L['mean']:>8.1f}{L['p50']:>7.0f}{L['p90']:>7.0f}"
                f"{prof['n_sent']['mean']:>7.2f}{prof['n_clause']['mean']:>7.2f}{sil / max(prof['n'], 1) * 100:>7.1f}%"
            )
        all_profiles[lang] = profiles

        # ---- 标点语气指纹
        lines.append(f"\n### 标点 / 语气指纹（出现率 = 含该标点的回合占比）\n")
        heads = ["…", "！", "？", "、", "，", "—", "～", "。"]
        lines.append(f"{'角色':<6}" + "".join(f"{h:>8}" for h in heads) + f"{'一人称':>9}{'称呼':>8}{'filler':>8}{'笑':>7}")
        lines.append("-" * 100)
        for ch in CHARS:
            if ch not in profiles:
                continue
            p = profiles[ch]
            row = f"{name[ch]:<6}"
            for h in heads:
                row += f"{p['punct_rate'][h] * 100:>7.0f}%"
            row += f"{p['first_person_rate'] * 100:>8.0f}%{p['address_suffix_rate'] * 100:>7.0f}%"
            row += f"{p['filler_rate'] * 100:>7.0f}%{p['laugh_rate'] * 100:>6.0f}%"
            lines.append(row)

        # ---- 长度分布（直方图）
        lines.append(f"\n### 回合字数分布\n")
        lines.append(f"{'角色':<6}{'0-5':>7}{'6-10':>7}{'11-20':>7}{'21-35':>7}{'36-50':>7}{'51+':>7}   直方图(中位)")
        lines.append("-" * 78)
        bins = [(0, 5), (6, 10), (11, 20), (21, 35), (36, 50), (51, 10**9)]
        medians = {ch: profiles[ch]["length"]["p50"] for ch in profiles}
        mmax = max(medians.values()) if medians else 1
        for ch in CHARS:
            if ch not in profiles:
                continue
            texts = [t for t in corpus[ch] if t.strip() and not S.turn_features(t).silent]
            lens = [len(t) for t in texts]
            n = len(lens)
            row = f"{name[ch]:<6}"
            for lo, hi in bins:
                c = sum(1 for x in lens if lo <= x <= hi)
                row += f"{c / n * 100:>6.0f}%"
            row += "   " + bar(medians[ch], mmax, 20) + f" {medians[ch]:.0f}"
            lines.append(row)

        # ---- 词级签名
        lines.append(f"\n### 各角色特有措辞（log-odds top 14，对全体语料）\n")
        toks = {ch: [t for t in corpus[ch] if t.strip()] for ch in CHARS}
        background = [t for ch in CHARS for t in toks[ch]]
        for ch in CHARS:
            if ch not in profiles:
                continue
            others = [t for c2 in CHARS if c2 != ch for t in toks[c2]]
            sig = S.logodds_signature(toks[ch], others, lang, top=14)
            words = "、".join(f"{w}({c})" for w, _, c in sig)
            lines.append(f"- **{name[ch]}**: {words}")

        # ---- 感动词 / 终助词明细（这是最能区分五人「声音」的一组）
        lines.append(f"\n### 感动词（フィラー）与句末助词的实际用词\n")
        for ch in CHARS:
            if ch not in profiles:
                continue
            if lang == "jp":
                inter = S.token_freq(toks[ch], lang, pos1_filter=["感動詞"])
                tail = S.token_freq(toks[ch], lang, pos1_filter=["助詞"])
                tail_top = [(w, c) for w, c in tail.most_common(60) if w in S.JP_SENTENCE_FINAL][:8]
            else:
                allw = S.token_freq(toks[ch], lang)
                inter = Counter({w: c for w, c in allw.items() if w in S.FILLER_CN})
                tail_top = []
            lines.append(f"- **{name[ch]}** 感动词: " + "、".join(f"{w}({c})" for w, c in inter.most_common(8)))
            if tail_top:
                lines.append(f"  句末助词: " + "、".join(f"{w}({c})" for w, c in tail_top))
            lines.append(f"  句末助词率: {profiles[ch]['sent_final_jp_per_turn']['mean']:.2f}/回合" + (f"   长音符率 {profiles[ch]['long_vowel_rate'] * 100:.0f}%" if lang == "jp" else ""))

        # ---- 两两区分度
        lines.append(f"\n### 两两区分度（|Δ中位字数| / 标点出现率差 之和，越大越好区分）\n")
        keys = ["…", "！", "？", "，"]
        lines.append(f"{'':<8}" + "".join(f"{name[c2]:>8}" for c2 in CHARS))
        for a in CHARS:
            row = f"{name[a]:<8}"
            for b in CHARS:
                if a == b:
                    row += f"{'—':>8}"
                    continue
                pa, pb = profiles.get(a), profiles.get(b)
                if not pa or not pb:
                    row += f"{'':>8}"
                    continue
                d = abs(pa["length"]["p50"] - pb["length"]["p50"]) / 20
                d += sum(abs(pa["punct_rate"][k] - pb["punct_rate"][k]) for k in keys) * 4
                row += f"{d:>8.1f}"
            lines.append(row)
        lines.append("")

    (report_dir / "profile_all.json").write_text(
        json.dumps(all_profiles, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    text = "\n".join(lines)
    (report_dir / "quant_report.md").write_text(text, encoding="utf-8")
    if empty and len(empty) == len([x for x in args.langs.split(",") if x.strip()]):
        raise SystemExit(
            f"[stop] 全部语言都没有语料（{empty}）——空语料会算出空画像，所以这里直接退出。\n"
            f"       先跑 tools/corpus/build_gold.py，或用 IDIOLECT_CORPUS_DIR 指向语料目录"
            f"（见 docs/02-corpus.md）。"
        )
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
