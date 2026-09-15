"""将探针批次导出为无需联网的交互证据报告，不重新计算评分。"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _paths import REPORT


def load_batch(directory: Path, label: str) -> dict:
    if not re.fullmatch(r'[\w.-]+', label) or label in ('.', '..'):
        raise ValueError(f'无效批次名：{label!r}')
    path = directory / f'probe_{label}.jsonl'
    rows = []
    for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict) or not all(isinstance(row.get(k), str) for k in ('char', 'scenario', 'reply')):
            raise ValueError(f'{path.name}:{number} 缺少字符型 char/scenario/reply')
        rows.append(row)
    summary_path = directory / f'probe_{label}_summary.json'
    score_path = directory / f'scene_distill_{label}.json'
    summary = json.loads(summary_path.read_text(encoding='utf-8')) if summary_path.exists() else {}
    scores = json.loads(score_path.read_text(encoding='utf-8')) if score_path.exists() else []
    repeat_path = directory / f'repeat_{label}.json'
    repetition = json.loads(repeat_path.read_text(encoding='utf-8')) if repeat_path.exists() else None
    repetition_status = 'missing'
    if isinstance(repetition, dict):
        repetition_status = 'available' if repetition.get('source_sha256') == hashlib.sha256(path.read_bytes()).hexdigest() else 'stale'
    if repetition_status != 'available':
        repetition = None
    if not isinstance(summary, dict) or not isinstance(scores, list):
        raise ValueError(f'{label} 的汇总或场景评分格式不正确')
    return dict(label=label, rows=rows, summary=summary, scores=scores,
                repetition=repetition, repetition_status=repetition_status,
                sources=[path.name, summary_path.name if summary_path.exists() else None,
                         score_path.name if score_path.exists() else None])


def compare_conditions(left: dict, right: dict) -> list[dict]:
    """字段级证据，不将元数据一致升级为统计可比性或改善判定。"""
    fields = {
        'model': '模型', 'temperature': 'Temperature', 'max_tokens': '输出预算',
        'thinking': '思考模式', 'extra_body': '附加参数', 'clock': '时钟',
        'dry_run': '是否干跑', 'assembly': '装配配置（实验变量）',
        'fixture_sha256': '夹具指纹', 'scenarios_sha256': '场景计划指纹',
        'scoring_profiles_sha256': '评分画像指纹', 'scene_baseline_sha256': '场景基线指纹',
        'probe_source_sha256': '探针代码指纹（实验变量）',
    }
    a = left.get('summary', {}).get('metadata') or {}
    b = right.get('summary', {}).get('metadata') or {}
    rows = []
    for key, title in fields.items():
        x, y = a.get(key), b.get(key)
        known = key in a and key in b and x is not None and y is not None and x != '' and y != ''
        if key in ('clock', 'assembly', 'fixture_sha256') and (not x or not y):
            known = False
        rows.append(dict(field=key, title=title, left=x, right=y,
                         status=('same' if x == y else 'different') if known else 'unknown'))
    return rows


def render(batches: list[dict]) -> str:
    if not batches:
        raise ValueError('至少需要一个批次')
    template = Path(__file__).with_name('report_template.html').read_text(encoding='utf-8')
    # script 数据区也会被 HTML 解析；不允许回复中的闭合标签逃逸。
    enriched = [{**batch, 'comparisons': {other['label']: compare_conditions(batch, other)
                 for other in batches if other['label'] != batch['label']}} for batch in batches]
    payload = json.dumps(enriched, ensure_ascii=False, allow_nan=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    return template.replace('__BATCH_DATA__', payload)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--labels', required=True, help='逗号分隔的批次名')
    parser.add_argument('--out', type=Path, default=REPORT / 'evaluation.html')
    args = parser.parse_args()
    try:
        labels = list(dict.fromkeys(s.strip() for s in args.labels.split(',') if s.strip()))
        html = render([load_batch(REPORT, label) for label in labels])
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(html, encoding='utf-8')
    except (OSError, ValueError) as exc:
        parser.exit(2, f'[report] {exc}\n')
    print(f'[report] 离线报告：{args.out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
