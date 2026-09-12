"""实验设计计算器：给定待测效应量与实测**单条**噪声，算出需要的样本量。

⚠️ 单位陷阱（2026-09-11 自己踩过，务必留意）：
  `probe_variance.json` 里的 sd 是「**整臂均值**的跨次标准差」（每次采样 8 条），
  不是「**单条样本**的标准差」。用它算样本量会把需求**低估约 4 倍**
  （0.098 vs 实测单条 sd 0.382）——因为 sd_mean = sd_single / sqrt(n_per_run)。
  本脚本因此默认从**探针原始输出**直接算单条 sd，而不是读 probe_variance.json。

实测（乐奈，96 条/臂）：
  · 单条 sd（nominal_start）≈ **0.382** → 96 条/臂的 95% 区间半宽 ≈ ±7.5pp
  · 观测到的 before→after 差 5.1pp，z = 0.93 → **无法拒绝零假设**
  · 要在该效应量下达到显著，需 ~427 条/臂

用法：
  py -X utf8 power_calc.py                                  # 从探针输出实测单条 sd
  py -X utf8 power_calc.py --sd 0.382 --effect 0.05
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

import argparse
import json
import math
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
REPORT = REPORT

# 各指标的「单条 sd」可从探针输出直接算；这里记录已实测值供离线引用
MEASURED_SINGLE_SD = {
    "nominal_start": 0.382,   # 乐奈，96 条/臂实测
    "self_ref": 0.347,
    "le6": 0.450,
}


def n_for(effect: float, sd: float, z: float = 1.96) -> int:
    """两独立样本均值比较（双侧 95%）所需每组样本量。"""
    if effect <= 0:
        return 10 ** 9
    return int(math.ceil((z * sd / effect) ** 2))


def measure_single_sd() -> dict[str, float]:
    """从探针原始输出直接算「单条样本」标准差。"""
    import style_features as S

    pools: dict[str, list[float]] = {"nominal_start": [], "self_ref": [], "le6": []}
    for lbl in ("rana_reg_before", "rana_reg_after", "rana_reg_v2"):
        p = REPORT / f"probe_{lbl}.jsonl"
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if not r.get("reply"):
                continue
            v = S.rana_register_score(r["reply"])
            pools["nominal_start"].append(v["nominal_start"])
            pools["self_ref"].append(v["self_ref"])
            pools["le6"].append(v["le6"])
    return {k: round(statistics.stdev(v), 4) for k, v in pools.items() if len(v) > 2}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sd", type=float, default=0.0)
    ap.add_argument("--effect", type=float, default=0.0)
    args = ap.parse_args()

    sd_map = measure_single_sd() or dict(MEASURED_SINGLE_SD)
    if args.sd:
        sd_map = {"（指定）": args.sd}
    print("单条样本标准差（实测，非均值跨次 SD）")
    for k, v in sd_map.items():
        print(f"  {k:<16}{v}")
    print()

    if args.effect:
        for k, sd in sd_map.items():
            print(f"  效应 {args.effect * 100:.0f}pp 需 {n_for(args.effect, sd)} 条/臂（{k}）")
        return 0

    effects = [0.15, 0.10, 0.05, 0.03]
    header = f"{'指标':<16}" + "".join(f"{f'{int(e * 100)}pp':>10}" for e in effects)
    print("每组所需样本量（双侧 95%，独立两样本）\n")
    print(header)
    print("-" * len(header))
    out: dict[str, dict] = {}
    for name, sd in sd_map.items():
        row = f"{name:<16}"
        out[name] = {"single_sd": sd}
        for e in effects:
            n = n_for(e, sd)
            out[name][f"n_for_{int(e * 100)}pp"] = n
            row += f"{n:>10}"
        print(row)

    print("\n折算：8 场景规模下每条需跑几次（向上取整）\n")
    print(header)
    print("-" * len(header))
    for name, sd in sd_map.items():
        row = f"{name:<16}"
        for e in effects:
            row += f"{math.ceil(n_for(e, sd) / 8):>10}"
        print(row)

    print("\n判读（按 nominal_start 单条 sd=0.382）：")
    print("  · 15pp 级差异：~25 条/臂（8 场景 × 4 次）——便宜，常规门槛")
    print("  · 10pp 级差异：~56 条/臂（8 场景 × 7 次）")
    print("  · 5pp 级差异：~224 条/臂（8 场景 × 28 次）——只在关键决策时做")
    print("  · 3pp 级差异：~622 条/臂 —— 不划算，别做")
    print("\n  另：配对设计在本指标上只提升 1.3 倍效力（见 paired_vs_independent.json），")
    print("      不足以改变上面的量级结论；提高样本量才是可靠手段。")
    (REPORT / "power_calc.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n-> report/power_calc.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())



if __name__ == "__main__":
    raise SystemExit(main())
