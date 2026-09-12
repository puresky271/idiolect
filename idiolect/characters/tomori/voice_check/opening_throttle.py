"""灯专属：起手式去重轮换（generalized throttle + rotate、2026-05-11 拍板更新）。

用户拍板 2026-05-10：
  灯的起手式 LLM 遵守度低、需要做去重。可选起手式：
    1. 嗯
    2. 啊
    3. 唔
    4. ······   （纯 6 中点）
    5. ······！ （6 中点 + 感叹）
    6. ······？ （6 中点 + 疑问）

用户拍板 2026-05-11（行为修正）：
  之前的"压制 = 直接剥头"过于粗暴——LLM **确实**用了起手式说明它觉得需要起手停顿、
  剥掉等于在不该剥的地方剥。改成：**replace（轮换）** = 把重复起手式换成 6 种里
  当下窗口里**最少被用过**的那一个。替换后的那个也算入去重计数（自然进入 history、
  下次 detect 拿到的就是替换值）。

  · 替换 = 剥旧 prefix + 加新 canonical prefix
  · 排除当前 kind 本身（不会替换成自己）
  · 优先选 prior 计数为 0 的 kind；多个并列时按灯-canonical 优先级（······ > 嗯 > 唔 > 啊 > ······？ > ······！）
  · 极端兜底：6 种都饱和（前 3 条用了 3 种不同 ≥ 2 次）→ 退回原 strip 行为

  约束：以省略号起手时、紧跟的字符不能再是省略号
        （e.g.「············啊那个」要塌成「······啊那个」）。

设计：
  · 窗口：最近 4 条 assistant 回复（含本条之前的 3 条）
  · 同类计数阈值：前 3 条里 ≥ 2 条用同种起手式 → 替换本条
  · 6 种起手式独立计数（嗯×2 不会让 ······ 也被替、各管各的）
  · `······！` / `······？` 视为独立类（语义负载和纯 `······` 不同）

历史：
  · 初版只覆盖「嗯」一种
  · 2026-05-10 扩展到 6 种、但用 strip 策略
  · 2026-05-11 改 strip → rotate replacement
"""
from __future__ import annotations

import re
from typing import Optional


# ─── 6 种起手式正则 ─────────────────────────────────────────────
# 每条匹配: 起首 hum / 中点 + 后续可选标点 / 空白
# 命名：用作字典 key（追踪哪种起手式被用过）
OPENING_KIND_HUM_N    = "hum_嗯"
OPENING_KIND_HUM_A    = "hum_啊"
OPENING_KIND_HUM_U    = "hum_唔"
OPENING_KIND_PAUSE    = "pause_neutral"   # ······
OPENING_KIND_PAUSE_Q  = "pause_question"  # ······？
OPENING_KIND_PAUSE_X  = "pause_exclaim"   # ······！

# 用户拍板 2026-05-10：嗯/啊/唔 后面**常**加 ······ 但**不强求**、所以只检测字本身。
# 字符可重复（嗯嗯嗯对 / 啊啊那个）；后面有没有 ······ / ，/ 标点都行。
# strip 时把字 + 可选尾部（标点 / 省略号 / 空白）一并剥掉。
_OPENING_TAIL = r"(?:[，,、…]+|·{3,}|\.{2,6}|\s+)*"

_OPENING_PATTERNS: list[tuple[str, re.Pattern]] = [
    # 顺序：长 / 特异 → 短 / 通用，确保 `······？` 不被 `······` 抢
    (OPENING_KIND_PAUSE_Q,  re.compile(r"^\s*·{3,}\s*[？?]\s*", re.UNICODE)),
    (OPENING_KIND_PAUSE_X,  re.compile(r"^\s*·{3,}\s*[！!]\s*", re.UNICODE)),
    (OPENING_KIND_PAUSE,    re.compile(r"^\s*·{3,}(?![？?！!])\s*", re.UNICODE)),
    # 嗯/啊/唔：只检字、尾部可选（贪婪吃同字重复 + 可选尾部）
    (OPENING_KIND_HUM_N,    re.compile(r"^\s*嗯+" + _OPENING_TAIL, re.UNICODE)),
    (OPENING_KIND_HUM_A,    re.compile(r"^\s*啊+" + _OPENING_TAIL, re.UNICODE)),
    (OPENING_KIND_HUM_U,    re.compile(r"^\s*唔+" + _OPENING_TAIL, re.UNICODE)),
]


