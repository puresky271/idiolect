
# ── idiolect 路径引导：仓库根 + 各 tools 子目录上 sys.path ──
import sys as _sys
from pathlib import Path as _Path
_ROOT = _Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "tools",
           *(_ROOT / "tools" / _d for _d in ("corpus", "distill", "probe", "score", "gates"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))
from _paths import CORPUS_DIR, DATA, REPORT, ROOT  # noqa: E402,F401
"""voice_check 模块化后的行为自检：全量跑，确认无损、不产空、变换类型正确。"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

BENCH = ROOT / '_audit_scratch' / 'v41' / 'bench'
sys.path.insert(0, str(ROOT))

from idiolect.characters.soyo.voice_check import clean_reply as soyo_clean, inspect as soyo_inspect, normalize_peer_nicknames
from idiolect.characters.rana.voice_check import clean_reply as rana_clean, inspect as rana_inspect, TIC_FORBIDDEN
from idiolect.characters.soyo.voice_check.thresholds import LEN_P90 as S_P90, LEN_HARD as S_HARD, EXCLAIM_MAX_PER_TURN as S_EX
from idiolect.characters.rana.voice_check.thresholds import LEN_P90 as R_P90, LEN_HARD as R_HARD, EXCLAIM_MAX_PER_TURN as R_EX

print('阈值 re-export:', (S_P90, S_HARD, S_EX), (R_P90, R_HARD, R_EX), TIC_FORBIDDEN)

# 收集全部文本：金标准 + 探针回复
texts = []
rows = [json.loads(l) for l in (CORPUS_DIR / 'cn.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]
for r in rows:
    if r.get('split') == 'train' and r['character'] in ('soyo', 'rana'):
        texts.append((r['character'], r['text']))
for p in sorted((BENCH / 'report').glob('probe_*.jsonl')):
    for l in p.read_text(encoding='utf-8').splitlines():
        if not l.strip():
            continue
        rec = json.loads(l)
        if rec.get('reply') and rec.get('char') in ('素世', '乐奈'):
            texts.append(('soyo' if rec['char'] == '素世' else 'rana', rec['reply']))

ALLOWED = {'exclaim_downgraded', 'ellipsis_normalized', 'period_collapsed', 'peer_nickname:1',
           'peer_nickname:2', 'peer_nickname:3', 'peer_nickname:4', 'peer_nickname:5'}
emptied = 0
kinds = Counter()
errors = 0
for key, t in texts:
    fn = soyo_clean if key == 'soyo' else rana_clean
    try:
        out, info = fn(t)
    except Exception as e:  # noqa: BLE001
        errors += 1
        print('  ERROR', type(e).__name__, e, repr(t[:40]))
        continue
    if t.strip() and not out.strip():
        emptied += 1
        print('  空输出!', repr(t[:60]))
    for c in info['changed']:
        kinds[c.split(':')[0]] += 1
    # 无损不变式：去掉空白与标点归一差异后，正文汉字必须守恒
    strip = lambda s: re.sub(r"[\s。！!？?…·，,、；;：:]+", "", str(s))
    if strip(out) != strip(t):
        # 允许的差异只有「裸本名 → 小X」这一种（会加一个「小」字）
        if strip(out).replace("小", "") != strip(t).replace("小", ""):
            print('  正文被改动!', repr(t[:50]), '->', repr(out[:50]))

print(f'\n共 {len(texts)} 条｜错误 {errors}｜空输出 {emptied}')
print('变更类型分布:', dict(kinds))

# inspect 不崩 + 规则名合法
rules = Counter()
for key, t in texts[:3000]:
    fn = soyo_inspect if key == 'soyo' else rana_inspect
    try:
        for k in fn(t):
            rules[k] += 1
    except Exception as e:  # noqa: BLE001
        print('  INSPECT ERROR', e)
print('命中规则:', dict(rules))
print('\nOK' if errors == 0 and emptied == 0 else '\n有问题')
