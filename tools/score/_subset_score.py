"""按子集聚合 scene_distill 结果（隔离某批夹具的效果，避免被其它格稀释）。"""
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
from pathlib import Path

REPORT = Path(__file__).resolve().parent / "report"
sys.stdout.reconfigure(encoding="utf-8")
a, b = sys.argv[1], sys.argv[2]
keys = set(sys.argv[3].split(",")) if len(sys.argv) > 3 else None

A = json.loads((REPORT / f"scene_distill_{a}.json").read_text(encoding="utf-8"))
B = json.loads((REPORT / f"scene_distill_{b}.json").read_text(encoding="utf-8"))


def sel(rows):
    return [r for r in rows if not keys or r["scene"] in keys]


sa, sb = sel(A), sel(B)
print(f"子集 = {sorted(keys) if keys else '全部'}")
print(f"{a}: n={len(sa)} 格｜蒸馏均值 {statistics.fmean(r['distill'] for r in sa):.3f}"
      f"｜中位字长均值 {statistics.fmean(r['out_med'] for r in sa):.1f}"
      f"｜基线中位均值 {statistics.fmean(r['base_med'] for r in sa):.1f}")
print(f"{b}: n={len(sb)} 格｜蒸馏均值 {statistics.fmean(r['distill'] for r in sb):.3f}"
      f"｜中位字长均值 {statistics.fmean(r['out_med'] for r in sb):.1f}"
      f"｜基线中位均值 {statistics.fmean(r['base_med'] for r in sb):.1f}")
d = statistics.fmean(r["distill"] for r in sb) - statistics.fmean(r["distill"] for r in sa)
print(f"Δ 蒸馏均值 = {d:+.3f}")

# 逐格
ma = {(r["char"], r["scene"]): r for r in sa}
mb = {(r["char"], r["scene"]): r for r in sb}
wins = sum(1 for k in ma if k in mb and mb[k]["distill"] > ma[k]["distill"])
loss = sum(1 for k in ma if k in mb and mb[k]["distill"] < ma[k]["distill"])
print(f"逐格：{wins} 格改善 / {loss} 格退化 / {len(ma) - wins - loss} 格持平")
for k in sorted(ma, key=lambda k: (mb.get(k, {}).get("distill", 9) - ma[k]["distill"])):
    if k in mb:
        print(f"  {k[0]:<4}{k[1]:<14} {ma[k]['out_med']:>5.0f} → {mb[k]['out_med']:>5.0f}"
              f"（基线 {ma[k]['base_med']:.0f}）  {ma[k]['distill']:.3f} → {mb[k]['distill']:.3f}")
