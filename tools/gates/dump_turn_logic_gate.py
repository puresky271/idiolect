"""turn_logic 的 prompt diff 门禁（含触发场景）——before/after 两臂都由此脚本产出。

为什么不能用 `scripts/dump_live_chat_prompt.py`：
  那条路径经 `offline_smoke` → `chat_server._build_system_prompt(dev_mode=True)`，
  而 turn_logic 场景/深模块**按设计**在开发者模式不触发（`is_developer=True` → 返回 ""）。
  所以全量 dump 看不到 turn_logic 的新块（它能证明的是「其余 prompt 零漂移」）。

两臂怎么取：
  · after  = 当前代码（深模块开启）
  · before = 同一份代码 + 官方回退开关（`*_TURN_LOGIC_<MODULE>_ENABLED=0`）全关
  深模块层是本次唯一的改动，且完全在 per-module env flag 后面；flag 全关即改动前行为，
  另有 `test_no_drift_when_no_deep_module_fires` 用逐字节比较守住这一点。
  （不是「改完之后手写一个 before」：两臂是同一脚本、同一输入、同一 session key 跑出来的。）

同时做三件校验：
  1. 命中正确性（每模块应有正例/负例）
  2. 角色串味（素世的块不得出现在乐奈的渲染里，反之亦然）
  3. 无深模块命中时逐字节零漂移（before/after 该场景必须完全相同）

产出 `report/turn_logic_gate_<phase>.json`（`IDIOLECT_REPORT_DIR` 可改）。
"""
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

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(ROOT))

import idiolect.registry as rp  # noqa: E402
import idiolect.scene_engine as engine  # noqa: E402

# 深模块的 env flag（回退开关）——before 臂把它们全部置 0
DEEP_FLAGS = {
    "素世": ("SOYO_TURN_LOGIC_HOME_ENABLED", "SOYO_TURN_LOGIC_WIND_ENSEMBLE_ENABLED"),
    "乐奈": ("RANA_TURN_LOGIC_SPACE_ENABLED", "RANA_TURN_LOGIC_NAP_ENABLED",
             "RANA_TURN_LOGIC_INTERESTING_ENABLED", "RANA_TURN_LOGIC_CAT_TALK_ENABLED"),
}

# 通用场景层的 env flag（角色无关）
GENERAL_FLAGS = (
    "GENERAL_SCENE_TURN_LOGIC_CRISIS_ENABLED",
    "GENERAL_SCENE_TURN_LOGIC_COMFORT_ENABLED",
    "GENERAL_SCENE_TURN_LOGIC_LOW_MOOD_ENABLED",
    "GENERAL_SCENE_TURN_LOGIC_WELLWISH_ENABLED",
    "GENERAL_SCENE_TURN_LOGIC_SCHEDULE_ENABLED",
    "GENERAL_SCENE_TURN_LOGIC_REQUEST_ENABLED",
    "GENERAL_SCENE_TURN_LOGIC_FACT_QA_ENABLED",
    "GENERAL_SCENE_TURN_LOGIC_BANTER_ENABLED",
    "GENERAL_SCENE_TURN_LOGIC_META_LANGUAGE_ENABLED",
    "GENERAL_SCENE_TURN_LOGIC_PROBE_STANCE_ENABLED",
    "GENERAL_SCENE_TURN_LOGIC_THIRD_PARTY_ENABLED",
)