def detect_opening(reply: str) -> Optional[str]:
    """返回起手式 kind（如 OPENING_KIND_HUM_N）；无起手式返 None。"""
    if not reply:
        return None
    for kind, pat in _OPENING_PATTERNS:
        if pat.match(reply):
            return kind
    return None


def _strip_opening(reply: str, kind: str) -> str:
    """剥掉指定 kind 的起手式（含尾随标点 / 空白）。"""
    for k, pat in _OPENING_PATTERNS:
        if k == kind:
            return pat.sub("", reply, count=1).lstrip()
    return reply


# ─── 连续 `······` 冲突修复 ─────────────────────────────────────
# 用户硬约束：以 `······` 起手时，紧跟的不能再是 `······`。
# 命中场景：「······」+「······啊那个」拼接 / LLM 直接吐出 12+ 中点连串。
# 注：normalize_ellipsis 已经会把 12+ 中点折回 6、但执行时机和这里隔阶段、
#     这里再做一次保险（按字面计数）。
# canonical 起手 = 恰好 6 中点。≥ 7 中点意味着 LLM 输出了 ······ 后又紧跟一段中点、
# 折回 6 即可（塌成单组 canonical 起手）。
_LEADING_RUN_ON_DOTS_RE = re.compile(r"^·{7,}", re.UNICODE)


def _fix_leading_double_ellipsis(reply: str) -> tuple[str, bool]:
    """如果起手 `······` 后紧跟另一组 `······`（≥ 7 中点连串）、塌成 6 中点。"""
    if not reply:
        return reply, False
    m = _LEADING_RUN_ON_DOTS_RE.match(reply)
    if not m:
        return reply, False
    rest = reply[m.end():]
    new_text = "······" + rest
    return new_text, True


# ─── 复合起手式拆分（2026-05-17） ──────────────────────────────
# 用户拍板：LLM 输出复合起手式（PAUSE + HUM + 句末标点）时、
#         把 prefix 段拆成独立气泡（如 `······嗯。`）、剩余内容是第 2 气泡。
# 例:
#   "······嗯。······它今天又乱跑了吗。" → ("······嗯。", "······它今天又乱跑了吗。")
#   "······啊。这样啊"                  → ("······啊。", "这样啊")
#   "······啊那个事情"                  → (None, ...)  # HUM 后无句末标点、不拆
#   "嗯，那个"                          → (None, ...)  # 非 PAUSE 起手
#
# 判定条件（三个都满足）：
#   1. 以 PAUSE (······) 起手
#   2. PAUSE 段后紧跟 HUM (嗯/啊/唔)
#   3. HUM 段后紧跟句末标点（。.！!？?）— 无标点视作单意图、不拆

# HUM 紧凑模式：仅匹配 hum char + 重复（不含 tail 标点）、便于精确切割
_COMPOUND_HUM_PAT = re.compile(r"^(嗯+|啊+|唔+)", re.UNICODE)
# 复合起手式后段必须的句末标点（不含逗号、避免 "嗯，今天" 这种单意图被误拆）
_COMPOUND_SENTENCE_END_PAT = re.compile(r"^[。.！!？?]", re.UNICODE)


def extract_compound_opening(reply: str) -> tuple[Optional[str], str]:
    """检测并拆分"复合起手式"（PAUSE + HUM + 句末标点）。

    返回 (compound_prefix, remaining)：
      · compound_prefix: 拆出来的 prefix 段（如 "······嗯。"），不是复合时为 None
      · remaining: 剩余文本（不是复合时返回原 reply）

    与 throttle_opening 的协作：
      · 必须在 throttle 之前调用、拿到 compound_prefix 后只把 remaining 传给 throttle
      · 复合 prefix 最终由调用方作为独立气泡 prepend 到回复分泡
    """
    text = str(reply or "")
    if not text or not text.strip():
        return None, text

    # Step 1: 检测 PAUSE 起手
    pause_pat = None
    for k, p in _OPENING_PATTERNS:
        if k == OPENING_KIND_PAUSE:
            pause_pat = p
            break
    if pause_pat is None:
        return None, text
    m_pause = pause_pat.match(text)
    if not m_pause:
        return None, text  # 非 PAUSE 起手、不是复合
    pause_text = m_pause.group(0).rstrip()  # 去尾空白、保留中点本身

    # Step 2: PAUSE 段后必须紧跟 HUM 字
    after_pause = text[m_pause.end():]
    m_hum = _COMPOUND_HUM_PAT.match(after_pause)
    if not m_hum:
        return None, text  # 不是复合
    hum_text = m_hum.group(0)  # 纯 hum 字本体（如 "嗯" / "嗯嗯"）

    # Step 3: HUM 段后必须紧跟句末标点（。.！!？?）
    after_hum = after_pause[m_hum.end():]
    m_end = _COMPOUND_SENTENCE_END_PAT.match(after_hum)
    if not m_end:
        return None, text  # HUM 后无句末标点、单意图、不拆
    sentence_end = m_end.group(0)
    remaining = after_hum[m_end.end():].lstrip()

    compound_prefix = pause_text + hum_text + sentence_end
    return compound_prefix, remaining


