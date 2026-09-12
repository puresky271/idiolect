"""临时：两臂逐格对比（中位 / 蒸馏分 / Δ）。"""
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
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent / "report"
sys.stdout.reconfigure(encoding="utf-8")
a, b = sys.argv[1], sys.argv[2]
A = {(r["char"], r["scene"]): r for r in json.loads((HERE / f"scene_distill_{a}.json").read_text(encoding="utf-8"))}
B = {(r["char"], r["scene"]): r for r in json.loads((HERE / f"scene_distill_{b}.json").read_text(encoding="utf-8"))}
print(f"{'角色':<5}{'场景':<11}{'中位A':>6}{'中位B':>6}{'基线':>6}{'蒸馏A':>8}{'蒸馏B':>8}{'Δ':>8}")
for k in sorted(A, key=lambda k: (B.get(k, {}).get("distill", 9) - A[k]["distill"])):
    o, n = A[k], B.get(k)
    if not n:
        continue
    print(f"{k[0]:<5}{k[1]:<11}{o['out_med']:>6.0f}{n['out_med']:>6.0f}{o['base_med']:>6.0f}"
          f"{o['distill']:>8.3f}{n['distill']:>8.3f}{n['distill'] - o['distill']:>+8.3f}")
