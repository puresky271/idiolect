"""灯专属：12 中点大停顿 bubble 注入器（deterministic）。

用户 2026-05-10 拍板：
  LLM 不会稳定输出独立省略号 bubble、所以 deterministic 后处理决定+注入。

三类（互斥、共享冷却 6 轮）：
  1) `············`           中性停顿（思考/发呆）— 不需要很强情感也可能发出来
  2) `············？`         疑惑（**仅出现在开头**）— 用户问得让灯犹豫
  3) `············！`         惊讶（**仅出现在开头**）— 用户说了让灯意外的话

冷却：6 轮（任一类 fire 后 6 轮内不再 fire、共享 budget）。

状态：进程内 dict，key=session_id（同 ws 会话内自然累计）。
进程重启自然清零、不持久化（大停顿是节奏调料、跨重启不需要 carry）。

为什么共享冷却而非按类独立：
  · 大停顿是「角色画风」、不是「情绪表」
  · 6 轮内出 2 次任意类型都会显得失重 / 卡顿
"""
from __future__ import annotations

import random
import re
from idiolect.scene_engine import SessionValues

# ── 三类形式 ─────────────────────────────────────────────
# 12 中点 + ?/! 是 server 主动决策的"大停顿+语义"组合、是 canon、保留。
# 区别 LLM 自然输出的 6 中点 ······？ / ······！：
#   · 6 中点 + ?/!：LLM 自己写的语义起手、紧凑、bubble_expander 不扩 (2026-05-18 收紧)
#   · 12 中点 + ?/!：server 决策的大停顿、视觉沉重、表"重量级疑问/突然反应"
# 三种 server 注入形式语义有别：
#   · ············    纯沉默 (思考 / 发呆)
#   · ············？  大停顿+疑惑 (用户问得让灯犹豫)
#   · ············！  大停顿+惊讶 (用户说了让灯意外的话)
_PAUSE_NEUTRAL = "············"
_PAUSE_QUESTION = "············？"
_PAUSE_EXCLAIM = "············！"

KIND_NEUTRAL = "neutral"
KIND_QUESTION = "question"
KIND_EXCLAIM = "exclaim"

_COOLDOWN_TURNS = 6

# ── 触发模式（正则）─────────────────────────────────────────
# 设计：每类一个**单一编译正则**（alternation），快、好维护、好 debug。
# 关键设计点：
#   · `\S{0,N}` 桥接——比固定关键词更容错（"还记得 ... 吗" 中间夹长定语也能命中）
#   · 中英文标点都匹配（？/? ！/!）
#   · 英文 canon 名（CRYCHIC / MyGO / Ave Mujica）IGNORECASE
#   · 不用 \b（中文没词边界）、用具体上下文 anchor 防误命中
#   · 慎用 `.*` — 都用有界量词、O(N) 不回溯爆炸

# 类 2 疑惑（深度问题专用、收紧 2026-05-10 拍板）：
#   只在用户问的是**深度问题**时才允许 `············？` 触发。
#   日常问话（在哪 / 怎么样 / 吃了吗 / 几点 / 好吗 等）**不触发**——
#   它们只是普通信息查询、灯不该用 12 中点大停顿来回应、否则破节奏（实测案例）。
#
#   两条命中规则（OR）：
#     A. 哲学 / 内省 / canon 记忆类 keyword 直接命中 (_DEEP_QUESTION_RE)
#     B. 含问号 `？/?` **且**同时含 thinking signal (CRYCHIC / 解散 / 写不出 / 心里 /
#        活着 / 一个人 / 等等) — 即使没明确哲学词、上下文也是 canon 重情绪
#
#   被切掉（现属"日常问"、不再触发 ············？）：
#     · 单纯的 [？?] 标点
#     · 怎么(会|办|可能|搞|回事|样)  — 「怎么样」「怎么办」太日常
#     · (是|有)?什么(意思|样子|情况|来着|感觉)  — 「什么意思」太日常
#     · 对吗 / 是吗 / 可以吗 / 好吗 / 行吗 / 对不对 / 是不是  — 礼貌确认类
#     · 为啥 / 算什么 / 怎么(才|能)算  — 口语 / 边界模糊
_DEEP_QUESTION_RE = re.compile(
    # 哲学 / 抽象命题
    r"意义|到底|究竟|本质"
    # 因果性 why（哲学性、不是日常「为什么不来」）
    r"|为什么(会|是)"
    r"|凭什么|何故|为何"
    # 怀疑 / 重申确认（情感重的）
    r"|真的(吗|假的)|确定吗|肯定吗"
    # canon 记忆类（灯式追忆）
    r"|还(记得|在|有|能|会|是)\S{0,12}吗"
    r"|你(还)?记得"
    # 反问灯本人（深度自指）
    r"|你怎么(看|想|觉得|认为)"
    r"|你(觉得|认为|确定|确信|觉不觉得)\S",  # 「你觉得呢」「你觉得 X」、单字 锚保命中
    re.IGNORECASE,
)

