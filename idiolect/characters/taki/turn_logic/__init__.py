"""taki.turn_logic — 立希在特定对话场景下的"轮次级"逻辑入口。

设计意图：
  - **本轮触发**：每次 chat reply 前根据 user_text 判断是否注入特殊指引
  - **窄入口**：只暴露 build_taki_special_block(user_text, character, *, session_id, is_developer)
  - **可叠加**：内部按场景路由
  - **可关闭**：env flag `TAKI_TURN_LOGIC_ENABLED=0` 一键回退

**taki 专属主题——卸下防御 / 流露真情**：
  其他角色的 turn_logic 是"知识扩展"（爱音美妆 / 灯昆虫天文 etc.）；
  立希的 turn_logic 主题是**"什么时候她会卸下嘴硬冷谈的外壳、露出真实温度"**。
  每个软肋一个 module、按 canon 触发。

当前状态（2026-05-12）：
  · 子系统 1：编曲 / 作曲 / DTM / 鼓（composition.py）— 知识激活
    3 层渐进 + 灯写词作曲流程 + 祥子作曲劣等感 双 canon override
  · 子系统 2：**熊猫（panda.py）— 卸防御 trigger #1**
    canon 最大萌点、聊到时语气兴奋 + 变软、但不装专家、被调侃时嘴硬回弹
  · 子系统 3：**凌晨窗口（late_night_window.py）— 卸防御 trigger #2（时段触发）**
    凌晨 0-5 + night_owl_today=True 时激活、chat / autogreet 双 mode
  · 子系统 4：**灯相关话题（topic_tomori_soften.py）— 卸防御 trigger #3**
    聊到灯时专注 + 不由自主放软、称呼硬锁「灯」零修饰
  · 子系统 5：**打工经历（part_time_job.py）— 专业经历激活（非卸防御）**
    RiNG / 凛凛子 / 香澄 / 沙绫 / 接客 / 乐奈抹茶交易 canon、按子分支注入针对性细节
  · 子系统 6：**Afterglow 狂热粉（afterglow_fan.py）— 卸防御 trigger #4（失态型）**
    Afterglow / 5 成员（兰/巴/モカ/ひまり/つぐみ）/ 念错纠正 / live 场景、紧张+激动+脸红+语无伦次
  · 后续按子系统逐个加：
    - daytime_drowsy（白天没精神：低能量加深、提到熬夜话题自然带）
    - family_school_anchor（姐姐 / 真希 / 祥子 / 花咲川转校 canon 触发硬约束）

装配样板（子系统执行 / 通用场景层 / fence 包装 / env 开关语义）统一下沉在
`idiolect.scene_engine`，本文件只声明数据与顺序；子系统走 `lazy_builder`
延迟 import（单模块坏掉只禁用它自己，沿用旧 try/except 的隔离语义）。

注：本模块产物供 taki.api render_supplemental_blocks 调用、最终注入到 system prompt。
"""
from __future__ import annotations

import logging
import os

from idiolect.registry import canonicalize_name
from idiolect.scene_engine import (
    append_general_scene_blocks,
    build_scene_blocks,
    env_enabled,
    lazy_builder,
    run_modules,
    wrap_blocks,
)

_log = logging.getLogger(__name__)

_PKG = "idiolect.characters.taki.turn_logic"

# ── 子系统层（顺序 = 注入顺序；不封顶、不带反照抄脚注——保持既有输出形态）──
_SUBSYSTEMS = (
    # 子系统 1: 编曲 / 作曲 / DTM / 鼓 知识
    ("composition", lazy_builder(_PKG, "composition", "build_composition_special_block")),
    # 子系统 2: 熊猫（卸防御 trigger #1）
    ("panda", lazy_builder(_PKG, "panda", "build_panda_special_block")),
    # 子系统 3: 灯相关话题（卸防御 trigger #3、专注 + 放软）
    ("topic_tomori_soften", lazy_builder(_PKG, "topic_tomori_soften",
                                         "build_tomori_soften_special_block")),
    # 子系统 4: 打工经历（RiNG / 凛凛子 / 香澄 / 沙绫 / 接客 / 乐奈抹茶交易）
    ("part_time_job", lazy_builder(_PKG, "part_time_job", "build_part_time_job_special_block")),
    # 子系统 5: Afterglow 狂热粉（卸防御 trigger #4、失态型）
    ("afterglow_fan", lazy_builder(_PKG, "afterglow_fan", "build_afterglow_fan_special_block")),
    # 子系统 6: 凌晨窗口（时段触发、不依赖 user_text）
    ("late_night_window", lazy_builder(_PKG, "late_night_window",
                                       "build_late_night_window_special_block")),
    # TODO 后续子系统：
    #   - daytime_drowsy: 白天没精神（凌晨窗口的镜像、捕捉熬夜后白天的低能量）
    #   - family_school_anchor: 姐姐 / 祥子 / 花咲川转校 硬约束
)