# ─── 6 种 opening 的 canonical 替换 prefix（rotate 时用） ──────
# 不一定和 LLM 原输出格式完全一样、但是 canon 灯 的标准起手 token。
_OPENING_PREFIX: dict[str, str] = {
    OPENING_KIND_HUM_N:    "嗯，",
    OPENING_KIND_HUM_A:    "啊，",
    OPENING_KIND_HUM_U:    "唔，",
    OPENING_KIND_PAUSE:    "······",
    OPENING_KIND_PAUSE_Q:  "······？",
    OPENING_KIND_PAUSE_X:  "······！",
}

# 灯-canonical 优先级（最 canon → 最少用），rotate 时同 count 按此 tie-break。
# ······ 是灯的标志性犹豫感、最 canon；······！最稀有、压在最末。
_OPENING_PRIORITY: list[str] = [
    OPENING_KIND_PAUSE,
    OPENING_KIND_HUM_N,
    OPENING_KIND_HUM_U,
    OPENING_KIND_HUM_A,
    OPENING_KIND_PAUSE_Q,
    OPENING_KIND_PAUSE_X,
]


def _pick_replacement_kind(
    current_kind: str,
    prior_kinds: list,
    threshold: int,
) -> str | None:
    """从 6 种 opening 里挑一个非 current_kind、prior 计数最低的来替换。

    选法：
      1. 排除 current_kind
      2. 按 prior 出现次数升序排（少用的优先）
      3. 同次按 _OPENING_PRIORITY 顺序（最 canon 优先）
      4. 如果 best candidate 的 count < threshold → 返回它（可替换）
      5. 全部 ≥ threshold → 返回 None（回退到 strip）
    """
    counts: dict[str, int] = {k: 0 for k in _OPENING_PRIORITY}
    for k in prior_kinds:
        if k in counts:
            counts[k] += 1
    candidates = [k for k in _OPENING_PRIORITY if k != current_kind]
    candidates.sort(key=lambda k: (counts[k], _OPENING_PRIORITY.index(k)))
    if not candidates:
        return None
    best = candidates[0]
    if counts[best] >= threshold:
        return None  # 都饱和、回退
    return best


# ─── HUM 系组（用户 2026-05-18 拍板：嗯/啊/唔 合并计数节流） ──
# 旧逻辑里 HUM_N (嗯) / HUM_A (啊) / HUM_U (唔) 三种各算一类、threshold=2 时
# 「1 嗯 + 1 啊 + 1 唔」不触发限频、但用户主观感受是「各种 hum 起手太多」。
# 改成：cur ∈ HUM 系组时、prior 里**所有** HUM 系都计入 same_count。
_HUM_GROUP: set[str] = {OPENING_KIND_HUM_N, OPENING_KIND_HUM_U, OPENING_KIND_HUM_A}


# ─── 主入口 ─────────────────────────────────────────────────────
_WINDOW_PRIOR = 4       # 2026-05-18 扩窗口 3 → 4（看更远历史）
_THRESHOLD_SAME = 2     # 前 N 条里 ≥ 2 条同 kind → 替换本条
_THRESHOLD_HUM_GROUP = 1  # 2026-05-18b 收紧 2 → 1（prior 4 条里出现 1 个 HUM 就触发当前限频）
_THRESHOLD_PAUSE_NEUTRAL = 2  # PAUSE_NEUTRAL 单独 threshold（不收紧、因为 strip 退路 PAUSE 不引入新内容）