# 类 3 惊讶：用户抛突发事件 / 强情绪 / 反差消息。
#   覆盖：感叹号 / 突然系 / 完了系 / 我刚系 / 决定宣告 / 强赞叹
_EXCLAIM_RE = re.compile(
    r"[！!]"                                    # 任何感叹号
    r"|突然|突如其来|忽然|猛地|一下子"
    r"|竟然|居然|没想到|想不到|没料到|出乎意料"
    r"|原来(是|你|这|如此)?"
    r"|我?刚(才|刚)?\S{0,4}(发现|知道|看到|听到|想到|意识到|遇到)"
    r"|刚(才|刚)\S{0,3}(发生|出来|结束)"
    r"|我(决定|打算|要去|想好了|准备)|决定了"
    r"|完了|糟了|糟糕|不好了|坏了|出事|出大事|大事不好"
    r"|好(厉害|强|猛|帅|可爱)|太(厉害|牛|强|过分|夸张)|超(厉害|强|牛)"
    r"|震惊|懵了|傻眼|卧槽|我去"
    r"|哇+|嚯+|哎呀|天呐|天哪|我的天",
    re.IGNORECASE,
)

# 类 1 思考/发呆：内省 / canon 重情绪 / 灯式抽象主题。
#   覆盖：MyGO canon 专名 / 创作焦虑 / 内心向 / 抽象命题 / 回忆词 / 情绪低落词
_THINKING_RE = re.compile(
    # canon 专名（MyGO / Ave Mujica / CRYCHIC + 9 首歌）
    r"CRYCHIC|MyGO|Ave\s*Mujica|Mujica"
    r"|春日影|壱雫空|迷星叫|影色舞|詩超絆|碧天伴走|名無声|音一会|栞"
    # canon 主题词
    r"|解散|分崩|分开|分别|散了"
    r"|掉队|跟不上|拖后腿|抢救|救不了"
    r"|写不出|没写出|没灵感|卡住|想不出来"
    r"|（写|作）(歌词|歌|曲|词|旋律)"
    r"|歌词|旋律|和弦|副歌|主歌"
    # 内心 / 内省
    r"|心里|内心|心底|心情|心思"
    r"|想了想|想了很久|一直在想|一直想|反复想"
    r"|想起|回想|想到|记忆|回忆|那时候|曾经|以前|当年"
    # 抽象命题
    r"|意义|未来|过去|存在|消失|永远"
    r"|为什么(会|要)?活|活着|死亡|结束|放弃|逃避"
    r"|一个人|独自|孤单|孤独|寂寞|空"
    # 情绪低落 / 焦虑
    r"|害怕|怕|紧张|不安|焦虑|压抑|心痛|心碎|想哭|难受|疼"
    r"|不知道(怎么|该)|不会(说|表达)|说不出"
    # 反问灯本人
    r"|你(会)?怎么(想|看|觉得|办)"
    r"|你(在|是)?(想|看|觉得|觉不觉得)什么",
    re.IGNORECASE,
)

# ── 状态 ─────────────────────────────────────────────
_STATE = SessionValues()   # 有上限的 per-session 状态表（见 scene_engine.SessionValues）


def _new_state() -> dict:
    return {"turn": 0, "last_fire_turn": -10_000}


def _get_state(session_id: str) -> dict:
    return _STATE.get_or_create(session_id, _new_state)


def reset_state(session_id: str | None = None) -> None:
    """清状态（测试用）。session_id=None → 清全部。"""
    _STATE.reset(session_id)


