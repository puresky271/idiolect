"""tomori.voice_check — 灯回复后处理强制清洗。

设计意图：
  prompt 层规则 LLM 不一定遵守、需要 deterministic 后处理把所有偏差
  清洗到灯的 canonical form。

当前包含（按调用顺序）：
  - ya_a_repetition.py:       「石头呀、树叶啊」→「石头、树叶」；「开心呀」→「开心」；「好呀/好啊」→「好」
  - space_pause.py:           CJK 裸空格补偿（空格当停顿 → `······`；省略号/标点相邻空格删）
  - punctuation.py:           随机把 1 个 ，/。 替换成 `······`（打散过于流畅）
  - exclamation_softener.py:  啊/吗 + ，/。 → 啊/吗 + `······`（短感叹软化）
  - ellipsis_pair.py:         单 ？/！ → `······？` / `······！`（配对强制）
  - ellipsis.py:              所有 ellipsis 变体（`…/……/.../······{n≠6}/——`）→ `······`（兜底归一）
  - ellipsis_quota.py:        超额裸 `······` 组降级回「，」/去掉（六点轰炸治理）
  - bubble_expander.py:       整行只有省略号的 bubble → `············`（12 中点）

不在 `clean_reply` 流程里的：opening_throttle.py（起手节流，要 history，由调用方单独调）。

调用顺序考量：
  · space_pause 在 punctuation 前（补出来的 ······ 计入 v5 existing 抵消、不叠加六点）
  · punctuation 先（替换可能产 `············`、由 ellipsis 兜底）
  · exclamation_softener 在 punctuation 之后（前者可能消除 啊。/吗。 让 softener 没事干、但也无害）
  · ellipsis_pair 在 softener 之后（softener 可能引入新 ······、不能让 pair 错误判 already_paired）
    actually pair 检查的是 `······？` 形式、softener 产的是 `啊······` 不和 ？ 相邻、互不影响
  · ellipsis 最后（兜底所有变体、含中间步骤新产生的 `············`）

后续可加（**都还没实现**，本仓库不含这几个模块；列在这里是为了标出后处理的已知缺口）：
  - sajiao_tail.py:  末尾撒娇词（呢/啦/呀/嘛/哦）清洗
  - confident.py:    评价副词 / confident 定论 词清洗
  - knowing.py:      知性化归纳句式检测
  - empathy_block.py: 不会共情语句的硬词检测
"""
from __future__ import annotations

from .ellipsis import (
    TOMORI_ELLIPSIS,
    normalize_ellipsis,
)
from .ya_a_repetition import strip_same_word_pair, strip_word_particle, strip_ya_a_enumeration
from .punctuation import random_replace_one_punct
from .exclamation_softener import soften_exclamation_endings, insert_separator_after_ah
from .ellipsis_pair import pair_ellipsis_with_question_excl
from .ellipsis_quota import demote_excess_ellipsis
from .space_pause import compensate_cjk_space_pause
from .bubble_expander import expand_ellipsis_only_bubbles
from .opening_throttle import (
    throttle_opening,
    detect_opening,
    OPENING_KIND_HUM_N,
    OPENING_KIND_HUM_A,
    OPENING_KIND_HUM_U,
    OPENING_KIND_PAUSE,
    OPENING_KIND_PAUSE_Q,
    OPENING_KIND_PAUSE_X,
)

__all__ = (
    "TOMORI_ELLIPSIS",
    "normalize_ellipsis",
    "strip_ya_a_enumeration",
    "strip_same_word_pair",
    "strip_word_particle",
    "random_replace_one_punct",
    "soften_exclamation_endings",
    "insert_separator_after_ah",
    "pair_ellipsis_with_question_excl",
    "demote_excess_ellipsis",
    "compensate_cjk_space_pause",
    "expand_ellipsis_only_bubbles",
    "clean_reply",
    # opening_throttle 单独 import（不在 clean_reply 流程里、需要 history）
    "throttle_opening",
    "detect_opening",
    "OPENING_KIND_HUM_N",
    "OPENING_KIND_HUM_A",
    "OPENING_KIND_HUM_U",
    "OPENING_KIND_PAUSE",
    "OPENING_KIND_PAUSE_Q",
    "OPENING_KIND_PAUSE_X",
)


