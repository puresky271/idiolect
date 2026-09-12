"""临时：6 个深模块的触发 / 去重 / 文本洁净自测（未接线时也能跑）。"""
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

from idiolect.characters.rana.turn_logic import cat_talk, interesting, nap, space  # noqa: E402
from idiolect.characters.soyo.turn_logic import home, wind_ensemble  # noqa: E402

MODULES = {
    "soyo.home": home,
    "soyo.wind": wind_ensemble,
    "rana.interesting": interesting,
    "rana.space": space,
    "rana.cat": cat_talk,
    "rana.nap": nap,
}

# 角色读到的文本里不许出现的东西（对齐 test_scene_turn_logic 的 HARD 表 + 语料元词）
META = ("语料", "实测", "lift", "金标准", "原作中位", "参照中位", "占比", "频次", "统计")

POSITIVE = {
    "soyo.home": ["今天在家做什么？妈妈回来吃饭吗", "妈妈工作很忙吧", "你平时自己做家务吗",
                  "听说你爸妈离婚了", "家里就你一个人吗"],
    "soyo.wind": ["听说你以前在吹奏乐社拉低音大提琴？", "你在吹奏乐社待过吧",
                  "低音大提琴和贝斯有什么区别", "你为什么后来去弹贝斯了", "你会看乐谱吗"],
    "rana.interesting": ["你觉得我们乐队的人怎么样？", "你怎么看灯", "这个演出有趣吗",
                         "刚才那个挺好玩的", "好无聊啊", "你以前说过有趣的女人吧"],
    "rana.space": ["你外婆的店是个什么样的地方", "外婆来看你演出了吗", "SPACE 还在营业吗",
                   "你的归宿是哪里", "你外婆弹吉他吗"],    "rana.cat": ["刚才在门口看到一只猫", "你喂过猫吗", "你是不是能听懂猫说话",
                 "那只猫在叫", "这里有猫吗"],
    # 注：「你现在在干嘛」**故意不触发**——nap 是 text-driven（无 睡/困 线索就不猜她困）
    "rana.nap": ["你是不是又睡着了", "你平时在哪睡觉", "好困", "你昨晚睡了没", "要不要睡一会"],
}

NEGATIVE = {
    "soyo.home": ["明天排练几点开始", "你觉得这个方案怎么样", "今天天气不错"],
    "soyo.wind": ["明天排练几点开始", "今天天气不错", "要不要喝咖啡"],
    "rana.interesting": ["明天排练几点开始", "今天天气不错"],
    "rana.space": ["明天排练几点开始", "今天天气不错"],
    "rana.cat": ["明天排练几点开始", "今天天气不错"],
    "rana.nap": ["明天排练几点开始", "今天天气不错"],
}


def main() -> int:
    bad = 0
    for name, mod in MODULES.items():
        fn = next(v for k, v in vars(mod).items() if k.startswith("build_") and k.endswith("_special_block"))
        reset = next(v for k, v in vars(mod).items() if k == "reset_session_fired")
        print(f"\n===== {name} =====")
        for i, text in enumerate(POSITIVE[name]):
            reset()
            got = fn(text, session_id=f"{name}-p{i}")
            flag = "OK " if got else "MISS"
            if not got:
                bad += 1
            print(f"  [{flag}] {text}  -> {len(got)} chars | {got.splitlines()[0] if got else ''}")
            for w in META:
                if w in got:
                    bad += 1
                    print(f"        !! 正文含元叙述「{w}」")
        for i, text in enumerate(NEGATIVE[name]):
            reset()
            got = fn(text, session_id=f"{name}-n{i}")
            if got:
                bad += 1
                print(f"  [FALSE-POS] {text} -> {got.splitlines()[0]}")
        # 去重：同一 session 第二次**不得重复同一块**（可以因更具体层级而换一块）
        reset()
        a = fn(POSITIVE[name][0], session_id="dedup")
        b = fn(POSITIVE[name][0], session_id="dedup")
        if a and b and a == b:
            bad += 1
            print("  !! 去重失效（同 session 第二次仍注入同一块）")
        elif a and not b:
            print("  [OK ] 去重生效（第二次为空）")
        elif a and b:
            print(f"  [OK ] 去重生效（第二次换层：{b.splitlines()[0]}）")
        # developer 模式
        reset()
        if fn(POSITIVE[name][0], session_id="dev", is_developer=True):
            bad += 1
            print("  !! developer 模式仍注入")
    print(f"\n{'PASS' if not bad else f'FAIL x{bad}'}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
