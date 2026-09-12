"""每个角色的**可检验台词基线** + 写前自查块。

这份数据的来路：从原作台词库按角色统计中位 / p90 字数、句数、小句数、
标点出现率与自称率。它替换的是「1-10 字为主」「少用感叹号」这类模糊表述——
模糊表述在新模型上只是倾向，给数字才是约束。

与「反助手腔」类约束的分工：

  · 本块管**写多少、什么形状**（长度 / 句数 / 句末 / 自称）；
  · 反助手腔类约束管**不写什么**（关系承诺 / 元叙述 / 心理归因 / 工整收束）。

`scene` 参数的作用：命中场景时，用**该角色在该场景**的原作分布替换长度与句数两项，
其余维度仍用全局值。同一个全局上限不可能对所有场景都对——原作里同角色不同场景的
中位差 1.6~2.6 倍。场景 key 由 `idiolect.scene_classifier.classify` 判定；判不出就传 ""。

原实现位置：mygo_chat 的 `turn_agents/prompt_cards.py`（`STYLE_TARGETS` +
`_build_style_target_block`）。这里摘出来作为独立模块，函数改名为公开的
`build_style_target_block`。
"""
from __future__ import annotations

# 角色 → 全局基线（与场景无关的那部分）
STYLE_TARGETS: dict[str, dict] = {
    "爱音": {
        "median_chars": 20, "p90_chars": 34, "sent_per_turn": 1.59, "clause_per_turn": 1.71,
        "ellipsis_rate": 0.41, "exclaim_rate": 0.36, "question_rate": 0.39,
        "period_rate": 0.14, "comma_rate": 0.51, "first_person_rate": 0.34,
        "top_interjections": ["啊", "诶", "哦", "嘛", "嗯"],
    },
    "灯": {
        "median_chars": 11, "p90_chars": 24, "sent_per_turn": 1.21, "clause_per_turn": 1.42,
        "ellipsis_rate": 0.82, "exclaim_rate": 0.19, "question_rate": 0.18,
        "period_rate": 0.09, "comma_rate": 0.28, "first_person_rate": 0.27,
        "top_interjections": ["啊", "嗯", "诶", "呃", "唔"],
    },
    "乐奈": {
        "median_chars": 6, "p90_chars": 13, "sent_per_turn": 1.19, "clause_per_turn": 1.21,
        "ellipsis_rate": 0.18, "exclaim_rate": 0.02, "question_rate": 0.16,
        "period_rate": 0.16, "comma_rate": 0.14, "first_person_rate": 0.17,
        "top_interjections": ["嗯", "啊", "唔", "哦"],
    },
    "素世": {
        "median_chars": 16, "p90_chars": 30, "sent_per_turn": 1.38, "clause_per_turn": 1.60,
        "ellipsis_rate": 0.43, "exclaim_rate": 0.06, "question_rate": 0.31,
        "period_rate": 0.22, "comma_rate": 0.47, "first_person_rate": 0.34,
        "top_interjections": ["啊", "哦", "嗯", "诶", "唔"],
    },
    "立希": {
        "median_chars": 15, "p90_chars": 29, "sent_per_turn": 1.39, "clause_per_turn": 1.56,
        "ellipsis_rate": 0.59, "exclaim_rate": 0.13, "question_rate": 0.24,
        "period_rate": 0.23, "comma_rate": 0.41, "first_person_rate": 0.35,
        "top_interjections": ["啊", "诶", "唉", "嗯", "哦"],
    },
}


def build_style_target_block(char: str, scene: str = "") -> str:
    """按角色实测基线渲染「可检验」的语气目标 + 写前自查。无该角色基线时返回 ""。"""
    t = STYLE_TARGETS.get(char)
    if not t:
        return ""
    scene_cn = ""
    st = None
    if scene:
        try:
            from idiolect.scene_length_targets import get_scene_target
            st = get_scene_target(char, scene)
        except Exception:  # noqa: BLE001 - 数据模块缺失时退回全局，不影响主流程
            st = None
    if st:
        median_chars, p90_chars = float(st["median"]), float(st["p90"])
        sent_per_turn = float(st["sent"])
        scene_cn = str(st.get("cn") or scene)
    else:
        median_chars = float(t["median_chars"])
        p90_chars = float(t["p90_chars"])
        sent_per_turn = float(t["sent_per_turn"])
    cap = int(p90_chars) + 4
    sent_cap = max(1, int(round(sent_per_turn + 0.6)))
    interjections = "、".join(str(x) for x in t.get("top_interjections", [])[:5])
    head = f"【说话尺度·{char}】" if not scene_cn else f"【说话尺度·{char}·{scene_cn}】"
    lines = [
        f"{head}（来自官方台词库，是**硬指标**、不是倾向）",
        f"- 长度：多数 **{median_chars:.0f} 字**左右，超过 **{p90_chars:.0f} 字**就算异常长。",
        f"- 句数：平均 **{sent_per_turn:.2f} 句** / {t['clause_per_turn']:.2f} 个小句。"
        + ("你绝大多数时候**只说一句**。" if sent_per_turn < 1.3 else ""),
        f"- 句末：{t['ellipsis_rate'] * 100:.0f}% 的话里有省略号（……），"
        f"{t['exclaim_rate'] * 100:.0f}% 有感叹号，{t['question_rate'] * 100:.0f}% 有问号，"
        f"只有 {t['period_rate'] * 100:.0f}% 用句号收尾。"
        + ("**不要给每句话都加句号**。" if t["period_rate"] < 0.3 else ""),
        f"- 自称：只有 **{t['first_person_rate'] * 100:.0f}%** 的话里出现「我」"
        f"——**大多数话不以「我」开头**。",
    ]
    if scene_cn:
        lines.insert(1, f"- 这一轮是「{scene_cn}」：这类场景里你的话**本来就比平时"
                        f"{'短' if st and median_chars < float(t['median_chars']) else '长'}**，"
                        f"按上面的数字来、不要套用别的场景的节奏。")
    if interjections:
        lines.append(f"- 常用语气词：{interjections}。")
    lines += [
        "",
        f"【写之前的硬检查·{char}】写完先自查，任何一项不过就改短：",
        f"1. 总字数 ≤ **{cap}**。超了就删，不是改写。",
        f"2. 句子 ≤ **{sent_cap}** 句（你平均只有 {sent_per_turn:.2f} 句）。",
        "3. **不要替对方把话补完整**：不写「你是想说……」「其实你是……」"
        "「你不需要一个人……」这类替对方定性或安慰的收束句。",
        "4. **不要总结**：不写「总之」「不管怎样」「无论如何」，不在结尾补一句意义升华。",
        "5. 句号只在语气真的落下时用；一句话本来可以停在省略号或半句上，**就停在那里**。",
    ]
    return "\n".join(lines)


def persona_card_prefix(char: str, user_text: str = "") -> str:
    """便捷入口：自己判场景 → 渲染基线块。角色未知时返回 ""。

    场景判定走 `idiolect.scene_classifier`；这里刻意**不**吞异常，
    因为调用方需要知道分类器是否可用（缺数据时 `build_style_target_block` 会退回全局）。
    """
    from idiolect.scene_classifier import classify

    scene = classify(user_text, char) if user_text else ""
    return build_style_target_block(char, scene)


__all__ = ["STYLE_TARGETS", "build_style_target_block", "persona_card_prefix"]
