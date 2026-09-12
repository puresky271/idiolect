
# ── idiolect 路径引导：仓库根 + 各 tools 子目录上 sys.path ──
import sys as _sys
from pathlib import Path as _Path
_ROOT = _Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "tools",
           *(_ROOT / "tools" / _d for _d in ("corpus", "distill", "probe", "score", "gates"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))
from _paths import CORPUS_DIR, DATA, REPORT, ROOT  # noqa: E402,F401
"""按场景统计**质量信号**（助手腔/越界/复读），而不是长度比值。

动机：长度偏差多是参照物错配（钩子类问题天然更长），
挑「该补哪个场景」要看**有没有真的出戏**。这里用确定性检测器：
  · idiolect.tone.detect —— 存在宣言 / 元叙述 / 心理归因 / 对仗 / 客服腔 / 视觉声称
  · 结构复读 —— 同一夹具 N 次生成里，起手词/句式高度重复（单轮检测器抓不到的病灶）
"""
import collections
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))
sys.path.insert(0, str(HERE))
from idiolect.tone import detect

LABELS = ('rest_scenes', 'prod_scene', 'life_hooks', 'prod_playalong')

# 起手 2 字，用来量「同一夹具多次生成是否同质」
def head2(t: str) -> str:
    t = re.sub(r"^[\s·…。，、！？~～—（(]+", "", str(t or ""))
    return t[:2]


tot = collections.Counter()
per_scene = collections.defaultdict(lambda: collections.Counter())
for lab in LABELS:
    p = REPORT / f'probe_{lab}.jsonl'
    if not p.exists():
        continue
    rows = [json.loads(l) for l in p.read_text(encoding='utf-8').splitlines() if l.strip()]
    rows = [r for r in rows if r.get('reply') and not r.get('error')]
    for r in rows:
        scene = r.get('scene') or '(全局)'
        key = (r['char'], scene)
        hits = detect(r['reply'], r['char'])
        per_scene[key]['n'] += 1
        if hits:
            per_scene[key]['tone'] += 1
            for k in hits:
                per_scene[key][k] += 1

print('=== 助手腔命中率（按 角色×场景，仅列有命中的）===')
rowsout = []
for (char, scene), c in per_scene.items():
    if c['tone']:
        rowsout.append((c['tone'] / c['n'], char, scene, c['tone'], c['n'], dict(c)))
for rate, char, scene, hit, n, c in sorted(rowsout, reverse=True):
    kinds = {k: v for k, v in c.items() if k not in ('n', 'tone')}
    print(f'  {char:4} {scene:14} {hit:3}/{n:3} = {rate:5.1%}   {kinds}')

print()
print('=== 结构复读：同一夹具 N 次生成里最常见起手占比 ===')
rep = []
for lab in LABELS:
    p = REPORT / f'probe_{lab}.jsonl'
    if not p.exists():
        continue
    by = collections.defaultdict(list)
    for l in p.read_text(encoding='utf-8').splitlines():
        if not l.strip():
            continue
        r = json.loads(l)
        if r.get('reply') and not r.get('error'):
            by[(r['char'], r['scenario'], r.get('scene') or '(全局)')].append(r['reply'])
    for (char, scen, scene), reps in by.items():
        if len(reps) < 6:
            continue
        c = collections.Counter(head2(t) for t in reps)
        top, cnt = c.most_common(1)[0]
        rep.append((cnt / len(reps), char, scen, scene, top, cnt, len(reps)))
for rate, char, scen, scene, top, cnt, n in sorted(rep, reverse=True)[:12]:
    print(f'  {rate:5.1%}  {char:4} {scen:24} 起手「{top}」×{cnt}/{n}  scene={scene}')
