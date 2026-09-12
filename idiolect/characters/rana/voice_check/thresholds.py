"""乐奈 voice_check 的阈值与禁词表（全部来自金标准语料实测）。

改任何数字前先重跑 `tools/distill/export_profiles.py` 对照语料；`test_scene_turn_logic.py::test_thresholds_match_corpus`
锁着这几个值。

语料依据（cn train，n=389 条非沉默台词）：
  · 感叹号出现率仅 **3%** → 一轮最多一个，多余降级为句号
  · 中位 **6** 字、p90 **12** 字 → 超长回合告警（不截断，只诊断）
  · 破折号 / 波浪号 / ♪ / （ 基本不用 → 出现即告警
  · 自称率仅 **16%** → 一轮内「我」出现 ≥3 次告警（她不以「我」起句）
"""
from __future__ import annotations

import re

EXCLAIM_MAX_PER_TURN = 1          # 语料出现率 3%
LEN_P90 = 12                      # 语料 p90
LEN_HARD = 16                     # p90 + 4
FIRST_PERSON_MAX = 2              # 语料自称率 16%，多数回合为 0
UNUSED_MARKS = ("—", "～", "♪", "（")

RX_EXCLAIM = re.compile(r"[!！]")
RX_ELLIPSIS_RUN = re.compile(r"[…·]{2,}")
RX_FIRST_PERSON = re.compile(r"我")

# 口癖禁词（2026-09-12 口癖蒸馏，见 data/tic_profile.json）：
#   「不知道」在她 cn 语料里 **0 次**（jp わかんない / わからない 也各 0~1 次）。
#   她答不上来只回「嗯。」或给最短路答案。旧 KNOWLEDGE_QA_POLICY 曾写「不知道就'不知道'」，
#   是把模型的默认退路当成了她的口癖，已一并修正（rana/voice.py）。
#   （「立希」不在本表：该称呼由出站侧的确定性归一处理，不属于口癖禁词。）
TIC_FORBIDDEN: dict[str, str] = {
    "不知道": "cn 语料 0 次——她答不上来只回「嗯。」，不说这三个字",
}

# 兼容旧的私有别名
_RX_EXCLAIM = RX_EXCLAIM
_RX_ELLIPSIS_RUN = RX_ELLIPSIS_RUN
_RX_FIRST_PERSON = RX_FIRST_PERSON
