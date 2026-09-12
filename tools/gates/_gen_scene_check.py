"""临时：通用场景模块（第二批）触发与正文自测。"""
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

import sys
from pathlib import Path

sys.path.insert(0, str(ROOT))

import idiolect.general_scenes as G  # noqa: E402
import idiolect.scene_engine as engine  # noqa: E402

META = ("语料", "实测", "lift", "金标准", "原作中位", "参照中位", "占比", "频次", "统计")

POS = {
    "crisis": ["我不想活了", "我要是不在了，你们会轻松一点吧", "没有我的话，你们也能做好吧"],
    "comfort": ["我一直在哭", "我快崩溃了", "我真的撑不住了"],
    "low_mood": ["最近好累", "压力好大", "完全提不起劲"],
    "wellwish": ["希望你们一直开心", "我怎么样都行", "我无所谓，你们好就行"],
}
NEG = {
    "crisis": ["我的伞不在了", "那只猫不在了", "明天排练几点开始"],
    "comfort": ["我笑哭了"],
    "low_mood": ["今天午饭吃什么"],
    "wellwish": ["我希望明天别下雨", "明天排练几点开始"],
}
CHARS = ["灯", "爱音", "素世", "立希", "乐奈"]

EXPECT_TITLE = {
    "crisis": "【本轮·对方说了「消失 / 活不下去」这类话】",
    "comfort": "【本轮·对方在哭 / 情绪崩溃】",
    "low_mood": "【本轮·对方说累 / 状态不好】",
    "wellwish": "【本轮·对方只祝愿别人好、把自己漏掉了】",
}


def first_line(block: str) -> str:
    for line in block.splitlines():
        if line.startswith("【本轮"):
            return line
    return block.splitlines()[0] if block else ""


def main() -> int:
    bad = 0
    for scene, texts in POS.items():
        print(f"\n===== {scene} =====")
        for text in texts:
            seen = {}
            for c in CHARS:
                engine.reset_session()
                blk = G.build_general_scene_blocks(c, text, session_id=f"{scene}:{c}")
                tag = first_line(blk[0]) if blk else ""
                seen.setdefault(tag, []).append(c)
                if not blk:
                    bad += 1
                    print(f"  [MISS] {c} / {text}")
                for w in META:
                    if blk and w in blk[0]:
                        bad += 1
                        print(f"  !! {c} 正文含元叙述「{w}」")
            # 每角色正文必须互不相同
            bodies = []
            for c in CHARS:
                engine.reset_session()
                blk = G.build_general_scene_blocks(c, text, session_id=f"d:{scene}:{c}")
                bodies.append(blk[0] if blk else "")
            if len(set(bodies)) != len(CHARS):
                bad += 1
                print(f"  !! {text}: 五角色正文不互异")
            print(f"  [OK ] {text}  标题: {sorted(set(seen))}")
        for text in NEG[scene]:
            for c in CHARS:
                engine.reset_session()
                blk = G.build_general_scene_blocks(c, text, session_id=f"n:{scene}:{c}")
                got = first_line(blk[0]) if blk else ""
                # 只有**命中本场景自己的标题**才算误报；命中别的场景是正常的
                # （通用场景补齐 13 个之后，「明天排练几点开始」本来就该进 schedule）
                if got == EXPECT_TITLE.get(scene):
                    bad += 1
                    print(f"  [FALSE-POS] {c} / {text} -> {got}（不该触发 {scene}）")
    print(f"\n{'PASS' if not bad else f'FAIL x{bad}'}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
