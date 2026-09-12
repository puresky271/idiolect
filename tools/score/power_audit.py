"""验算 power_calc 的结论与实测是否自洽。

疑点：probe_variance.json 里的 sd 是「**整臂均值**的跨次标准差」，
      不是「单条样本」的标准差。用错量纲会严重低估所需样本量。
      实测反证：96 条/臂的三臂比较也没分辨出 3pp 差异，
      而 power_calc 说 41 条/臂就够——两者矛盾，必须查清。

做法：把 96 条/臂的输出当总体，直接看「其子样本均值的抽样标准差」，
      再与单条 SD 的理论公式对比。
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
import math
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import style_features as S  # noqa: E402

REPORT = REPORT


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="功效验算：从探针输出反推单条标准差，核对所需样本量")
    ap.add_argument("--labels", default="rana_reg_before,rana_reg_after,rana_reg_v2",
                    help="要验算的臂 label（逗号分隔；默认是历史上那三臂）")
    args = ap.parse_args()

    print("=== 用探针输出反推「单条」标准差 ===\n")
    print(f"{'臂':<18}{'n':>5}{'均值':>9}{'单条sd':>9}{'均值SE(理论)':>13}")
    print("-" * 56)
    per_arm: dict[str, list[float]] = {}
    for lbl in [x for x in args.labels.split(",") if x]:
        p = REPORT / f"probe_{lbl}.jsonl"
        if not p.exists():
            continue
        xs: list[float] = []
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("reply"):
                xs.append(S.rana_register_score(r["reply"])["nominal_start"])
        if len(xs) < 2:
            continue
        per_arm[lbl] = xs
        m = statistics.fmean(xs)
        sd = statistics.stdev(xs)
        se = sd / math.sqrt(len(xs))
        print(f"{lbl:<18}{len(xs):>5}{m:>9.3f}{sd:>9.3f}{se:>13.4f}")

    if not per_arm:
        print(f"[skip] 找不到可用的探针产物（report/probe_<label>.jsonl，label ∈ {args.labels}）。\n"
              f"       先跑 tools/probe/probe_runner.py --label <label> …，\n"
              f"       或用 --labels 指定你自己的臂；只想估算需求样本量用 tools/score/power_calc.py。")
        return 0

    # 整臂均值的跨次 SD（probe_variance.json）应当 ≈ 单条sd / sqrt(每次条数)
    vp = REPORT / "probe_variance.json"
    if vp.exists():
        d = json.loads(vp.read_text(encoding="utf-8"))
        sd_mean_across_reps = d["summary"]["nominal_start"]["sd"]
        per_run_n = d["per_repeat"][0]["n"]
        print(f"\nprobe_variance.json：每次采样 {per_run_n} 条，"
              f"整臂均值的跨次 SD = {sd_mean_across_reps:.4f}")
        # 由跨次 SD 反推单条 SD
        implied_single = sd_mean_across_reps * math.sqrt(per_run_n)
        print(f"→ 由它反推的「单条 sd」≈ {implied_single:.4f}")
        xs = list(per_arm.values())[0]
        actual_single = statistics.stdev(xs)
        print(f"→ 实测「单条 sd」≈ {actual_single:.4f}")
        print(f"→ 两者{'一致' if abs(implied_single - actual_single) < 0.05 else '**不一致**'}")

    # 用「单条 sd」正确算样本量
    xs = list(per_arm.values())[0]
    sd1 = statistics.stdev(xs)
    print(f"\n=== 正确的样本量（单条 sd = {sd1:.3f}）===\n")
    print(f"{'效应量':<10}{'每组条数':>10}{'8场景×每条跑':>14}")
    print("-" * 36)
    for eff in (0.15, 0.10, 0.05, 0.03):
        n = math.ceil((1.96 * sd1 / eff) ** 2)
        print(f"{f'{int(eff * 100)}pp':<10}{n:>10}{math.ceil(n / 8):>14}")

    # 解释三臂为何无法分辨
    if len(per_arm) >= 2:
        arms = list(per_arm.items())
        m1, m2 = statistics.fmean(arms[0][1]), statistics.fmean(arms[1][1])
        diff = abs(m2 - m1)
        se = sd1 * math.sqrt(1 / len(arms[0][1]) + 1 / len(arms[1][1]))
        z = diff / se if se else 0
        print(f"\n=== 为什么 before/after 无法分辨 ===\n")
        print(f"观测差 {diff * 100:.1f}pp，标准误 {se * 100:.1f}pp，z = {z:.2f}")
        print(f"（需要 |z| > 1.96 才算显著；实测 z={z:.2f} → 无法拒绝零假设）")
        print(f"要达到 |z|=1.96 且保持该效应量，需每条臂约 "
              f"{math.ceil(2 * (1.96 * sd1 / diff) ** 2)} 条" if diff > 0 else "")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
