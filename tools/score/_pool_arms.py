"""池化比较：把同一批夹具的多个臂合并成大样本，再与基线臂比。

为什么需要：单臂每格只有 6 条，中位数的摆动已经大于效应本身
（例：乐奈同一场景在相邻两臂 0.551 → 0.350）。项目自己的功效分析结论是
「10pp 效应需要 ~57 样本/臂」——所以正确的做法是**池化**，不是继续改正文。

用法：
  py -X utf8 _pool_arms.py gen_off gen_on4,gen_on5,gen_on6,gen_on7,gen_on8,gen_on9,gen_on10
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

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.stdout.reconfigure(encoding="utf-8")

import style_features as S  # noqa: E402

REPORT = REPORT
BASE = json.loads((DATA / "scene_char_baseline.json").read_text(encoding="utf-8"))


def load(label: str) -> list[dict]:
    p = REPORT / f"probe_{label}.jsonl"
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] \
        if p.exists() else []


def dev(a: float, b: float) -> float:
    import math
    if not a and not b:
        return 0.0
    if not a or not b:
        return 1.0
    return min(abs(math.log2(a / b)), 2.0)


def cells(rows: list[dict]) -> dict[tuple[str, str], list[str]]:
    per: dict[tuple[str, str], list[str]] = defaultdict(list)
    for r in rows:
        if r.get("reply") and r.get("scene"):
            per[(r["char"], r["scene"])].append(r["reply"])
    return per


def score(per: dict[tuple[str, str], list[str]]) -> dict[tuple[str, str], dict]:
    out = {}
    for k, reps in per.items():
        b = BASE.get(f"{k[0]}|{k[1]}")
        if not b:
            continue
        prof = S.profile_from_texts(reps, "cn")
        if not prof.get("n"):
            continue
        d = (2.0 * dev(prof["length"]["p50"], b["length"]["p50"])
             + 1.0 * dev(prof["length"]["p90"], b["length"]["p90"])
             + 1.5 * dev(prof["n_sent"]["mean"], b["n_sent"]["mean"])) / 4.5
        out[k] = {"n": prof["n"], "out_med": prof["length"]["p50"],
                  "base_med": b["length"]["p50"], "distill": round(max(0.0, 1 - d), 3)}
    return out


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="多臂池化：把同一批夹具的多个臂合并成大样本再与基线臂比")
    ap.add_argument("off_labels", help="基线臂（逗号分隔）")
    ap.add_argument("on_labels", help="注入臂（逗号分隔，可有多个）")
    ap.add_argument("scenes", nargs="?", default="", help="只算这些场景 key（逗号分隔，可选）")
    args = ap.parse_args()

    off_labels = args.off_labels.split(",")
    on_labels = args.on_labels.split(",")
    only = set(args.scenes.split(",")) if args.scenes else None

    off_rows = [r for lab in off_labels for r in load(lab)]
    on_rows = [r for lab in on_labels for r in load(lab)]
    if not off_rows or not on_rows:
        print(f"[skip] 找不到探针产物：report/probe_<label>.jsonl\n"
              f"       基线 {off_labels} 命中 {len(off_rows)} 条｜注入 {on_labels} 命中 {len(on_rows)} 条\n"
              f"       先跑 tools/probe/probe_runner.py --label <label> …")
        return 0
    if only:
        off_rows = [r for r in off_rows if r.get("scene") in only]
        on_rows = [r for r in on_rows if r.get("scene") in only]
    print(f"基线臂 {off_labels} → {len(off_rows)} 条｜注入臂 {len(on_labels)} 个 → {len(on_rows)} 条"
          + (f"｜只算 {sorted(only)}" if only else ""))

    A, B = score(cells(off_rows)), score(cells(on_rows))
    shared = sorted(set(A) & set(B), key=lambda k: (B[k]["distill"] - A[k]["distill"]))
    ma = statistics.fmean(A[k]["distill"] for k in shared)
    mb = statistics.fmean(B[k]["distill"] for k in shared)
    na = sum(A[k]["n"] for k in shared)
    nb = sum(B[k]["n"] for k in shared)
    print(f"\n共有 {len(shared)} 格｜基线样本 {na} 条 / 注入样本 {nb} 条")
    print(f"蒸馏均值：{ma:.3f} → {mb:.3f}  (Δ {mb - ma:+.3f})")
    wins = sum(1 for k in shared if B[k]["distill"] > A[k]["distill"])
    loss = sum(1 for k in shared if B[k]["distill"] < A[k]["distill"])
    print(f"逐格：{wins} 改善 / {loss} 退化 / {len(shared) - wins - loss} 持平")

    # 用「中位字长 / 基线」的比值做符号检验（对中位数摆动更稳）
    import math
    ratios_a = [A[k]["out_med"] / A[k]["base_med"] for k in shared]
    ratios_b = [B[k]["out_med"] / B[k]["base_med"] for k in shared]
    print(f"\n长度比值（输出中位/基线中位）均值：{statistics.fmean(ratios_a):.2f}× → "
          f"{statistics.fmean(ratios_b):.2f}×")
    closer = sum(1 for x, y in zip(ratios_a, ratios_b) if abs(y - 1) < abs(x - 1))
    print(f"更接近 1.0 的格：{closer}/{len(shared)}")
    print(f"\n{'格':<22}{'基线n':>6}{'注入n':>6}{'中位A':>7}{'中位B':>7}{'基线':>6}{'蒸馏A':>8}{'蒸馏B':>8}")
    for k in shared:
        print(f"{k[0] + '/' + k[1]:<22}{A[k]['n']:>6}{B[k]['n']:>6}{A[k]['out_med']:>7.0f}"
              f"{B[k]['out_med']:>7.0f}{A[k]['base_med']:>6.0f}{A[k]['distill']:>8.3f}{B[k]['distill']:>8.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
