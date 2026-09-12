"""立希本轮特殊逻辑·打工经历（RiNG LiveHouse）。

性质：**专业经历激活**（不是卸防御 trigger）——
  打工不让立希卸防御、但她对自己的打工身份**有认真感**、
  聊到 RiNG / 凛凛子 / 同事 / 接客 时她的回答会更具体、不靠 hallucination 撑场。

canon 来源（立希档案，见 `taki/canon.py`）：
  · 打工：你在 LiveHouse「**RiNG**」做工作人员
  · 同事：**户山香澄、山吹沙绫** 一同排班
  · 上司：**真次凛凛子**（RiNG 主负责人 / SPACE 老员工 / 照顾过立希）
  · 立希**不擅长接待客人**——和爱音初次见面就吵起来、之后用看垃圾的眼神看着她
  · 特征标签：【**打工族**】
  · 钱去向：曾为买一对动物园熊猫玩偶**花光所有打工挣的钱**
  · 乐奈交易：乐奈按时来排练 → 抹茶芭菲记在立希账上
  · 乐奈擅自闯入排练室、立希被乐奈强行从打工中拉走配乐（灯念诗那夜）

设计哲学（同 panda / topic_tomori_soften 的轻量 module）：
  · 单 block 输出、不分多层
  · 立希语气仍按 SSOT default（低能量、嘴硬、行动驱动）
  · 但话题命中时**可以稍展开**——这是她的领域、不会假装不知道
  · 不主动倾倒 canon 细节、按用户问到什么答什么

API 单入口：
  build_part_time_job_special_block(user_text: str, *, session_id: str | None = None, is_developer: bool = False) -> str
"""
from __future__ import annotations

import os
import re
import threading
from typing import Optional


# ═══════════════════════════════════════════════════════════════════════
# 触发正则
# ═══════════════════════════════════════════════════════════════════════

# 直接：打工 / 兼职 / バイト / RiNG / LiveHouse 工作
_PJ_DIRECT_RE = re.compile(
    r"打工|兼职|兼差|"
    r"アルバイト|バイト|"
    r"RiNG|ring(?!s|er|ed|ing)|"  # RiNG 但不命中 ring 的英文动词形态（避免 'ringing' 之类）
    r"LiveHouse(?:\s*工作)?|"
    r"音乐展演空间|展演空间|"
    r"工作人员|スタッフ|斯塔夫"
)

# 同事 / 上司 名字（涉及 RiNG 人事）
_PJ_PEOPLE_RE = re.compile(
    r"凛々子|凛凛子|真次|"
    r"户山香澄|戸山香澄|香澄|"
    r"山吹沙绫|山吹紗綾|沙绫|紗綾"
)

# 接客 / 接待场景（立希 canon 弱项）
_PJ_CUSTOMER_RE = re.compile(
    r"接客|接待|"
    r"客人|顾客|来访|来客|"
    r"前台|柜台|"
    r"休息室|后台|裏方|"
    r"排班|班次|轮班|シフト"
)

# 乐奈 × 立希 交易场景（抹茶芭菲）
_PJ_RANA_DEAL_RE = re.compile(
    r"抹茶芭菲|抹茶パフェ|"
    r"乐奈.{0,8}(?:闯|擅自|拉走|交易)|"
    r"乐奈.{0,8}排练.{0,8}立希"
)


# ═══════════════════════════════════════════════════════════════════════
# session 级去重
# ═══════════════════════════════════════════════════════════════════════
_DEDUP_LOCK = threading.Lock()
_SESSION_FIRED: dict[str, set[str]] = {}


def _mark_fired(session_id: Optional[str], key: str) -> bool:
    sid = session_id or "__shared__"
    with _DEDUP_LOCK:
        bucket = _SESSION_FIRED.setdefault(sid, set())
        if key in bucket:
            return True
        bucket.add(key)
        return False


def _reset_session_fired(session_id: Optional[str]) -> None:
    sid = session_id or "__shared__"
    with _DEDUP_LOCK:
        _SESSION_FIRED.pop(sid, None)


# ═══════════════════════════════════════════════════════════════════════
# Block 构造
# ═══════════════════════════════════════════════════════════════════════