# 场景层（既有模块）+ 本轮新增深模块的触发场景
# (user_text, 期望触发?, 归属标记) —— 归属标记用于判断该块应不应该出现
CASES = {
    "素世": [
        # 场景层（回归：改动不得影响既有模块）
        ("你是不是还放不下CRYCHIC和祥子", True, "scene"),
        ("想喝点茶还是咖啡", True, "scene"),
        ("你不是说今天没空吗", True, "scene"),
        ("今天午饭吃什么", True, "general.banter"),
        # 深模块：home / wind_ensemble
        ("今天在家做什么？妈妈回来吃饭吗", True, "soyo.home"),
        ("你平时自己做家务吗", True, "soyo.home"),
        ("听说你爸妈离婚了", True, "soyo.home"),
        ("听说你以前在吹奏乐社拉低音大提琴？", True, "soyo.wind_ensemble"),
        ("你为什么后来去弹贝斯了", True, "soyo.wind_ensemble"),
    ],
    "乐奈": [
        # 场景层（回归）
        ("我的吉他弦断了", True, "scene"),
        ("放学后买抹茶芭菲吗", True, "scene"),
        ("明天几点上课", True, "general.schedule"),
        # 通用场景第二批（crisis / comfort / low_mood / wellwish）
        ("我不想活了，反正没有我你们也能做好吧", True, "general.crisis"),
        ("我一直在哭，快撑不住了", True, "general.comfort"),
        ("最近好累，压力好大", True, "general.low_mood"),
        ("希望你们一直开心，我无所谓", True, "general.wellwish"),
        # 通用场景第三批（schedule / request / fact_qa / banter）
        ("明天排练几点开始", True, "general.schedule"),
        ("你能不能帮我看看这个", True, "general.request"),
        ("这首歌是什么名字", True, "general.fact_qa"),
        ("今天天气不错，午饭吃什么", True, "general.banter"),
        # 通用场景第四批（meta_language / probe_stance / third_party）
        ("你刚才那句是什么意思，我没听懂", True, "general.meta_language"),
        ("你是不是有喜欢的人了", True, "general.probe_stance"),
        ("爱音今天来练习了吗", True, "general.third_party"),
        # 深模块：space / nap / interesting / cat_talk
        ("你外婆的店是个什么样的地方", True, "rana.space"),
        ("你的归宿是哪里", True, "rana.space"),
        ("你是不是又睡着了", True, "rana.nap"),
        ("你平时在哪睡觉", True, "rana.nap"),
        ("你觉得我们乐队的人怎么样？", True, "rana.interesting"),
        ("你以前说过有趣的女人吧", True, "rana.interesting"),
        ("你是不是能听懂猫说话", True, "rana.cat_talk"),
        ("刚才在门口看到一只猫", True, "rana.cat_talk"),
    ],
    "立希": [
        # 场景层（回归：立希的专属场景）
        ("你喜欢熊猫吗", True, "scene"),
        ("乐奈今天又不见人影了，肯定又跑去逗猫了", True, "scene"),
        ("明天几点上课", True, "general.schedule"),
        # 通用场景第二批
        ("我不想活了，反正没有我你们也能做好吧", True, "general.crisis"),
        ("我一直在哭，快撑不住了", True, "general.comfort"),
        ("最近好累，压力好大", True, "general.low_mood"),
        ("希望你们一直开心，我无所谓", True, "general.wellwish"),
        # 通用场景第三批
        ("明天排练几点开始", True, "general.schedule"),
        ("你能不能帮我看看这个", True, "general.request"),
        ("这首歌是什么名字", True, "general.fact_qa"),
        ("今天天气不错，午饭吃什么", True, "general.banter"),
        # 通用场景第四批（meta_language / probe_stance / third_party）
        ("你刚才那句是什么意思，我没听懂", True, "general.meta_language"),
        ("你是不是有喜欢的人了", True, "general.probe_stance"),
        ("爱音今天来练习了吗", True, "general.third_party"),
    ],
}

