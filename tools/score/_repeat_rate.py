"""各臂的同格互异率：不同有效回复数 / 有效回复数，失败与空白另计。

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
import argparse
import hashlib
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

def summarize(rows: list[dict], category: str = "") -> dict:
    selected = [r for r in rows if not category or r.get('cat') == category]
    per: dict[tuple[str, str], list[str]] = defaultdict(list)
    errors = empty = 0
    for row in selected:
        if row.get('error'):
            errors += 1
        elif not isinstance(row.get('reply'), str) or not row['reply'].strip():
            empty += 1
        else:
            per[(row['char'], row['scenario'])].append(row['reply'])
    cells = []
    for (char, sc), reps in sorted(per.items()):
        counts = Counter(reps)
        cells.append(dict(char=char, scenario=sc, n=len(reps), distinct=len(counts),
                          most_repeated=max(counts.values())))
    valid = sum(c['n'] for c in cells)
    distinct = sum(c['distinct'] for c in cells)
    return dict(schema_version=1, category=category, total=len(selected), valid=valid,
                distinct=distinct, errors=errors, empty=empty, cells=cells,
                ratio=distinct / valid if valid else None)


def main() -> int:
    parser = argparse.ArgumentParser(description='有效回复的同格互异率；空批次返回无数据')
    parser.add_argument('labels', help='逗号分隔的批次名')
    parser.add_argument('category', nargs='?', default='', help='仅统计此类别，默认全部')
    args = parser.parse_args()
    rc = 0
    for label in args.labels.split(','):
        if not re.fullmatch(r'[\w.-]+', label):
            parser.error('批次名不能包含路径分隔符')
        path = REPORT / f'probe_{label}.jsonl'
        try:
            raw = path.read_bytes()
            rows = [json.loads(line) for line in raw.decode('utf-8').splitlines() if line.strip()]
            result = summarize(rows, args.category)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            print(f'[repeat] {label}: {exc}', file=sys.stderr)
            rc = 2
            continue
        result.update(label=label, source_sha256=hashlib.sha256(raw).hexdigest())
        (REPORT / f'repeat_{label}.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'\n===== {label} =====')
        for cell in result['cells']:
            print(f"{cell['char']} {cell['scenario']} n={cell['n']} distinct={cell['distinct']} 最多重复={cell['most_repeated']}")
        ratio = f"{result['ratio']:.2f}" if result['ratio'] is not None else '无数据'
        print(f"合计 distinct {result['distinct']}/{result['valid']} = {ratio}；错误 {result['errors']}，空白 {result['empty']}")
        if not result['valid']:
            rc = 2
    return rc


if __name__ == '__main__':
    raise SystemExit(main())
