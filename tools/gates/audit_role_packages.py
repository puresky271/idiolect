
# ── idiolect 路径引导：仓库根 + 各 tools 子目录上 sys.path ──
import sys as _sys
from pathlib import Path as _Path
_ROOT = _Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "tools",
           *(_ROOT / "tools" / _d for _d in ("corpus", "distill", "probe", "score", "gates"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))
from _paths import CORPUS_DIR, DATA, REPORT, ROOT  # noqa: E402,F401
"""素世 / 乐奈 角色包对齐审计：五包逐项对照，找出真实缺口。"""
import importlib
import inspect
from pathlib import Path

PKGS = ['anon', 'soyo', 'tomori', 'taki', 'rana']
PKG_DIR = ROOT / 'idiolect' / 'characters'
# 宿主项目里的 VOICE_CONSTRAINTS.md / PROGRESS.md / voice_mood.py 不随本仓库发布
# （前两份是开发记录，后一份依赖宿主的 mood 基建），所以不列进来当期望组件。
COMPONENTS = ['__init__.py', 'api.py', 'canon.py', 'voice.py', 'voice_check', 'turn_logic']

print(f"{'组件':22}" + ''.join(f'{p:>8}' for p in PKGS))
print('-' * 62)
for comp in COMPONENTS:
    row = f'{comp:22}'
    for p in PKGS:
        path = PKG_DIR / p / comp
        row += f"{('  ✓' if path.exists() else '  ✗'):>8}"
    print(row)

print()
print('=== 角色包 API 契约（idiolect/registry.py 暴露的）===')
import sys
sys.path.insert(0, str(ROOT))
import idiolect.registry as rp
NAMES = {'anon': '爱音', 'soyo': '素世', 'tomori': '灯', 'taki': '立希', 'rana': '乐奈'}
API = ['render_supplemental_blocks', 'get_voice_manifest', 'get_canon_profile',
       'get_canon_facts', 'postprocess_reply']
print(f"{'API':26}" + ''.join(f'{p:>8}' for p in PKGS))
for a in API:
    row = f'{a:26}'
    for p in PKGS:
        pkg = rp.get_role_package(NAMES[p])
        row += f"{('  ✓' if pkg and hasattr(pkg, a) else '  ✗'):>8}"
    print(row)

print()
print('=== voice_check 阈值对照（只素世/乐奈有）===')
for p in ('soyo', 'rana'):
    try:
        m = importlib.import_module(f'{p}.voice_check')
        vals = {k: getattr(m, k) for k in dir(m)
                if k.isupper() and isinstance(getattr(m, k), (int, float, str, tuple))}
        print(f'  {p}: {vals}')
    except Exception as e:  # noqa: BLE001
        print(f'  {p}: 导入失败 {e}')

print()
print('=== turn_logic 入口暴露的子系统 ===')
for p in PKGS:
    try:
        m = importlib.import_module(f'idiolect.characters.{p}.turn_logic')
        src = inspect.getsource(m)
        n = src.count('try:')
        keys = [k for k in dir(m) if k.endswith('_SCENES')]
        # 2026-09-12：素世/乐奈的深模块走 `_DEEP_MODULES` 循环分发，
        # 单看 `try:` 数量会低估深度 → 一并报出深模块清单。
        deep = [k for k, _ in getattr(m, '_DEEP_MODULES', ())]
        # 目录里实际的模块文件数（排除 __init__），作为「真模块数量」的客观口径
        n_files = len([f for f in (PKG_DIR / p / 'turn_logic').glob('*.py')
                       if f.name != '__init__.py'])
        print(f'  {p:7} try-块 {n:>2} 个｜模块文件 {n_files}｜'
              f'SCENES {keys}｜DEEP {deep}')
    except Exception as e:  # noqa: BLE001
        print(f'  {p:7} 导入失败 {e}')
