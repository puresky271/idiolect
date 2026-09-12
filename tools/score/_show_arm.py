"""临时：并排打印某场景在两臂的 6 条回复。"""
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

HERE = Path(__file__).resolve().parent
sys.stdout.reconfigure(encoding="utf-8")
scenario = sys.argv[1]
labels = sys.argv[2].split(",") if len(sys.argv) > 2 else ["gen_off", "gen_on"]
for lab in labels:
    p = REPORT / f"probe_{lab}.jsonl"
    if not p.exists():
        print(f"[{lab}] 缺文件")
        continue
    rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    reps = [r["reply"] for r in rows if r["scenario"] == scenario]
    lens = sorted(len(x) for x in reps)
    med = lens[len(lens) // 2] if lens else 0
    print(f"\n== {lab} · {scenario} · n={len(reps)} 中位 {med} ==")
    for x in reps:
        print(f"  [{len(x):3}] {x!r}")