# ── 意图分类 ─────────────────────────────────────────────
def _has_thinking_signal(user_text: str) -> bool:
    return bool(user_text and _THINKING_RE.search(user_text))


def _has_deep_question_signal(user_text: str) -> bool:
    """深度问题判定（2 条 OR）：
      A. _DEEP_QUESTION_RE 命中（哲学 / 因果性 why / 怀疑 / canon 记忆 / 反问灯）
      B. 含问号 + thinking signal 共现（即便没明确哲学词、canon 重情绪上下文也算）

    日常问话（在哪 / 怎么样 / 吃了吗 / 几点）**不命中**——这是设计的本意。
    """
    if not user_text:
        return False
    if _DEEP_QUESTION_RE.search(user_text):
        return True
    if ("？" in user_text or "?" in user_text) and _has_thinking_signal(user_text):
        return True
    return False


# 兼容名（旧 self-test 仍引用 `_has_question_signal`、改成深度版）
_has_question_signal = _has_deep_question_signal


def _has_exclaim_signal(user_text: str) -> bool:
    return bool(user_text and _EXCLAIM_RE.search(user_text))


def _afterglow_factor(char_state: dict | None) -> float:
    """afterglow active 时给 thinking/neutral 概率加权。"""
    if not isinstance(char_state, dict):
        return 1.0
    afterglow = char_state.get("emotional_afterglow") or {}
    if not isinstance(afterglow, dict):
        return 1.0
    decay = int(afterglow.get("decay_turns", 0) or 0)
    if decay <= 0:
        return 1.0
    emotion = str(afterglow.get("primary_emotion", "")).strip().lower()
    if emotion in ("sad", "concerned", "touched", "stung", "lonely", "anxious"):
        return 1.6 if decay >= 3 else 1.3
    return 1.1


# ── 主入口 ─────────────────────────────────────────────
def decide_big_pause_kind(
    *,
    user_text: str = "",
    char_state: dict | None = None,
    session_id: str = "default",
    rng: random.Random | None = None,
) -> str | None:
    """只决策、不动 reply。返回 fired_kind ∈ {neutral,question,exclaim,None}。

    分离决策的原因：分泡器会**过滤**纯省略号 bubble、≤ 50 字不拆，
    所以不能把 `············` 直接拼到 reply 文本前再 split、必须在 split 完
    之后由调用方把 pause 行作为独立 bubble prepend 到分泡列表。
    """
    rng = rng or random
    state = _get_state(session_id)
    state["turn"] += 1
    cur_turn = state["turn"]

    if cur_turn - state["last_fire_turn"] < _COOLDOWN_TURNS:
        return None

    af = _afterglow_factor(char_state)
    is_q_deep = _has_deep_question_signal(user_text)  # 仅深度问题、收紧后
    is_x = _has_exclaim_signal(user_text)
    is_t = _has_thinking_signal(user_text)

    fired: str | None = None
    if is_q_deep and rng.random() < 0.40:
        fired = KIND_QUESTION
    if not fired and is_x and rng.random() < 0.45:
        fired = KIND_EXCLAIM
    if not fired:
        base = 0.18
        if is_t:
            base += 0.20
        base *= af
        if rng.random() < min(0.70, base):
            fired = KIND_NEUTRAL

    if fired:
        state["last_fire_turn"] = cur_turn
    return fired


def pause_line_for(kind: str | None) -> str | None:
    if not kind:
        return None
    return {
        KIND_NEUTRAL: _PAUSE_NEUTRAL,
        KIND_QUESTION: _PAUSE_QUESTION,
        KIND_EXCLAIM: _PAUSE_EXCLAIM,
    }.get(kind)


def decide_and_inject_big_pause(
    reply_text: str,
    *,
    user_text: str = "",
    char_state: dict | None = None,
    session_id: str = "default",
    rng: random.Random | None = None,
) -> tuple[str, str | None]:
    """便利封装：决策 + 把 pause 拼到 reply 开头（用于 self-test / 简单场景）。

    主路径用 `decide_big_pause_kind` + `pause_line_for` 分两步、
    避免被 sentence-bubble splitter 过滤掉纯省略号 bubble。
    """
    if not reply_text or not isinstance(reply_text, str):
        return reply_text, None
    fired = decide_big_pause_kind(
        user_text=user_text, char_state=char_state,
        session_id=session_id, rng=rng,
    )
    line = pause_line_for(fired)
    if not line:
        return reply_text, None
    return line + "\n" + reply_text, fired