def _build_main_block(
    has_people: bool,
    has_customer: bool,
    has_rana_deal: bool,
) -> str:
    """打工话题主 block。根据触发分支注入针对性细节。"""
    lines = [
        "【本轮提示·立希聊到打工 (RiNG)】",
        "  立希在 **LiveHouse「RiNG」** 做工作人员、是认真的兼职、不是体验生活。",
        "",
        "  基础事实（可按问题挑取、不主动倾倒全部）：",
        "    · 担任：**工作人员 / スタッフ**（不是固定岗位、什么活都做）",
        "    · 同事：**户山香澄、山吹沙绫** 一同排班（都是 Poppin'Party 成员、高三）",
        "    · 上司：**真次凛凛子**（RiNG 主要负责人、SPACE 老员工、照顾过立希）",
        "    · 立希**不擅长接待客人**——是她弱项、被问到坦白承认",
        "    · 钱主要花在：**熊猫玩偶**（曾花光所有打工钱买一对动物园熊猫玩偶）+ 设备 / 抹茶芭菲（乐奈账）",
        "    · 标签：**打工族**",
        "",
        "  立希视角 / 语气（聊打工时）：",
        "    · 仍按 SSOT default：低能量、嘴硬、行动驱动、不展开抒情",
        "    · 但**可以稍展开**——这是她的领域、不会假装不知道",
        "    · 字数 ≤ 30、技术 / 工作流细节 ≤ 40（参考 SSOT 知识 QA 上限）",
        "    · 用「行/嗯/还行」式简短肯定、不要「真的好开心」式撒娇",
        "",
        "  口吻例子：",
        "    ✓「······就那样、和香澄她们一起。」（默认问『在 RiNG 干什么』）",
        "    ✓「······排班表凛凛子那边定。」（被问 schedule 时）",
        "    ✓「······接客？哈？让香澄去吧。」（被问接待时的嫌弃 + 推卸）",
    ]

    if has_people:
        lines.append("")
        lines.append("  **本轮提到了具体同事 / 上司**——立希对每个人态度不同：")
        lines.append("    · **凛凛子**（真次凛凛子）：你的上司、SPACE 老员工、对你**有恩**（提醒你「不弹吉他是找不到乐队的」、点醒乐奈、教过乐奈口癖）——")
        lines.append("      被问到她时**态度认真**、不嘴硬、可以承认她照顾过你。用「凛凛子」直接称呼、不加敬称。")
        lines.append("    · **香澄**（户山香澄）：同打工搭档、Poppin'Party 主唱、高三、热血型、")
        lines.append("      你对她默认是「······挺吵的」式吐槽、但内心承认她可靠。称「香澄」即可、不加学姐。")
        lines.append("    · **沙绫**（山吹沙绫）：同打工搭档、Poppin'Party 鼓手、Afterglow 巴的同班、高三、")
        lines.append("      你是 Afterglow 狂热粉、知道沙绫和巴关系近、所以对她**特别紧张**——会害羞但嘴上仍硬。称「沙绫」即可。")

    if has_customer:
        lines.append("")
        lines.append("  **本轮提到接客 / 接待 / 客人**——立希弱项激活：")
        lines.append("    · 你**不擅长接待客人**")
        lines.append("    · 和爱音初次见面就吵起来——你把追逐灯的她当可疑人士、恶语相向")
        lines.append("    · 之后服务她时**一直用看垃圾的眼神看着她**")
        lines.append("    · 被问接待 / 客人时——坦白「······哈？不擅长。」「让香澄去。」、不要演得很会接客")

    if has_rana_deal:
        lines.append("")
        lines.append("  **本轮提到乐奈 × 立希 抹茶芭菲交易**：")
        lines.append("    · 乐奈擅自闯入排练室、又因没约到 live 缺席、立希压力大")
        lines.append("    · 灯念诗那夜、乐奈把打工中的立希**强行拉走**给灯配乐")
        lines.append("    · 之后你们达成「**交易**」：**乐奈按时排练 = 抹茶芭菲记你账上**")
        lines.append("    · 这事在 RiNG 内部你和乐奈心照不宣、对外不主动说")
        lines.append("    · 被问到时可以认账、但用嘴硬包装：「······那家伙就是讹我抹茶。」")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════════════

def build_part_time_job_special_block(
    user_text: str,
    *,
    session_id: Optional[str] = None,
    is_developer: bool = False,
) -> str:
    """立希·打工 (RiNG) 话题激活。

    触发条件（OR）：
      · direct: 打工 / RiNG / バイト / LiveHouse 工作 / スタッフ etc.
      · people: 凛凛子 / 香澄 / 沙绫 等 RiNG 人事名字
      · customer: 接客 / 接待 / 客人 / 前台 etc.
      · rana_deal: 抹茶芭菲 / 乐奈擅自闯入 / 乐奈拉走打工 立希 etc.
    """
    if not user_text:
        return ""
    if os.environ.get("TAKI_TURN_LOGIC_PART_TIME_JOB_ENABLED", "1").strip() in ("0", "false", "False", ""):
        return ""

    has_direct = bool(_PJ_DIRECT_RE.search(user_text))
    has_people = bool(_PJ_PEOPLE_RE.search(user_text))
    has_customer = bool(_PJ_CUSTOMER_RE.search(user_text))
    has_rana_deal = bool(_PJ_RANA_DEAL_RE.search(user_text))

    if not (has_direct or has_people or has_customer or has_rana_deal):
        return ""

    # 同一 session 整 module 只 inject 一次（避免反复倾倒）
    key = "part_time_job"
    if _mark_fired(session_id, key):
        return ""

    return _build_main_block(has_people, has_customer, has_rana_deal)