def _enabled() -> bool:
    return env_enabled(os.environ.get("TAKI_TURN_LOGIC_ENABLED"))


def build_taki_special_block(
    user_text: str,
    character: str,
    *,
    session_id: str | None = None,
    is_developer: bool = False,
    now_jst=None,
    ledger: dict | None = None,
    mode: str = "chat",
    scene_context: dict | None = None,
) -> str:
    """立希本轮特殊指引拼装。

    Args:
        user_text:    当前 turn 的 user message
        character:    角色名（经 registry 归一化的任意别名）
        session_id:   ws session id（可选）— 子系统用作 per-session 去重 key；
                      None → 子系统 fallback 单一 bucket（共享去重状态）
        is_developer: True = 本轮触发对象是**开发者**（smoke / debug / config）、
                      False = 本轮触发对象是**普通用户**（in-canon 对话）。

    Returns:
        prompt 片段字符串、无内容时返 ""
    """
    # 名字表只有 registry 一份（见 AGENTS.md）：自带名单会与之漂移，
    # 代价是别名能解析到包、却在包内被判 False 静默返空。
    if canonicalize_name(character) != "立希":
        return ""
    if not _enabled():
        return ""
    # 2026-05-12: auto_greet / idle 路径下 user_text 为空（主动开口、不是回应）。
    # 那时仍需要触发时段/状态类子系统（如 late_night_window）、所以不能直接 return。
    # text-driven 子系统（composition / panda）自己内部判 user_text 空。
    _is_text_driven_only_path = mode == "chat" and not user_text
    if _is_text_driven_only_path:
        return ""

    blocks, _fired = run_modules(
        _SUBSYSTEMS, user_text,
        label="TakiTurnLogic",
        shared_kwargs={"session_id": session_id, "is_developer": is_developer},
        per_module_kwargs={
            "late_night_window": {"now_jst": now_jst, "ledger": ledger, "mode": mode},
        })

    # ─── 子系统 8: 乐奈 / 野猫（`rana_cat` 场景，野猫 lift 8.49 = 全表最强绑定） ───
    # 立希此前**没有任何乐奈相关场景模块**，这个信号无处落地。
    # 这一轮她要做的是「抱怨 + 去处理」（中位 20 字），不是 taki_soft_spot 那种单纯软肋（10 字）。
    if not is_developer:
        try:
            from .scenes import TAKI_RANA_SCENES
            blocks.extend(build_scene_blocks(user_text, TAKI_RANA_SCENES,
                                             session_id=session_id, max_blocks=1))
        except Exception as _err:
            _log.warning("[TakiTurnLogic/rana_related] error: %s", _err)

    # ─── 通用场景层（13 个五角色共有的场景；本角色一套正文） ───
    # 2026-09-12 新增：`affection`（被示好）实测是两条 probe 臂里最差的场景——
    # 立希中位 2 字（该场景参照中位 12）＝过度沉默，所以需要场景级指引，长度目标压不住。
    # 必须排在 scene_mode_adapter **之前**（后者按设计最末注入）。
    append_general_scene_blocks(
        blocks, "立希", user_text, label="TakiTurnLogic",
        session_id=session_id, is_developer=is_developer, max_blocks=1)

    # ─── 子系统 7: 场景模式适配器（Mode A/B/C 切档） ───
    # 多路加权检测用户当下场景、决定要不要从默认 Mode A 切到 Mode B（平铺）或 Mode C（短温度）
    # 必须**最末**注入：让 panda / 灯 / Afterglow / 凌晨 / 熬夜 等卸防御 block 先决定
    if user_text and scene_context:
        adapter_blocks, _ = run_modules(
            (("scene_mode_adapter",
              lazy_builder(_PKG, "scene_mode_adapter", "build_scene_mode_adapter_block")),),
            user_text,
            label="TakiTurnLogic",
            shared_kwargs={"session_id": session_id, "is_developer": is_developer,
                           "context": scene_context})
        blocks.extend(adapter_blocks)

    # 双线包装：每个 block 独立加 ═════ 上下边界、让 LLM 视觉上把它们当独立 fence 看待
    return wrap_blocks(blocks)
