"""Prompt 补丁实验框架：在**不改生产代码**的前提下测试候选 prompt 改动。

做法：拿真实 messages dump，只在 system prompt 的指定锚点插入/替换片段，
其余部分逐字节不变。这样 before/after 的差异只可能来自被测片段。

已实现的补丁：
  targets   —— 把金标准数值目标（中位/p90/出现率）写进 persona card 末尾，
               替代「1-10 字为主」这类模糊表述。可检验、可复现。
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
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
TARGETS_PATH = DATA / "style_targets.json"

# char_key（罗马字）→ 场景表使用的中文名。场景表键是「素世」，而
# `data/style_targets.json` 的 name 字段是「爽世」，两者不能混用。
SCENE_CHAR_NAME = {"anon": "爱音", "tomori": "灯", "taki": "立希", "soyo": "素世", "rana": "乐奈"}


def load_targets(lang: str = "cn") -> dict:
    return json.loads(TARGETS_PATH.read_text(encoding="utf-8"))[lang]


# persona card 结束 = style_target 层开始：发布版四层装配里 canon + voice 之后
# 的第一个块头就是【说话尺度·…】。锚真实层边界，不锚可能被别的句子复用的短语。
PERSONA_END_MARK = "【说话尺度·"


def find_persona_end(system: str) -> int:
    """返回 persona card 结束位置（= style_target 层【说话尺度·】块的行首）。

    2026-09-13 评审 C1：旧锚点串「【所有角色共用·反客服腔硬约束】」在发布版
    prompt 里只出现在一句交叉引用内部，find 返回的是句子中间的偏移，A/B 补丁
    会把句子腰斩。改成锚真实层边界后，找不到就报错退出——静默退化成「追加到
    system 末尾」会把被测块甩出 persona card，两臂差异就不再只是被测块。
    """
    if system.startswith(PERSONA_END_MARK):
        return 0
    i = system.find("\n" + PERSONA_END_MARK)
    if i >= 0:
        return i + 1
    raise SystemExit(
        "find_persona_end：system 里没有 style_target 层边界（行首的【说话尺度·…】）。"
        "发布版四层装配必有这一层；外部 dump 请先确认布局，补丁落点不许靠猜。")


def build_targets_block(char_cn: str, t: dict) -> str:
    """生成「数值目标」块。措辞刻意用可检验的硬数字，不用倾向词。

    ⚠ 这是**实验臂**，不是生产块：它把数字块追加到 persona card 末尾，用来测量
    「只给数字」能带来多少提升（历史各臂的对照基线）。生产块见
    `idiolect/style_target.py`，措辞已经去过术语（「实测台词基线/中位/p90」→
    「说话尺度/多数/超过…就算异常长」），因为元叙述门禁把「实测」「基线」「中位」
    定为角色不可见词。**两边故意不同步**：改了这里，历史臂之间就不可比了。
    """
    parts = [
        f"【实测台词基线·{char_cn}】（来自官方台词库，共 {t['n']} 句。这是**硬指标**，不是倾向）",
        f"- 长度：中位 **{t['median_chars']:.0f} 字**，p90 **{t['p90_chars']:.0f} 字**。"
        f"**超过 p90 就是异常长**，属于出戏。",
        f"- 句数：平均 **{t['sent_per_turn']:.2f} 句**、{t['clause_per_turn']:.2f} 个小句。"
        + ("你绝大多数时候**只说一句**。" if t["sent_per_turn"] < 1.3 else ""),
        f"- 句末："
        f"{t['ellipsis_rate'] * 100:.0f}% 的话里有省略号（……），"
        f"{t['exclaim_rate'] * 100:.0f}% 有感叹号，"
        f"{t['question_rate'] * 100:.0f}% 有问号，"
        f"只有 {t['period_rate'] * 100:.0f}% 用句号收尾。"
        + ("**不要给每句话都加句号**。" if t["period_rate"] < 0.3 else ""),
        f"- 自称：只有 **{t['first_person_rate'] * 100:.0f}%** 的话里出现「我」。"
        f"**大多数话不以「我」开头**，不要每句都写「我……」。",
        f"- 逗号：{t['comma_rate'] * 100:.0f}% 的话里有逗号；不需要把每个小句都用逗号串起来。",
    ]
    if t.get("top_interjections"):
        parts.append(f"- 常用语气词：{'、'.join(t['top_interjections'][:5])}。")
    return "\n".join(parts)


def build_scene_block(char_cn: str, st: dict) -> str:
    """按「本轮场景」渲染数值目标块（只替换长度/句数两行，其余仍用全局值）。

    实测踩过的坑：初版只插 scene block、把 `build_hardcap_block` 一起丢了，
    于是两臂差异不止「场景 vs 全局」一个变量，d_scene 的素世|fact_qa 长度中位
    54 vs d_global 24（原作 10）看起来像回归，实际是被测臂少了整段硬上限清单。
    调用方必须把硬上限块一起拼上。

    措辞受元叙述门禁约束：不出现「基线 / 实测 / 中位 / p90」这类词。
    """
    return (
        f"【这一轮的说话尺度·{char_cn}·{st.get('cn') or ''}】"
        f"（来自官方台词库，是**硬指标**、不是倾向）\n"
        f"- 长度：多数 **{float(st['median']):.0f} 字**左右，"
        f"超过 **{float(st['p90']):.0f} 字**就算异常长。\n"
        f"- 句数：平均 **{float(st['sent']):.2f} 句**（本场景的样本 n = {int(st.get('n') or 0)}）。\n"
        f"- 这一轮按上面的数字来，不要套用别的场景的节奏。"
    )


def build_hardcap_block(char_cn: str, t: dict) -> str:
    """第二轮：在数值目标之后再加**可判定的硬上限与检查清单**。

    动机：第一轮 targets 补丁把素世 +11.8、乐奈 +7.7，但爱音/灯几乎没动——
    因为纯描述性数字容易被当成参考。这里改成「写之前先检查」的可判定规则，
    并给出两条最容易踩的红线（把话补完整、把一件事说成三句）。
    """
    p90 = max(int(t["p90_chars"]), 8)
    cap = p90 + 4
    sent_cap = max(1, int(round(t["sent_per_turn"] + 0.6)))
    return (
        f"【写之前的硬检查·{char_cn}】\n"
        f"写完先自查，任何一项不过就改短：\n"
        f"1. 总字数 ≤ **{cap}**（你实测 p90 = {t['p90_chars']:.0f} 字）。超了就删，不是改写。\n"
        f"2. 句子 ≤ **{sent_cap}** 句。{char_cn}平均只有 {t['sent_per_turn']:.2f} 句。\n"
        f"3. **不要替对方把话补完整**：不许写「你是想说……」「其实你是……」"
        f"「你不需要一个人……」这类替对方定性或安慰的收束句。\n"
        f"4. **不要总结**：不写「总之」「不管怎样」「无论如何」；不要在结尾补一句意义升华。\n"
        f"5. 句号只在语气真的落下时用。若一句话本来可以停在省略号或半句上，**就停在那里**。"
    )


def build_anchor_block(char_cn: str, t: dict) -> str:
    """第三轮：专治「情感轮变空」。

    实测证据：v43 补丁把长度压到金标准区间了，但在情感型情景上锚点密度塌到 0.10~0.41
    （示爱/亲密 0.10、情绪崩溃 0.41），而信息型情景有 5~13。即回复是靠「只说态度、
    不说具体事」变短的。裁判在「自伤/消失话题」给全场最低分（71.7，grounding 2.67）。

    所以这一块不压长度，而是要求**把情绪落到一个眼前的具体东西上**。
    """
    return (
        f"【情感场景·必须落地】\n"
        f"当对方在说难受、害怕、想你、或者担心失去你时——**不要用一句态度或承诺收尾**。\n"
        f"你要做的是：从你此刻的处境里挑**一个具体的、能指认的东西**接住对方。\n"
        f"可用素材：现在几点、在哪个房间、手上在做什么、窗外天气、桌上有什么、"
        f"手机/笔记本/乐器/食物/猫的当下状态。\n"
        f"✓ 例：「（具体物/动作）+ 我自己的反应」，两句以内。\n"
        f"✗ 反例：只写「我听着」「我在」「我知道」「你别多想」——这些没有落地，等于没说。\n"
        f"注意：落地**不等于**变长。一个具体名词加一个短反应就够，"
        f"长度仍守上面的基线（{char_cn} p90 = {t['p90_chars']:.0f} 字）。"
    )


RANA_REGISTER_BLOCK = "【句式结构·这是你最大的辨识点】"


def _rana_block_end(text: str, start: int) -> int:
    """乐奈句式块的结束边界：下一个行首【标题 或 （跨角色… 说明段，取先到者。

    2026-09-13 修：manifest 在句式块之后新增了【常用物件与话题】等节，
    只认「（跨角色」说明段会把后面三节一并剥掉——取两个候选里更早的那个。
    """
    cands = [
        x for x in (
            text.find("\n【", start + len(RANA_REGISTER_BLOCK)),
            text.find("\n（跨角色", start),
        ) if x >= 0
    ]
    return min(cands) if cands else -1


def strip_rana_register(system: str) -> str:
    """从夹具里**移除**已落盘的乐奈句式块，构造干净的 before 臂。

    用途：manifest 一旦改到工作树，夹具就含了新块，无法再取到 before 状态。
    这里按块边界精确剔除（从块标题到下一个空行后的标题），其余部分逐字节不动。
    必须先验证剔除后的文本确实不含该块，否则宁可报错也不要产出脏臂。
    """
    start = system.find(RANA_REGISTER_BLOCK)
    if start < 0:
        raise SystemExit("夹具里没有乐奈句式块——before 臂无法构造")
    nxt = _rana_block_end(system, start)
    if nxt < 0:
        raise SystemExit("找不到乐奈句式块的结束边界")
    out = system[:start] + system[nxt + 1:]
    if RANA_REGISTER_BLOCK in out:
        raise SystemExit("剔除后仍含该块，拒绝产出脏臂")
    return out


# ── 场景模块候选（供 turn_logic 迭代用） ──────────────────────────
# 每个候选对应 scenes.py 里的一个场景 key；正文由语料统计 + canon 手工撰写。
SCENE_MODULE_CANDIDATES: dict[str, dict[str, str]] = {
    "rana_guitar": {
        "watch": "anchors",
        "block": (
            "【本轮·吉他/演出】\n"
            "- 先给最短的处置或判断（换弦、松了、调音、带去），再考虑要不要解释。\n"
            "- 可用细节：弦、拨片、琴盒、指板、音色闷/亮、排练时间、RiNG。\n"
            "- 不要教学：不说「先这样再那样」的步骤说明，除非对方明确问怎么弄。"
        ),
    },
    "rana_food": {
        "watch": "anchors",
        "block": (
            "【本轮·抹茶/食物】\n"
            "- 这是少数可以有温度的话题：可以主动提出要或不要。\n"
            "- 可用细节：抹茶芭菲、抹茶冰淇淋、荞麦面、点心、放学后的路线。\n"
            "- 仍然短：一到两句，不描述口感层次。"
        ),
    },
    "rana_cat": {
        "watch": "anchors",
        "block": (
            "【本轮·猫/观察】\n"
            "- 丢一个具体观察就够：猫的位置、动作、天气的当下状态。\n"
            "- 不问对方感受、不做引申。观察本身即是回答。\n"
            "- 可用细节：屋檐、院子、水池、湿掉的毛、她外婆家。"
        ),
    },
}


def build_scene_module_blocks(scene_keys: list[str]) -> str:
    blocks = [SCENE_MODULE_CANDIDATES[k]["block"] for k in scene_keys if k in SCENE_MODULE_CANDIDATES]
    return "\n\n".join(blocks)


def _persona_card_from_code(char_key: str, *, drop_rana_register: bool) -> str:
    """用**当前代码**重建 persona card（= canon + voice 两层全文），可选择性剔除乐奈句式块。

    为什么需要：夹具是历史 dump（往往是打补丁之前），里面嵌的是旧的 manifest / persona card。
    探针若直接用夹具，就测不到 manifest 层的改动。这里现读 registry 的 canon / voice，
    保证测的是当前代码；A/B 两臂都走它，唯一差别就是要测的那个块。

    2026-09-13 修：旧实现 import 的 `idiolect.style_target._get_persona_card` 在发布版
    仓库里不存在（那是私有完整系统的入口），live_persona 系补丁一跑就 ImportError。
    发布版的 persona card 就是 canon + voice，从 `idiolect.registry` 取。
    """
    names = {"anon": "爱音", "soyo": "素世", "tomori": "灯", "taki": "立希", "rana": "乐奈"}
    from idiolect.registry import get_canon_profile, get_voice_manifest

    name = names[char_key]
    canon = (get_canon_profile(name) or "").strip()
    voice = (get_voice_manifest(name) or "").strip()
    card = "\n\n".join(x for x in (canon, voice) if x)
    if not card:
        raise SystemExit(f"无法从代码取到 {name} 的 persona card（canon/voice 均为空）")
    if drop_rana_register:
        start = card.find(RANA_REGISTER_BLOCK)
        if start >= 0:
            nxt = _rana_block_end(card, start)
            card = card[:start] + card[nxt + 1:] if nxt >= 0 else card
            if RANA_REGISTER_BLOCK in card:
                raise SystemExit("剔除乐奈句式块失败")
    return card


def swap_in_live_persona_card(system: str, char_key: str, *, drop_rana_register: bool) -> str:
    """把夹具里的旧 persona card 替换成当前代码构建的版本。

    定位（发布版四层装配）：persona card = 从 system 开头到 style_target 层
    （【说话尺度·】块）之间的全部内容，即 canon + voice。私有完整系统的历史
    dump 带【输出格式·所有角色共用】标记的，仍按旧两标记定位。
    """
    new_card = _persona_card_from_code(char_key, drop_rana_register=drop_rana_register)
    start = system.find("【输出格式·所有角色共用】")
    if start >= 0:
        # 私有完整系统 dump：card 从【输出格式·所有角色共用】到反客服腔块结束
        end = system.find("【所有角色共用·反客服腔硬约束】", start)
        if end < 0:
            raise SystemExit("夹具里找不到 persona card 终点")
        # 反客服腔块本身属于 persona card，需一并替换：找到它的结束（下一个二级标题或串尾）
        tail = system.find("\n【", end + len("【所有角色共用·反客服腔硬约束】"))
        end_full = tail if tail > 0 else len(system)
        return system[:start] + new_card + system[end_full:]
    # 发布版四层：canon 是第 0 层，card 一直延伸到 style_target 层开始；
    # 层间的空行分隔符属于装配器，不在 card 里，替换时要补回来
    end = find_persona_end(system)
    return new_card + "\n\n" + system[end:]


def apply_patch(system: str, char_key: str, patch: str, targets: dict,
                *, scene: str = "", scene_cn: str = "") -> str:
    """把补丁应用到 system prompt（char_key 为 tomori/anon/rana/soyo/taki）。

    scene / scene_cn：仅 `targets_scene` 用——按「本轮场景」注入该场景的原作基线。
    """
    if patch == "none":
        return system
    if patch == "live_persona":
        # 当前代码的 persona card（含乐奈句式块）
        return swap_in_live_persona_card(system, char_key, drop_rana_register=False)
    if patch == "live_persona_no_rana_reg":
        # 同上但剔除乐奈句式块 → 与 live_persona 构成只差一个块的对照
        return swap_in_live_persona_card(system, char_key, drop_rana_register=True)
    if patch == "strip_rana_register":
        return strip_rana_register(system)
    if patch == "targets_scene":
        # 按场景条件化的长度/句数目标 —— **只替代全局 STYLE_TARGETS 的长度部分**。
        # ⚠️ 2026-09-12 踩过：初版只插 scene block、把 targets_cap 臂的
        # `build_hardcap_block` 一起丢了，于是两臂差异不止「场景 vs 全局」一个变量，
        # d_scene 的素世|fact_qa 长度中位 54 vs d_global 24（原作 10）看起来像回归，
        # 实际是被测臂少了整段硬上限清单。修正：硬上限必须保留。
        t = targets.get(char_key)
        if not t:
            return system
        # 场景表用中文角色名索引；t["name"] 是导出脚本里的显示名（soyo → 爽世），
        # 与场景表的键（素世）不一致，所以这里按 char_key 映射。
        name = SCENE_CHAR_NAME.get(char_key, t.get("name", char_key))
        # 数据来自随仓库发布的 `idiolect/scene_length_targets.py`（130 个 角色 × 场景 目标，
        # 由 tools/distill/export_scene_targets.py 生成）。
        # 2026-09-13 修：这条臂的 import 曾指向一个不存在的 `scene_targets` 模块、
        # 必然 ImportError —— 此前是死的。
        from idiolect.scene_length_targets import get_scene_target
        st = get_scene_target(name, scene)
        if not st:
            # 不再静默返回原 prompt：那等于把处理臂悄悄变成对照组。
            raise SystemExit(
                f"targets_scene: 角色 {name!r} 场景 {scene!r} 没有场景目标"
                f"（导出时样本 < 20 的组合会被丢弃）——要么换场景，要么先补基线。")
        block = build_scene_block(name, st) + "\n\n" + build_hardcap_block(t.get("name", name), t)
        i = find_persona_end(system)
        return system[:i].rstrip() + "\n\n" + block + "\n\n" + system[i:]
    if patch == "scenes_v3":
        # 场景模块候选版：数值目标 + 硬上限 + 按场景注入模块，故意**不含**句式块，
        # 用来检验「场景模块能否替代全局语域约束」
        t = targets.get(char_key)
        if not t:
            return system
        name = t.get("name", char_key)
        block = (build_targets_block(name, t) + "\n\n" + build_hardcap_block(name, t)
                 + "\n\n" + build_scene_module_blocks(list(SCENE_MODULE_CANDIDATES)))
        i = find_persona_end(system)
        return system[:i].rstrip() + "\n\n" + block + "\n\n" + system[i:]
    t = targets.get(char_key)
    if not t:
        return system
    name = t.get("name", char_key)
    if patch == "targets":
        block = build_targets_block(name, t)
    elif patch == "targets_cap":
        block = build_targets_block(name, t) + "\n\n" + build_hardcap_block(name, t)
    elif patch == "targets_cap_anchor":
        block = (build_targets_block(name, t) + "\n\n" + build_hardcap_block(name, t)
                 + "\n\n" + build_anchor_block(name, t))
    else:
        raise SystemExit(f"unknown patch: {patch}")
    i = find_persona_end(system)
    # 插在 style_target 层之前（canon + voice 的末尾 = persona card 结束），
    # 与生产装配的层序一致；找不到层边界时 find_persona_end 会直接报错
    return system[:i].rstrip() + "\n\n" + block + "\n\n" + system[i:]


def describe(patch: str) -> str:
    return {
        "none": "生产现状 prompt（无改动）",
        "targets": "在 persona card 末尾插入「实测台词基线」数值目标块",
        "targets_cap": "数值目标块 + 可判定的硬上限检查清单（含「不许替对方补完/不许总结」）",
        "targets_cap_anchor": "数值目标 + 硬上限 + 情感场景强制落地（专治情感轮锚点塌陷）",
        "strip_rana_register": "从夹具中剔除乐奈句式块（构造干净的 before 臂）",
        "targets_scene": "按**本轮场景**注入该角色该场景的原作长度/句数基线（替代全局 targets）",
        "live_persona": "用当前代码重建 persona card（含乐奈句式块）",
        "live_persona_no_rana_reg": "同上但剔除乐奈句式块（与 live_persona 只差一个块）",
        "scenes_v3": "数值目标 + 硬上限 + 按场景注入模块（不含全局句式约束）",
    }.get(patch, patch)
