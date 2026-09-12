"""元叙述门禁：**角色会读到的每一段字符串**里都不许出现语料/统计/方法论词汇。

`#` 注释与 docstring 不算（不进 prompt），只查真正会被拼进 system prompt 的文本。

覆盖面（2026-09-13 补齐——此前只扫 voice.py，留下三个盲区）：

  1. voice manifest（五个角色包）
  2. **canon 长档案**（`get_canon_profile`）
  3. **style_target 说话尺度块**（全局 + 命中场景两态）
  4. **turn_logic 渲染结果**（门禁矩阵里的全部触发样例）

盲区 #3 是真的漏过一次：`style_target` 的块标题当时写着「实测台词基线」——
`实测` 就在本文件的 HARD 列表里，却从来没人扫过它，于是它一直躺在每个人的
prompt 里。**门禁的价值等于它的覆盖面**，不是它跑绿了。
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

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

# HARD：语料/统计/方法论 词汇 —— 角色绝不该看到「有人在统计我」
META_HARD = [
    "语料", "实测", "专指", "lift", "金标准", "cn train", "蒸馏", "统计",
    "占比", "出现次数", "persona card", "子模块", "manifest", "基线", "中位",
]
# SOFT：只报告不失败 —— 这些词出现在「禁止说 X」的护栏里是合法的
META_SOFT = ["系统", "AI", "prompt", "模块", "角色卡"]

MODULES = {
    "灯": "idiolect.characters.tomori.voice",
    "爱音": "idiolect.characters.anon.voice",
    "乐奈": "idiolect.characters.rana.voice",
    "素世": "idiolect.characters.soyo.voice",
    "立希": "idiolect.characters.taki.voice",
}
CHARS = ["爱音", "灯", "立希", "素世", "乐奈"]


def _report(name: str, text: str) -> int:
    """扫描一段角色可见文本；有 HARD 命中就逐行打出来并返回 1。"""
    hits = [w for w in META_HARD if w in text]
    soft = [w for w in META_SOFT if w in text]
    if hits:
        print(f"[FAIL] {name} len={len(text)} 含元叙述：{hits}")
        for w in hits:
            for i, line in enumerate(text.splitlines()):
                if w in line:
                    print(f"        L{i}: {line.strip()[:110]}")
        return 1
    print(f"[ ok ] {name} len={len(text)}" + (f"  (soft: {soft})" if soft else ""))
    return 0


def scan_surfaces() -> int:
    """canon / style_target / turn_logic 三个此前没被扫过的面。"""
    from idiolect.registry import get_canon_profile, render_turn_special_block
    from idiolect.style_target import build_style_target_block
    import mock_clock as MOCK

    bad = 0
    for char in CHARS:
        bad += _report(f"canon.{char}", get_canon_profile(char) or "")
    for char in CHARS:
        bad += _report(f"style_target.{char}(全局)", build_style_target_block(char, ""))
        bad += _report(f"style_target.{char}(场景)", build_style_target_block(char, "comfort"))

    from dump_turn_logic_gate import CASES
    import idiolect.scene_engine as engine

    seen: set[tuple[str, str]] = set()
    for char, cases in CASES.items():
        for text, want_fire, owner in cases:
            if not want_fire or (char, owner) in seen:
                continue
            seen.add((char, owner))
            engine.reset_session()
            block = render_turn_special_block(
                char, text, session_id=f"gate:{char}:{owner}", is_developer=False,
                mode="chat", now_jst=MOCK.mock_now()) or ""
            bad += _report(f"turn_logic.{char}/{owner}", block)
    return bad


def main() -> int:
    bad = 0
    for name, mod in MODULES.items():
        m = importlib.import_module(mod)
        bad += _report(f"{name}（{mod}）", m.get_voice_manifest())
        for attr in ("NICKNAME_RULE", "KNOWLEDGE_QA_POLICY", "QA_STYLE_LINE"):
            v = getattr(m, attr, "")
            h = [w for w in META_HARD if w in str(v)]
            if h:
                bad += 1
                print(f"        [FAIL] {name}.{attr} 含元叙述 {h}: {v}")
    print("-" * 72)
    bad += scan_surfaces()
    print("PASS" if not bad else f"FAIL x{bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
