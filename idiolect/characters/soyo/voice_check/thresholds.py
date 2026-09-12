"""素世 voice_check 的阈值与正则（全部来自金标准语料实测）。

改任何数字前先重跑 `char_style_spec.py`；`test_scene_turn_logic.py::test_thresholds_match_corpus`
锁着这几个值。

语料依据（cn train，n=862 条非沉默台词）：
  · 感叹号出现率仅 **6%** → 一轮最多一个，多余降级为句号
  · 中位 **16** 字、p90 **30** 字 → 超长回合告警（硬上限取 p90+4）
  · 顿号 / 破折号 / 波浪号 / ♪ 基本不用 → 出现即告警
  · 自称率 33%（比乐奈宽松，所以 FIRST_PERSON_MAX=4）
"""
from __future__ import annotations

import re

EXCLAIM_MAX_PER_TURN = 1          # 语料出现率 6%
LEN_P90 = 30
LEN_HARD = 34                     # p90 + 4
UNUSED_MARKS = ("、", "—", "～", "♪")
FIRST_PERSON_MAX = 4              # 语料自称率 33%，比乐奈宽松

RX_EXCLAIM = re.compile(r"[!！]")
RX_ELLIPSIS_RUN = re.compile(r"[…·]{2,}")
RX_FIRST_PERSON = re.compile(r"我")

# 同伴本名（不带「小」前缀的裸用法）
PEERS = ("爱音", "灯", "立希", "乐奈")
RX_BARE_PEER = re.compile(r"(?<![小])(" + "|".join(PEERS) + r")")

# ── 强制替换：裸本名 → 小名（与爱音的 soyorin/rikki 同理）───────
# 语料依据：素世 1085 条里裸名只出现 6 次，其中 4 次是**别的意思**
#   （「负责关灯」「别的灯光」= 灯具；「高松灯」「要乐奈」= 姓氏全名），
#   说明她几乎从不用裸名 → 替换规则很安全。
# 参考实现：response_contract/sanitization.py::_enforce_dialogue_nickname_policy 的
#   `_tomori_nickname_repl`（用窗口排除「关灯/灯光/灯笼」等假阳性）。
SURNAMES = ("高松", "千早", "椎名", "长崎", "要", "若叶")
RX_FULL_NAME = re.compile("(" + "|".join(SURNAMES) + r")(" + "|".join(PEERS) + r")")

# 「灯」单独处理：它同时是常用名词（灯具/灯光/关灯…）
LAMP_CONTEXTS = (
    "灯光", "灯火", "灯笼", "灯饰", "灯泡", "灯具", "灯牌", "灯罩", "灯塔", "灯会",
    "街灯", "路灯", "车灯", "台灯", "电灯", "吊灯", "彩灯", "提灯", "点灯", "开灯",
    "关灯", "亮灯", "打灯", "红绿灯", "信号灯", "霓虹灯", "聚光灯", "圣诞灯", "床头灯",
    # 动宾倒置形态（「把灯打开」「灯亮着」「灯坏了」）——「开灯」在表里但
    # 「灯打开」语序相反，靠子串匹配抓不到，单列
    "灯打开", "灯关", "灯亮", "灯灭", "灯坏", "灯闪", "灯在闪", "灯太亮",
)

# 「乐奈」的「要」是姓但不是所有场合；用全名正则已覆盖「要乐奈」
RX_MUTSU = re.compile(r"(?<![小])睦")

# 兼容旧的私有别名（外部/历史脚本按 `sv._PEERS` 这类名字取过）
_RX_EXCLAIM = RX_EXCLAIM
_RX_ELLIPSIS_RUN = RX_ELLIPSIS_RUN
_RX_FIRST_PERSON = RX_FIRST_PERSON
_PEERS = PEERS
_RX_BARE_PEER = RX_BARE_PEER
_SURNAMES = SURNAMES
_RX_FULL_NAME = RX_FULL_NAME
_LAMP_CONTEXTS = LAMP_CONTEXTS
_RX_MUTSU = RX_MUTSU
