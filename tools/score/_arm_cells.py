"""两臂逐格对比（中位 / 蒸馏分 / Δ）。

输入是 `scene_distill.py` 的两份产物 `report/scene_distill_<label>.json`，
所以顺序是：先跑探针 → 再跑 `scene_distill.py --labels A,B` → 最后本脚本。

用法：
    py -X utf8 tools/score/_arm_cells.py gen_off gen_on
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
import sys


def main() -> int:
    ap = argparse.ArgumentParser(description="两臂逐格对比（按蒸馏分改善降序）")
    ap.add_argument("arm_a", help="基线臂 label")
    ap.add_argument("arm_b", help="对比臂 label")
    args = ap.parse_args()

    def load(label: str) -> dict:
        p = REPORT / f"scene_distill_{label}.json"
        if not p.exists():
            print(f"[skip] 缺 {p}\n       先跑 tools/score/scene_distill.py --labels {label}")
            raise SystemExit(0)
        return {(r["char"], r["scene"]): r
                for r in json.loads(p.read_text(encoding="utf-8"))}

    A, B = load(args.arm_a), load(args.arm_b)
    print(f"{'角色':<5}{'场景':<14}{'中位A':>7}{'中位B':>7}{'基线':>7}{'蒸馏A':>9}{'蒸馏B':>9}{'Δ':>9}")
    for k in sorted(A, key=lambda k: (B.get(k, {}).get("distill", 9) - A[k]["distill"])):
        o, n = A[k], B.get(k)
        if not n:
            continue
        print(f"{k[0]:<5}{k[1]:<14}{o['out_med']:>7.0f}{n['out_med']:>7.0f}{o['base_med']:>7.0f}"
              f"{o['distill']:>9.3f}{n['distill']:>9.3f}{n['distill'] - o['distill']:>+9.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
