"""对照：黑名单式规则信号 vs 分布距离信号 的强度（决定 benchmark 该建在哪一层）。

结论用途：如果黑名单触发率极低而分布 z 很大 → benchmark 主体必须是分布距离，
黑名单只做兜底。避免把预算花在抓不住的层上。
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
from _paths import CORPUS_DIR, DATA, REPORT, ROOT  # noqa: E402,F401

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import rules as R  # noqa: E402
import style_features as S  # noqa: E402

CHARS = ["tomori", "anon", "rana", "soyo", "taki"]
CORPUS_NAME = {"灯": "tomori", "爱音": "anon", "乐奈": "rana", "素世": "soyo", "爽世": "soyo", "立希": "taki"}


def load_gold(lang="cn"):
    out = defaultdict(list)
    for line in (CORPUS_DIR / f"{lang}.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            out[r["character"]].append(r["text"])
    return out


def load_live():
    out = defaultdict(list)
    for line in (HERE.parent / "corpus.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("role") != "assistant":
            continue
        ch = CORPUS_NAME.get(str(r.get("char")))
        if ch:
            out[ch].extend(t for t in r["content"].split("\n") if t.strip())
    return out


# 用于 z 检验的标量特征
FEATS = {
    "中位字长": lambda f: None,  # 分布量，单独算
    "均句数": lambda f: f.n_sent,
    "均小句": lambda f: f.n_clause,
    "省略号率": lambda f: 1.0 if f.punct_any["…"] else 0.0,
    "感叹号率": lambda f: 1.0 if f.punct_any["！"] else 0.0,
    "句号率": lambda f: 1.0 if f.punct_any["。"] else 0.0,
    "一人称率": lambda f: 1.0 if f.first_person else 0.0,
    "filler率": lambda f: 1.0 if f.filler else 0.0,
}


def feat_vec(texts):
    fs = []
    for t in texts:
        f = S.turn_features(t, "cn")
        if f.silent:
            continue
        fs.append(f)
    if not fs:
        return {}, 0
    out = {}
    for name, fn in FEATS.items():
        vals = [fn(f) for f in fs]
        vals = [v for v in vals if v is not None]
        out[name] = statistics.fmean(vals) if vals else 0.0
    lens = [f.length for f in fs]
    out["中位字长"] = statistics.median(lens)
    out["均字长"] = statistics.fmean(lens)
    return out, len(fs)


def main() -> int:
    gold = load_gold()
    live = load_live()
    print(f"{'角色':<8}{'维度':<12}{'gold':>9}{'live':>9}{'倍率':>9}")
    print("-" * 48)
    for ch in CHARS:
        g, gn = feat_vec(gold[ch])
        l, ln = feat_vec(live[ch])
        for key in ["中位字长", "均字长", "均句数", "均小句", "省略号率", "感叹号率", "句号率", "一人称率", "filler率"]:
            if key not in g or key not in l:
                continue
            gv, lv = g[key], l[key]
            ratio = (lv / gv) if gv else float("inf")
            flag = ""
            if abs(lv - gv) > 0.15 and key.endswith("率"):
                flag = "  ← 分布级差"
            if key in ("中位字长", "均字长") and ratio > 1.4:
                flag = "  ← 长度超标"
            if key == "一人称率" and lv - gv > 0.15:
                flag = "  ← 自我指涉超标"
            print(f"{R.CN_NAME[ch]:<8}{key:<12}{gv:>9.2f}{lv:>9.2f}{ratio:>9.2f}{flag}")
        print()

    # 黑名单规则 vs 分布信号 强度对比
    print("=" * 60)
    print("黑名单规则总触发率（live，气泡级）")
    tot = 0
    hit = 0
    vhit = 0
    for ch in CHARS:
        for t in live[ch]:
            f = S.turn_features(t, "cn")
            if f.silent:
                continue
            tot += 1
            hits = R.check_text(ch, t, sentence_count=f.n_sent, length=f.length)
            if hits:
                hit += 1
            if any(h.level == "V" for h in hits):
                vhit += 1
    print(f"  live 气泡 {tot} 条：任一命中 {hit} ({hit / tot * 100:.1f}%)，含 V 级 {vhit} ({vhit / tot * 100:.1f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