def throttle_opening(
    reply: str,
    recent_assistant_replies: list[str],
) -> tuple[str, dict]:
    """对灯 reply 起手式做去重轮换 + 连续省略号冲突修复。

    Args:
        reply: 待清洗的 reply 文本
        recent_assistant_replies: 最近 N 条 assistant 回复（**不含当前**）、
                                  时间倒序无所谓、本函数只用 detect_opening 计数。

    Returns:
        (new_reply, info)
        info keys:
          · current_kind: 当前 reply 的起手式（None 表示无）
          · replaced: 是否替换了起手式（rotate）
          · replacement_kind: 替换成的目标 kind（仅在 replaced=True 时有意义）
          · stripped: 是否退回到 strip 模式（罕见、6 种都饱和时）
          · double_ellipsis_fixed: 是否修复了连续省略号
          · prior_kinds: 前 N 条的 kind 列表（debug）

    备注：替换后的 prefix 自然进入下一轮 prior_kinds（detect_opening 看的是
    最终 reply 的 prefix）、所以"替换后的那个也进入去重计算"自动成立。
    """
    info: dict = {
        "current_kind": None,
        "replaced": False,
        "replacement_kind": None,
        "stripped": False,
        "double_ellipsis_fixed": False,
        "prior_kinds": [],
    }
    text = str(reply or "")
    if not text.strip():
        return text, info

    # ─── Step 1: 修复连续 `······` 起手 ───
    text, dd_fixed = _fix_leading_double_ellipsis(text)
    info["double_ellipsis_fixed"] = dd_fixed

    # ─── Step 2: 检测当前起手式 ───
    cur_kind = detect_opening(text)
    info["current_kind"] = cur_kind
    if cur_kind is None:
        return text, info  # 无起手式、不需要 throttle

    # ─── Step 3: 检测前 N 条起手式 ───
    prior_kinds: list = []
    for prior in (recent_assistant_replies or [])[: _WINDOW_PRIOR]:
        prior_kinds.append(detect_opening(prior))
    info["prior_kinds"] = [k or "" for k in prior_kinds]

    # 历史不够、暂不替换（让用户看到几条 canon 风格再开始限频）
    if len([k for k in prior_kinds if k is not None]) < 2 and len(prior_kinds) < _WINDOW_PRIOR:
        return text, info

    # ─── Step 4: 同类计数（2026-05-18：HUM 系组合并计数） ───
    # cur ∈ HUM 系组（嗯/啊/唔）→ same_count 看 prior 里所有 HUM 系总数
    # cur 是 PAUSE 系 → same_count 只看同 kind（PAUSE_NEUTRAL/_Q/_X 各自）
    if cur_kind in _HUM_GROUP:
        same_count = sum(1 for k in prior_kinds if k in _HUM_GROUP)
        threshold = _THRESHOLD_HUM_GROUP
        info["hum_group_count"] = same_count
    else:
        same_count = sum(1 for k in prior_kinds if k == cur_kind)
        threshold = _THRESHOLD_SAME
    if same_count < threshold:
        return text, info  # 未达阈值、原样返回

    # ─── Step 5: 优先尝试 rotate 替换 ───
    body = _strip_opening(text, cur_kind)
    # 防御：剥完后必须有实际内容
    if not (body and re.search(r"[一-鿿\w]", body)):
        return text, info

    # 2026-05-17: cur=PAUSE_NEUTRAL 时不 rotate 到 HUM 系列——
    # 用户反馈："嗯，/······嗯 太多了"。从 PAUSE rotate 到 HUM 会把 LLM 原本无语义的
    # `······` 起手强行换成 `嗯，/啊，/唔，` 带 hum 字内容、推高 hum opening 频率。
    # 2026-08-16: 也不再 strip；`······` 是灯 canon 起手，直接剥掉会丢失前端可见符号。
    # PAUSE_Q / PAUSE_X 带疑问 / 感叹语义、同样不 strip 也不 rotate（保留语义 marker）。
    if cur_kind in (OPENING_KIND_PAUSE, OPENING_KIND_PAUSE_Q, OPENING_KIND_PAUSE_X):
        return text, info

    # 2026-05-18: cur ∈ HUM 系组（嗯/啊/唔）且触发阈值 → 直接 rotate to PAUSE_NEUTRAL
    # 不再调 _pick_replacement_kind（避免选到其他 HUM 系、仍推高 hum 总频率）。
    # body 头部如果已经自带 PAUSE → 退到 strip（不重复加 prefix）。
    if cur_kind in _HUM_GROUP:
        body_head_kind = detect_opening(body)
        if body_head_kind == OPENING_KIND_PAUSE:
            info["stripped"] = True
            info["hum_to_strip_body_has_pause"] = True
            return body, info
        info["replaced"] = True
        info["replacement_kind"] = OPENING_KIND_PAUSE
        new_prefix = _OPENING_PREFIX[OPENING_KIND_PAUSE]  # "······"
        if body and body[0] in "，、,；;：:。.？?！!…·":
            _prefix_no_punct = re.sub(r"[，,。.！!？?…·]+$", "", new_prefix)
            return _prefix_no_punct + body, info
        return new_prefix + body, info

    replacement_kind = _pick_replacement_kind(cur_kind, prior_kinds, _THRESHOLD_SAME)
    if replacement_kind is not None:
        # 2026-05-17: 处理"复合起手式"——LLM 原 reply 可能是 PAUSE + HUM 双重起手
        # （e.g. `······嗯。它今天又乱跑了吗`），strip 掉 cur_kind 后 body 头部仍带另
        # 一种 opening。此时若 replacement_kind 与 body 头部 kind 相同、拼接会
        # 重复（"嗯，嗯。它今天又乱跑了吗"）。
        # 处理：detect body 头部 kind、若与 replacement_kind 相同 → 跳过 rotate、
        # 让 body 自带的 opening 当起手（回退到 strip 模式语义）。
        body_head_kind = detect_opening(body)
        if body_head_kind is not None and body_head_kind == replacement_kind:
            info["stripped"] = True
            info["prior_kinds_redundant"] = True
            return body, info
        new_prefix = _OPENING_PREFIX[replacement_kind]
        # 智能拼接：如果 body 已经以标点 / 省略号开头、新 prefix 不带尾标点更自然
        # （否则会出现"嗯，，那个"双逗号）
        if body and body[0] in "，、,；;：:。.？?！!…·":
            # body 已带标点、用纯字 prefix（剥掉 prefix 的尾标点）
            _prefix_no_punct = re.sub(r"[，,。.！!？?…·]+$", "", new_prefix)
            new_text = _prefix_no_punct + body
        else:
            new_text = new_prefix + body
        info["replaced"] = True
        info["replacement_kind"] = replacement_kind
        return new_text, info

    # ─── Step 6: 6 种都饱和、兜底 strip ───
    info["stripped"] = True
    return body, info


