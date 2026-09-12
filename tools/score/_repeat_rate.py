"""临时：各臂的「同格内重复度」——distinct 回复数 / 总条数。

为什么需要：真实探针显示模型的失效模式是**照抄正文示例**，表现是同一格 6 条高度雷同。
长度指标看不出这个，必须有独立的重复度列。
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
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.stdout.reconfigure(encoding="utf-8")
labels = sys.argv[1].split(",") if len(sys.argv) > 1 else ["gen_off", "gen_on", "gen_on2"]
cat_filter = sys.argv[2] if len(sys.argv) > 2 else "通用场景"

for lab in labels:
    p = REPORT / f"probe_{lab}.jsonl"
    if not p.exists():
        continue
    rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    per: dict[tuple[str, str], list[str]] = defaultdict(list)
    for r in rows:
        per[(r["char"], r["scenario"])].append(r["reply"])
    print(f"\n===== {lab} =====")
    print(f"{'角色':<5}{'夹具':<26}{'n':>3}{'distinct':>9}{'最长重复':>10}")
    tot = dis = 0
    for (char, sc), reps in sorted(per.items()):
        from collections import Counter
        c = Counter(reps)
        n, d = len(reps), len(set(reps))
        top = c.most_common(1)[0][1]
        tot += n
        dis += d
        flag = " ⚠️" if top >= 4 else ("  ·" if top == 3 else "")
        print(f"{char:<5}{sc:<26}{n:>3}{d:>9}{top:>10}{flag}")
    print(f"合计 distinct {dis}/{tot} = {dis / tot:.2f}")