# ── self-test ────────────────────────────────────────────────
if __name__ == "__main__":
    # 1) 关键词召回单元（不打概率门、纯正则）
    # 深度问题（应命中 _has_deep_question_signal）
    q_hits = [
        "你觉得CRYCHIC的解散到底意味着什么？",  # 你觉得 + 解散 + 到底 + ?
        "为什么会这样",                          # 为什么会
        "还记得我们第一次见面那次吗",            # 还记得 ... 吗
        "你还记得当时素世说的话",                # 你记得
        "活着到底有什么意义",                    # 到底 + 意义 + 活着(thinking)
        "真的吗",                                # 真的吗
        "你觉得呢",                              # 你觉得 + ?
        "你怎么看这首歌？",                      # 你怎么看
        "凭什么这么对她",                        # 凭什么
        "CRYCHIC 还会重组吗？",                  # ? + thinking(CRYCHIC)
        "解散到底是为什么？",                    # 到底 + ? + thinking(解散)
    ]
    # 日常问 / 礼貌确认（**不应**命中 — 收紧的核心）
    q_miss = [
        "今天天气不错",                          # 无问号无深度词
        "我吃了拉面",
        "好的",
        "下午好呀，你现在在哪？",                # 用户实测的 case、纯日常
        "你在哪",
        "你在不在",
        "今天怎么样",
        "怎么样",
        "怎么办",
        "什么意思啊这是",                        # 「什么意思」日常、不再触发
        "对不对",                                # 礼貌确认
        "好吗",                                  # 同上
        "可以吗",
        "吃了吗",
        "几点了",
    ]
    x_hits = [
        "我刚才决定要去考音乐学院了！",
        "突然想到一件事",
        "完了完了完了",
        "天哪你居然知道",
        "卧槽这也太厉害了",
        "我决定下个月退出乐队",
        "刚刚发现一个事",
        "哇哇哇哇",
    ]
    x_miss = [
        "嗯",
        "今天去神田川",
        "你怎么看",  # 这条是问句不是惊叹（虽然两类可共存、但单独检测应该 only question）
    ]
    t_hits = [
        "你觉得CRYCHIC会重组吗",
        "我最近一个人的时候老是想起以前",
        "歌词写不出来",
        "为什么活着这件事",
        "Ave Mujica 上次的演出",
        "心里一直空着",
        "你怎么想",
        "梦到春日影",
    ]

    fail = 0
    for s in q_hits:
        if not _has_question_signal(s):
            print(f"[FAIL q_hit ] {s!r}"); fail += 1
    for s in q_miss:
        if _has_question_signal(s):
            print(f"[FAIL q_miss] {s!r}"); fail += 1
    for s in x_hits:
        if not _has_exclaim_signal(s):
            print(f"[FAIL x_hit ] {s!r}"); fail += 1
    for s in x_miss:
        if _has_exclaim_signal(s):
            print(f"[FAIL x_miss] {s!r}"); fail += 1
    for s in t_hits:
        if not _has_thinking_signal(s):
            print(f"[FAIL t_hit ] {s!r}"); fail += 1

    # 2) 冷却 + 决策流程
    rng = random.Random(42)
    reset_state()
    # 用真深度关键词触发首条、然后下一条立刻测冷却
    decide_and_inject_big_pause("嗯", user_text="意义到底是什么", session_id="cd", rng=rng)
    out, kind = decide_and_inject_big_pause("嗯", user_text="意义到底是什么", session_id="cd", rng=rng)
    if kind is not None:
        print(f"[FAIL cooldown] expected None got {kind}"); fail += 1
    for _ in range(5):
        decide_and_inject_big_pause("x", user_text="", session_id="cd", rng=rng)
    out, kind = decide_and_inject_big_pause("x", user_text="突然！", session_id="cd", rng=rng)
    if kind is None:
        print(f"[FAIL cooldown release]"); fail += 1

    print()
    print("OVERALL:", "PASS" if fail == 0 else f"FAIL ({fail})")