def clean_reply(text: str) -> tuple[str, dict]:
    """灯回复后处理总入口。

    Returns:
        (cleaned_text, info_dict)
        info_dict 含每个清洗器的 violations 计数、用于 log / self_eval。

    流程：
      0. ya_a_repetition:      物件枚举去呀/啊；同词重复折叠；情绪词/好词尾缀清洗
      0d. space_pause:         CJK 裸空格补偿（空格当停顿 → `······`）
      1. punctuation:          随机 1 个 ，/。 → `······`
      2. exclamation_softener: 啊/吗 + ，/。 → 啊/吗 + `······`
      3. ellipsis_pair:        单 ？/！ → `······？` / `······！`
      4. ellipsis:             所有 ellipsis 变体兜底归一到 `······`
      4b. ellipsis_quota:      超额裸 `······` 组降级回「，」/去掉（六点轰炸治理）
      5. bubble_expander:      纯省略号 bubble (整行只有 ······[？！]*) → `············`（12 中点）
                               注：必须在 ellipsis 之后、否则 12 会被归一回 6
    """
    if not text:
        return text, {"violations": {}, "ok": True}

    info: dict = {"violations": {}, "ok": True}

    # Stage 0a: 物件枚举「石头呀、树叶啊」→「石头、树叶」
    text, ya_a_enum_count = strip_ya_a_enumeration(text)
    if ya_a_enum_count > 0:
        info["violations"]["ya_a_enumeration"] = ya_a_enum_count
        info["ok"] = False

    # Stage 0b: 同词重复「好呀，好啊」→「好」
    text, same_pair_count = strip_same_word_pair(text)
    if same_pair_count > 0:
        info["violations"]["ya_a_same_word_pair"] = same_pair_count
        info["ok"] = False

    # Stage 0c: 情绪词/好词尾缀「开心呀」「好啊」→「开心」「好」
    text, word_particle_count = strip_word_particle(text)
    if word_particle_count > 0:
        info["violations"]["ya_a_word_particle"] = word_particle_count
        info["ok"] = False

    # Stage 0d: CJK 裸空格补偿（2026-08-25：空格当停顿 → ······、防下游删空格后两句熔成零标点连读）
    text, space_pause_count = compensate_cjk_space_pause(text)
    if space_pause_count > 0:
        info["violations"]["space_pause"] = space_pause_count
        info["ok"] = False

    # Stage 1: punctuation 随机替换
    text, punct_count = random_replace_one_punct(text)
    if punct_count > 0:
        info["violations"]["punctuation"] = punct_count
        info["ok"] = False

    # Stage 2: 啊/吗 + ，/。 软化
    text, soften_count = soften_exclamation_endings(text)
    if soften_count > 0:
        info["violations"]["exclamation_softener"] = soften_count
        info["ok"] = False

    # Stage 2b: 啊 + 中文 → 插 ······ (70%) 或 ， (30%) — 2026-05-12 新加
    text, insert_count = insert_separator_after_ah(text)
    if insert_count > 0:
        info["violations"]["insert_separator_after_ah"] = insert_count
        info["ok"] = False

    # Stage 3: ？/！ 强制配对 `······`
    text, pair_count = pair_ellipsis_with_question_excl(text)
    if pair_count > 0:
        info["violations"]["ellipsis_pair"] = pair_count
        info["ok"] = False

    # Stage 4: ellipsis 兜底归一所有变体到 6 中点
    text, ellipsis_count = normalize_ellipsis(text)
    if ellipsis_count > 0:
        info["violations"]["ellipsis"] = ellipsis_count
        info["ok"] = False

    # Stage 4b: ······ 组数配额——超额裸组降级回「，」/去掉（2026-08-08 六点轰炸治理）
    text, quota_count = demote_excess_ellipsis(text)
    if quota_count > 0:
        info["violations"]["ellipsis_quota"] = quota_count
        info["ok"] = False

    # Stage 5: 纯省略号 bubble 扩展 6 → 12（必须在 ellipsis 兜底之后）
    text, expand_count = expand_ellipsis_only_bubbles(text)
    if expand_count > 0:
        info["violations"]["bubble_expand"] = expand_count
        # 这一步是 enrichment、不是 violation 修复、ok 状态不变

    return text, info
