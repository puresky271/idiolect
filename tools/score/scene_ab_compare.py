"""按场景蒸馏指标比较两臂：谁更贴近「原作同场景」。

主指标：逐场景的 `长度比值 = 输出中位 / 原作同场景中位`（越接近 1 越好）。
在**高对比场景**上，场景条件化那臂应当把比值显著拉向 1。

产出 report/scene_ab_distill.json
"""
from __future__ import annotations

# ── idiolect 路径引导：仓库根 + 各 tools 子目录上 sys.path ──
import sys as _sys
from pathlib import Path as _Path
_ROOT = _Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "tools",
           *(_ROOT / "tools" / _d for _d in ("corpus", "distill", "probe", "score", "gates"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))
from _paths import CORPUS_DIR, DATA, REPORT, ROOT  # noqa: E402,F401

import argparse
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import style_features as S  # noqa: E402

REPORT = REPORT
BASE = json.loads((DATA / "scene_char_baseline.json").read_text(encoding="utf-8"))


def load_ratios(label: str) -> dict[str, dict]:
    p = REPORT / f"probe_{label}.jsonl"
    if not p.exists():
        return {}
    per: dict[tuple[str, str], list[str]] = defaultdict(list)
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("reply") and r.get("scene"):
            per[(r["char"], r["scene"])].append(r["reply"])
    out: dict[str, dict] = {}
    for (char, scene), replies in per.items():
        b = BASE.get(f"{char}|{scene}")
        if not b:
            continue
        prof = S.profile_from_texts(replies, "cn")
        if not prof.get("n"):
            continue
        out[f"{char}|{scene}"] = {
            "n": prof["n"],
            "out_med": prof["length"]["p50"],
            "base_med": b["length"]["p50"],
            "ratio": prof["length"]["p50"] / b["length"]["p50"] if b["length"]["p50"] else None,
            "out_sent": prof["n_sent"]["mean"],
            "base_sent": b["n_sent"]["mean"],
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", required=True)
    ap.add_argument("--after", required=True)
    args = ap.parse_args()

    A, B = load_ratios(args.before), load_ratios(args.after)
    keys = sorted(set(A) & set(B))
    print(f"=== 逐场景蒸馏对比：`{args.before}` vs `{args.after}`（{len(keys)} 个共同场景）===\n")
    print(f"{'角色|场景':<26}{'原作中位':>9}{'before':>9}{'after':>9}{'比值b':>8}{'比值a':>8}{'改善':>8}")
    print("-" * 80)
    ds = []
    for k in keys:
        a, b = A[k], B[k]
        ra, rb = a["ratio"], b["ratio"]
        if ra is None or rb is None:
            continue
        # 改善 = 离 1 的距离减少多少（正 = 更接近原作）
        gain = abs(ra - 1) - abs(rb - 1)
        ds.append(gain)
        char, scene = k.split("|")
        print(f"{char + '|' + scene:<26}{a['base_med']:>9.0f}{a['out_med']:>9.0f}{b['out_med']:>9.0f}"
              f"{ra:>8.2f}{rb:>8.2f}{gain:>+8.2f}")

    if ds:
        m = statistics.fmean(ds)
        sd = statistics.stdev(ds) if len(ds) > 1 else 0.0
        se = sd / math.sqrt(len(ds)) if ds else 0.0
        z = m / se if se else 0.0
        better = sum(1 for x in ds if x > 0.02)
        worse = sum(1 for x in ds if x < -0.02)
        print(f"\n平均改善 {m:+.3f}（SE {se:.3f}, z={z:.2f}）")
        print(f"更接近原作 {better} 个｜更远 {worse} 个｜基本不变 {len(ds) - better - worse} 个")
        print(f"显著性：{'是' if abs(z) > 1.96 else '**否**'}")
        (REPORT / "scene_ab_distill.json").write_text(json.dumps({
            "before": args.before, "after": args.after, "n_scenes": len(ds),
            "mean_gain": round(m, 4), "se": round(se, 4), "z": round(z, 2),
            "better": better, "worse": worse,
            "per_scene": {k: {"ratio_before": round(A[k]["ratio"], 3),
                              "ratio_after": round(B[k]["ratio"], 3)} for k in keys},
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