# ─── self-test ────────────────────────────────────────────────
if __name__ == "__main__":
    fail = 0

    # 1) detect_opening
    detect_cases = [
        # 带尾部
        ("嗯，那个", OPENING_KIND_HUM_N),
        ("嗯······那个", OPENING_KIND_HUM_N),
        ("嗯…明白了", OPENING_KIND_HUM_N),
        ("啊，是这样啊", OPENING_KIND_HUM_A),
        ("唔······好像是", OPENING_KIND_HUM_U),
        # **裸字起手**（用户 2026-05-10 拍板：不强求尾部）
        ("嗯然后那个", OPENING_KIND_HUM_N),
        ("啊那个", OPENING_KIND_HUM_A),
        ("唔好像是", OPENING_KIND_HUM_U),
        ("嗯嗯嗯对", OPENING_KIND_HUM_N),    # 重复字
        ("啊啊", OPENING_KIND_HUM_A),         # 仅重复字
        ("嗯", OPENING_KIND_HUM_N),           # 单字
        # ······ 系
        ("······那个", OPENING_KIND_PAUSE),
        ("······？", OPENING_KIND_PAUSE_Q),
        ("······！突然想到", OPENING_KIND_PAUSE_X),
        # 无起手
        ("应该是吧", None),
        ("那个事情", None),                    # 不以嗯/啊/唔/······起手
        ("", None),
    ]
    for inp, exp in detect_cases:
        got = detect_opening(inp)
        ok = got == exp
        if not ok:
            fail += 1
        print(f"[{'PASS' if ok else 'FAIL'}] detect: {inp!r:30} -> {got} (exp {exp})")

    # 2) 连续 `······` 起手修复
    print()
    fix_cases = [
        ("······························啊那个", "······啊那个", True),  # 30 中点缩回 6
        ("············啊那个", "······啊那个", True),  # 12 → 6
        ("······啊那个", "······啊那个", False),  # 6 不动
        ("嗯······啊", "嗯······啊", False),  # 不是起手 ······
        ("", "", False),
    ]
    for inp, exp_text, exp_fixed in fix_cases:
        got, fixed = _fix_leading_double_ellipsis(inp)
        ok = (got == exp_text and fixed == exp_fixed)
        if not ok:
            fail += 1
        print(f"[{'PASS' if ok else 'FAIL'}] fix-dd: {inp!r:40} -> {got!r:25} fixed={fixed}")

    # 3) throttle: 同类前 3 条里 ≥ 2 条 → 轮换（rotate）替换
    print()
    # case A: 前 3 条都嗯起手 → 当前嗯被替换成最少用的（······ 优先、count 都 0）
    out, info = throttle_opening("嗯，那个事情", ["嗯…好的", "嗯，明白了", "嗯······对"])
    assert info["replaced"], f"expected replaced, info={info}"
    assert info["replacement_kind"] == OPENING_KIND_PAUSE, f"expected ······ tiebreak, info={info}"
    assert out.startswith("······"), f"expected ······ prefix, got {out!r}"
    print(f"[PASS] throttle A (3x 嗯 → rotate to ······): {out!r} info={info}")

    # case B (v6 收紧后): 前 3 条 1 条嗯、1 条 ······、1 条无 → HUM_GROUP=1 ≥ 1 触发 → rotate
    # 旧 v5 threshold=2 时不触发、v6 threshold=1 后任何 prior hum 就触发
    out, info = throttle_opening("嗯，那个事情", ["嗯…好的", "······对", "应该是吧"])
    assert info["replaced"], f"v6 expected REPLACED (HUM_GROUP=1 ≥ 1), info={info}"
    assert info["replacement_kind"] == OPENING_KIND_PAUSE
    print(f"[PASS] throttle B (v6: HUM_GROUP=1 触发): {out!r} info={info}")

    # case C: ······ 系列独立计数（嗯 多不会替 ······）
    out, info = throttle_opening("······那个", ["嗯，是的", "嗯…好", "嗯······对"])
    assert not info["replaced"], f"expected NOT replaced (different kind), info={info}"
    print(f"[PASS] throttle C (kind iso): {out!r} info={info}")

    # case D: ······？ 和 ······ 也独立
    out, info = throttle_opening("······？怎么了", ["······对", "······啊那个", "······好的"])
    assert not info["replaced"], f"expected NOT replaced (······？ vs ······), info={info}"
    print(f"[PASS] throttle D (······？ iso): {out!r} info={info}")

    # case E: 当前无起手式 → 不影响
    out, info = throttle_opening("应该是吧", ["嗯，对", "嗯…好"])
    assert info["current_kind"] is None
    print(f"[PASS] throttle E (no opening): {out!r}")

    # case F: 历史不够（< 2 prior with kinds）→ 不替换
    out, info = throttle_opening("嗯，那个", ["嗯，对"])
    assert not info["replaced"]
    print(f"[PASS] throttle F (history short): {out!r}")

    # case G: 连续省略号先缩回 6 点；PAUSE 起手保留（不 strip）
    out, info = throttle_opening("············啊那个", ["······对", "······好", "······啊"])
    assert info["double_ellipsis_fixed"], f"expected dd_fixed, info={info}"
    assert not info["stripped"], f"PAUSE 起手不应被 strip, info={info}"
    assert not info["replaced"], f"expected NOT rotate-replaced, info={info}"
    assert out == "······啊那个", f"expected canonical pause kept, got {out!r}"
    print(f"[PASS] throttle G (dd-fix + PAUSE keep): {out!r} info={info}")

    # case H: 剥完只剩省略号会回退原文（无 body 防御）
    out, info = throttle_opening("嗯······", ["嗯，对", "嗯…好", "嗯，啊"])
    # 剥"嗯······"后只剩 ······ / 标点、不通过 `[一-鿿\w]` 检测 → 回退原文
    assert not info["replaced"]
    assert not info["stripped"]
    print(f"[PASS] throttle H (no-body defensive): {out!r} replaced={info['replaced']}")

    # case I: rotate 后 body 已带标点 → 不双逗号
    out, info = throttle_opening("嗯，对的", ["嗯，啊", "嗯，那", "嗯，唔"])
    assert info["replaced"]
    # body 是 "对的"（剥完）、prefix "······" 加上去 → "······对的"
    # 注：本例 body 不带标点开头（_strip_opening lstrip 过了）；
    # 但下面 case J 测带标点的
    print(f"[PASS] throttle I (rotate clean): {out!r} info={info}")

    # case J: 同 kind 但 body 第一字是标点（罕见、e.g. 起手 strip 后 body 直接以 …… 开头）
    # 用 "嗯，，那" 这种 LLM 异常拼接做 stress
    out, info = throttle_opening("嗯，，，那个", ["嗯，对", "嗯，啊", "嗯…好"])
    # _strip_opening 用 tail 正则吃掉 "嗯，，，"、body = "那个"、加 ······ → "······那个"
    assert info["replaced"]
    assert "，，" not in out, f"unexpected double comma: {out!r}"
    print(f"[PASS] throttle J (no double-punct): {out!r}")

    # case K: 复合起手式（PAUSE + HUM 双重）在 PAUSE 保留策略下原样保留
    out, info = throttle_opening(
        "······嗯。······它今天又乱跑了吗。",
        ["······好的", "······对"],
    )
    assert not info["replaced"], f"expected NOT replaced, info={info}"
    assert not info["stripped"], f"expected PAUSE kept, info={info}"
    assert out == "······嗯。······它今天又乱跑了吗。", f"expected unchanged, got {out!r}"
    print(f"[PASS] throttle K (compound opening kept): {out!r} info={info}")

    # case K2: PAUSE 起手即使后面带 HUM 也原样保留
    out, info = throttle_opening(
        "······啊那个事情",
        ["······对", "······好"],
    )
    assert not info["stripped"], f"expected PAUSE kept, info={info}"
    assert not info["replaced"]
    assert out == "······啊那个事情", f"expected unchanged, got {out!r}"
    print(f"[PASS] throttle K2 (PAUSE keep): {out!r} info={info}")

    # case L: cur=PAUSE_NEUTRAL 即使前几条也是 PAUSE，仍保留 canon 起手
    out, info = throttle_opening(
        "······谢谢。······有你这句话",
        ["嗯，明白", "······对", "······好"],  # prior 2x pause
    )
    assert not info["stripped"], f"expected PAUSE kept, info={info}"
    assert not info["replaced"], f"expected NOT rotated, info={info}"
    assert out.startswith("······"), f"expected canonical pause kept, got {out!r}"
    print(f"[PASS] throttle L (PAUSE keep): {out!r} info={info}")

    # case M (2026-05-17 v5): cur=PAUSE_Q / PAUSE_X 不 rotate 不 strip、保留语义 marker
    out, info = throttle_opening(
        "······？怎么了",
        ["······？真的吗", "······？为什么"],  # 2x PAUSE_Q
    )
    # cur=PAUSE_Q、same_count=2≥2、但 v5 策略：PAUSE_Q 有疑问语义、保留原样
    assert not info["replaced"], f"expected NOT replaced (PAUSE_Q has semantic), info={info}"
    assert not info["stripped"], f"expected NOT stripped (semantic marker), info={info}"
    assert out.startswith("······？"), f"expected unchanged, got {out!r}"
    print(f"[PASS] throttle M (v5: PAUSE_Q semantic kept): {out!r} info={info}")

    # case N (2026-05-18): HUM 系组（嗯/啊/唔）合并计数——旧逻辑各自 count 都 = 1 不触发
    # 新逻辑：HUM_GROUP 总数 ≥ 2 → 触发 → rotate to PAUSE_NEUTRAL（不 rotate 到其他 HUM）
    out, info = throttle_opening(
        "嗯，那个事情",
        ["啊，那个", "唔，看", "嗯，对"],  # 3 个不同 HUM kind 混搭
    )
    assert info["replaced"], f"expected replaced (HUM_GROUP merged count=3), info={info}"
    assert info["replacement_kind"] == OPENING_KIND_PAUSE, f"expected rotate to PAUSE not another HUM, info={info}"
    assert info.get("hum_group_count") == 3, f"expected hum_group_count=3, info={info}"
    assert out.startswith("······"), f"expected ······ prefix, got {out!r}"
    print(f"[PASS] throttle N (v6: HUM_GROUP merged count → PAUSE): {out!r} info={info}")

    # case N2: HUM_GROUP 2 个混搭 + 1 个其他 = ≥ 2 触发
    out, info = throttle_opening(
        "啊，明白了",
        ["嗯，对", "······好的", "唔，看"],
    )
    # prior HUM_GROUP = 嗯+唔 = 2、PAUSE = 1、cur=HUM_A、HUM_GROUP count = 2 ≥ 2 → 触发
    assert info["replaced"], f"expected replaced (HUM_GROUP=2 mixed), info={info}"
    assert info["replacement_kind"] == OPENING_KIND_PAUSE, f"expected PAUSE, info={info}"
    print(f"[PASS] throttle N2 (v6: HUM_GROUP=2 混搭): {out!r} info={info}")

    # case N3 (v6b 收紧后): HUM_GROUP=1 现在足以触发（threshold 2 → 1）
    # 旧期望"不触发"已撤回——用户主动要求"进一步压制 hum 起手"。
    out, info = throttle_opening(
        "嗯，那个",
        ["······好", "······对", "应该是吧", "嗯，对"],
    )
    assert info["replaced"], f"v6b expected REPLACED (HUM_GROUP=1 ≥ 1), info={info}"
    assert info["replacement_kind"] == OPENING_KIND_PAUSE
    print(f"[PASS] throttle N3 (v6b: HUM_GROUP=1 触发): {out!r} info={info}")

    # case N4 (v6b 新增): prior 完全无 hum → cur hum 仍可保留
    out, info = throttle_opening(
        "嗯，那个",
        ["······好", "······对", "应该是吧", "······啊那个"],  # 全 pause / none
    )
    assert not info["replaced"], f"expected NOT replaced (HUM_GROUP=0), info={info}"
    print(f"[PASS] throttle N4 (v6b: HUM_GROUP=0 不触发): {out!r} info={info}")

    # case O (2026-05-18b 用户拍板): 独立 `······` bubble 不能被 throttle 误伤
    # 灯的招牌大停顿 = 单 bubble 只有 `······`（无字）、server bubble_expander 扩成 12 中点
    # throttle 的 step 5 guard `body and re.search([一-鿿\w], body)` 会拦下 strip 后空 body
    # 即使 prior 全是 pause、threshold 满足、独立 ······ bubble 也不被 strip → 保留招牌
    out, info = throttle_opening("······", ["······对", "······好", "······啊", "······嗯"])
    # cur=PAUSE_NEUTRAL、prior 4 个 pause、same_count=4 ≥ 2 触发
    # 但 strip 后 body="" 无字、guard 拦下 → 返回原 "······"
    assert not info["replaced"], f"独立 ······ bubble 不应被 rotate, info={info}"
    assert not info["stripped"], f"独立 ······ bubble 不应被 strip (保留招牌大停顿), info={info}"
    assert out == "······", f"独立 ······ bubble 应保留原样, got {out!r}"
    print(f"[PASS] throttle O (12-dot big_pause 招牌保留): {out!r} info={info}")

    # case O2: 独立 `······？` 同样保留
    out, info = throttle_opening("······？", ["······？真的吗", "······？为什么"])
    assert not info["replaced"]
    assert not info["stripped"]
    assert out == "······？"
    print(f"[PASS] throttle O2 (独立 ······？ 保留): {out!r} info={info}")

    # 4) extract_compound_opening：复合起手式拆分（2026-05-17）
    print()
    compound_cases = [
        # (input, expected_prefix, expected_remaining_starts_with_or_full)
        # 标准复合：PAUSE + HUM + 句末标点
        ("······嗯。······它今天又乱跑了吗。", "······嗯。", "······它今天又乱跑了吗。"),
        ("······啊。这样啊", "······啊。", "这样啊"),
        ("······唔！突然想到", "······唔！", "突然想到"),
        ("······嗯？怎么了", "······嗯？", "怎么了"),
        # 多个 hum 字重复也算
        ("······嗯嗯。明白了", "······嗯嗯。", "明白了"),
        # 非复合：HUM 后无句末标点、不拆
        ("······啊那个事情", None, "······啊那个事情"),
        ("······嗯，今天又乱跑了。", None, "······嗯，今天又乱跑了。"),
        # 非复合：单 HUM、无 PAUSE 起手
        ("嗯，那个", None, "嗯，那个"),
        # 非复合：纯 PAUSE 起手、无 HUM
        ("······它今天又乱跑了", None, "······它今天又乱跑了"),
        # 边界：空 / 仅 PAUSE
        ("", None, ""),
        ("······", None, "······"),
        # 非常规：PAUSE 后跟数字或英文（非 HUM）
        ("······好的", None, "······好的"),
    ]
    for inp, exp_prefix, exp_remain in compound_cases:
        got_prefix, got_remain = extract_compound_opening(inp)
        ok = (got_prefix == exp_prefix and got_remain == exp_remain)
        if not ok:
            fail += 1
        print(f"[{'PASS' if ok else 'FAIL'}] compound: {inp!r:36} -> prefix={got_prefix!r} remain={got_remain!r}")

    print()
    print("OVERALL:", "PASS" if fail == 0 else f"FAIL ({fail})")
