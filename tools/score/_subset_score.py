"""按子集聚合 `scene_distill` 的结果：隔离某一批夹具的效果，避免被其它格稀释。

动机：全表池化会把「只改了某几个场景」的效果摊薄。要看某一批夹具（例如某几个场景）
到底动没动，得只在那个子集里比。

用法：
    py -X utf8 tools/score/_subset_score.py gen_off gen_on                    # 全表
    py -X utf8 tools/score/_subset_score.py gen_off gen_on crisis,comfort     # 只看这两类场景
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
import statistics
import sys


def main() -> int:
    ap = argparse.ArgumentParser(description="按场景子集聚合计分（对比两臂）")
    ap.add_argument("arm_a", help="基线臂 label")
    ap.add_argument("arm_b", help="对比臂 label")
    ap.add_argument("scenes", nargs="?", default="", help="场景 key（逗号分隔；留空 = 全部）")
    args = ap.parse_args()

    def load(label: str) -> list[dict]:
        p = REPORT / f"scene_distill_{label}.json"
        if not p.exists():
            print(f"[skip] 缺 {p}\n       先跑 tools/score/scene_distill.py --labels {label}")
            raise SystemExit(0)
        return json.loads(p.read_text(encoding="utf-8"))

    keys = {k for k in args.scenes.split(",") if k} or None
    A, B = load(args.arm_a), load(args.arm_b)

    def sel(rows):
        return [r for r in rows if not keys or r["scene"] in keys]

    sa, sb = sel(A), sel(B)
    if not sa or not sb:
        print(f"[skip] 子集为空（场景 {sorted(keys) if keys else '全部'}）；可用场景见 scene_distill 产物")
        return 0
    print(f"子集 = {sorted(keys) if keys else '全部'}")
    print(f"{args.arm_a}: n={len(sa)} 格｜蒸馏均值 {statistics.fmean(r['distill'] for r in sa):.3f}"
          f"｜中位字长均值 {statistics.fmean(r['out_med'] for r in sa):.1f}"
          f"｜基线中位均值 {statistics.fmean(r['base_med'] for r in sa):.1f}")
    print(f"{args.arm_b}: n={len(sb)} 格｜蒸馏均值 {statistics.fmean(r['distill'] for r in sb):.3f}"
          f"｜中位字长均值 {statistics.fmean(r['out_med'] for r in sb):.1f}"
          f"｜基线中位均值 {statistics.fmean(r['base_med'] for r in sb):.1f}")
    d = statistics.fmean(r["distill"] for r in sb) - statistics.fmean(r["distill"] for r in sa)
    print(f"Δ 蒸馏均值 = {d:+.3f}")

    ma = {(r["char"], r["scene"]): r for r in sa}
    mb = {(r["char"], r["scene"]): r for r in sb}
    wins = sum(1 for k in ma if k in mb and mb[k]["distill"] > ma[k]["distill"])
    loss = sum(1 for k in ma if k in mb and mb[k]["distill"] < ma[k]["distill"])
    print(f"逐格：{wins} 格改善 / {loss} 格退化 / {len(ma) - wins - loss} 格持平")
    for k in sorted(ma, key=lambda k: (mb.get(k, {}).get("distill", 9) - ma[k]["distill"])):
        if k in mb:
            print(f"  {k[0]:<4}{k[1]:<14} {ma[k]['out_med']:>5.0f} → {mb[k]['out_med']:>5.0f}"
                  f"（基线 {ma[k]['base_med']:.0f}）  {ma[k]['distill']:.3f} → {mb[k]['distill']:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