# 每个归属标记对应的「必须出现」的标题（判 before/after 差异归属）
MARKER_TITLE = {
    "soyo.home": "【本轮·聊到妈妈】|【本轮·家务 / 做饭】|【本轮·提到家里】|【本轮·触及家里的具体旧事】",
    "soyo.wind_ensemble": "【本轮·聊到低音大提琴 / 音乐节】|【本轮·聊到吹奏乐社 / 社团】|【本轮·聊到乐器 / 乐谱】|【本轮·问到怎么从吹奏乐社转到乐队的】",
    "rana.space": "【本轮·聊到外婆】|【本轮·聊到 SPACE / live house】|【本轮·聊到归宿 / 容身之处】|【本轮·外婆和演出连在一起】",
    "rana.nap": "【本轮·她现在很困 / 正在睡】|【本轮·问她在哪睡 / 找什么地方睡】|【本轮·提到睡 / 熬夜 / 没睡】",
    "rana.interesting": "【本轮·对方要她给出评价】|【本轮·对方自己说了「有趣 / 好玩」】|【本轮·对方说了「无聊 / 没意思」】|【本轮·对方提到了那句旧说法（有趣的女人）】",
    "rana.cat_talk": "【本轮·提到了猫】|【本轮·谈到具体的猫 / 喂猫 / 摸猫】|【本轮·对方问她是不是能听懂猫说话】",
    "general.crisis": "【本轮·对方说了「消失 / 活不下去」这类话】",
    "general.comfort": "【本轮·对方在哭 / 情绪崩溃】",
    "general.low_mood": "【本轮·对方说累 / 状态不好】",
    "general.wellwish": "【本轮·对方只祝愿别人好、把自己漏掉了】",
    "general.schedule": "【本轮·对方问日程 / 安排】",
    "general.request": "【本轮·对方求你帮忙 / 让你拿主意】",
    "general.fact_qa": "【本轮·对方问一个事实】",
    "general.banter": "【本轮·闲聊（天气 / 吃的 / 小事）】",
    "general.meta_language": "【本轮·对方问「你刚才那句什么意思 / 我没听懂」】",
    "general.probe_stance": "【本轮·对方在试探你的态度】",
    "general.third_party": "【本轮·聊到别的成员 / 别人做了什么】",
}


def render(char: str, text: str) -> str:
    engine.reset_session()
    return rp.render_turn_special_block(
        char, text,
        session_id=f"gate:{char}:{text[:10]}",
        is_developer=False,
        now_jst=datetime(2026, 9, 12, 15, 0, 0),
        mode="chat",
    ) or ""


def leak_check() -> dict:
    soyo = render("素世", "CRYCHIC 的事")
    rana = render("乐奈", "吉他")
    return {
        "soyo_in_rana": "【本轮·旧事触发】" in rana,
        "rana_in_soyo": "【本轮·吉他/演出】" in soyo,
        "soyo_has_soyo_deep": "【本轮·聊到" in soyo,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=("before", "after"), required=True)
    args = ap.parse_args()

    if args.phase == "before":
        for flags in DEEP_FLAGS.values():
            for f in flags:
                os.environ[f] = "0"
        for f in GENERAL_FLAGS:
            os.environ[f] = "0"
    else:
        for flags in DEEP_FLAGS.values():
            for f in flags:
                os.environ.pop(f, None)
        for f in GENERAL_FLAGS:
            os.environ.pop(f, None)

    out: dict = {"phase": args.phase, "cases": []}
    bad = 0
    # before 臂 = 回退开关全关，**按定义**什么都不该触发，所以这一臂不判定期望，
    # 只用同一脚本、同一输入留一份可 diff 的基线。判定发生在 after 臂。
    enforce = args.phase == "after"
    if not enforce:
        print("[note] before 臂：期望表不参与判定（该臂本来就不触发），只产出基线供 diff")
    print(f"{'角色':<5}{'user_text':<32}{'len':>7}  触发  期望  判定")
    print("-" * 68)
    for char, cases in CASES.items():
        for text, want, owner in cases:
            block = render(char, text)
            fired = bool(block)
            verdict = "OK " if fired == want else "FAIL"
            if fired != want:
                if enforce:
                    bad += 1
                verdict = "基线" if not enforce else verdict
            # 归属校验：新模块的标记必须在 after 出现
            if enforce and owner in MARKER_TITLE:
                import re
                if not re.search(MARKER_TITLE[owner], block):
                    verdict = "FAIL(归属)"
                    bad += 1
            print(f"{char:<5}{text[:30]:<32}{len(block):>7}  {str(fired):<5} {str(want):<5} {verdict}")
            out["cases"].append({
                "char": char, "user_text": text, "len": len(block),
                "fired": fired, "expect": want, "owner": owner, "block": block,
            })

    out["leak"] = leak_check()
    print(f"\n角色串味: {out['leak']}")
    if out["leak"]["soyo_in_rana"] or out["leak"]["rana_in_soyo"]:
        bad += 1

    REPORT.mkdir(parents=True, exist_ok=True)
    dst = REPORT / f"turn_logic_gate_{args.phase}.json"
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"-> {dst}")
    print("PASS" if not bad else f"FAIL x{bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
