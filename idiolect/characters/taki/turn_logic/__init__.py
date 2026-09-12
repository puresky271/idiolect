"""taki.turn_logic — 立希在特定对话场景下的"轮次级"逻辑入口（仿 tomori / anon turn_logic）。

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

注：本模块产物供 taki.api render_supplemental_blocks 调用、最终注入到 system prompt。
"""
from __future__ import annotations

import os


def _enabled() -> bool:
    return os.environ.get("TAKI_TURN_LOGIC_ENABLED", "1").strip() not in ("0", "false", "False", "")


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
        character:    角色名
        session_id:   ws session id（可选）— 子系统用作 per-session 去重 key；
                      None → 子系统 fallback 单一 bucket（共享去重状态）
        is_developer: True = 本轮触发对象是**开发者**（smoke / debug / config）、
                      False = 本轮触发对象是**普通用户**（in-canon 对话）。

    Returns:
        prompt 片段字符串、无内容时返 ""
    """
    # 兼容多种名字写法（立希 / 椎名立希 / Rikki / Taki ...）
    try:
        from ..api import is_taki
        if not is_taki(character):
            return ""
    except Exception:
        if character != "立希":
            return ""

    if not _enabled():
        return ""
    # 2026-05-12: auto_greet / idle 路径下 user_text 为空（主动开口、不是回应）。
    # 那时仍需要触发时段/状态类子系统（如 late_night_window）、所以不能直接 return。
    # text-driven 子系统（composition / panda）自己内部判 user_text 空。
    _is_text_driven_only_path = mode == "chat" and not user_text
    if _is_text_driven_only_path:
        return ""

    blocks: list[str] = []

    # ─── 子系统 1: 编曲 / 作曲 / DTM / 鼓 知识 ───
    try:
        from .composition import build_composition_special_block
        _comp_blk = build_composition_special_block(user_text, session_id=session_id, is_developer=is_developer)
        if _comp_blk:
            blocks.append(_comp_blk)
    except Exception as _err:
        print(f"[TakiTurnLogic/composition] error: {_err}", flush=True)

    # ─── 子系统 2: 熊猫（卸防御 trigger #1） ───
    try:
        from .panda import build_panda_special_block
        _panda_blk = build_panda_special_block(user_text, session_id=session_id, is_developer=is_developer)
        if _panda_blk:
            blocks.append(_panda_blk)
    except Exception as _err:
        print(f"[TakiTurnLogic/panda] error: {_err}", flush=True)

    # ─── 子系统 3: 灯相关话题（卸防御 trigger #3、专注 + 放软） ───
    try:
        from .topic_tomori_soften import build_tomori_soften_special_block
        _tomo_blk = build_tomori_soften_special_block(user_text, session_id=session_id, is_developer=is_developer)
        if _tomo_blk:
            blocks.append(_tomo_blk)
    except Exception as _err:
        print(f"[TakiTurnLogic/topic_tomori_soften] error: {_err}", flush=True)

    # ─── 子系统 4: 打工经历（RiNG / 凛凛子 / 香澄 / 沙绫 / 接客 / 乐奈抹茶交易） ───
    try:
        from .part_time_job import build_part_time_job_special_block
        _pj_blk = build_part_time_job_special_block(user_text, session_id=session_id, is_developer=is_developer)
        if _pj_blk:
            blocks.append(_pj_blk)
    except Exception as _err:
        print(f"[TakiTurnLogic/part_time_job] error: {_err}", flush=True)

    # ─── 子系统 5: Afterglow 狂热粉（卸防御 trigger #4、失态型） ───
    try:
        from .afterglow_fan import build_afterglow_fan_special_block
        _ag_blk = build_afterglow_fan_special_block(user_text, session_id=session_id, is_developer=is_developer)
        if _ag_blk:
            blocks.append(_ag_blk)
    except Exception as _err:
        print(f"[TakiTurnLogic/afterglow_fan] error: {_err}", flush=True)

    # ─── 子系统 6: 凌晨窗口（夜猫子互相理解、不说教） ───
    # 时段触发、不依赖 user_text；只在凌晨 0-5 + night_owl_today=True 时激活
    try:
        from .late_night_window import build_late_night_window_special_block
        _late_blk = build_late_night_window_special_block(
            user_text,
            now_jst=now_jst,
            ledger=ledger,
            session_id=session_id,
            is_developer=is_developer,
            mode=mode,
        )
        if _late_blk:
            blocks.append(_late_blk)
    except Exception as _err:
        print(f"[TakiTurnLogic/late_night_window] error: {_err}", flush=True)

    # ─── 子系统 8: 乐奈 / 野猫（`rana_cat` 场景，野猫 lift 8.49 = 全表最强绑定） ───
    # 立希此前**没有任何乐奈相关场景模块**，这个信号无处落地。
    # 这一轮她要做的是「抱怨 + 去处理」（中位 20 字），不是 taki_soft_spot 那种单纯软肋（10 字）。
    if not is_developer:
        try:
            from idiolect.scene_engine import build_scene_blocks
            from .scenes import TAKI_RANA_SCENES
            blocks.extend(build_scene_blocks(user_text, TAKI_RANA_SCENES,
                                             session_id=session_id, max_blocks=1))
        except Exception as _err:
            print(f"[TakiTurnLogic/rana_related] error: {_err}", flush=True)

    # ─── 通用场景层（13 个五角色共有的场景；本角色一套正文） ───
    # 2026-09-12 新增：`affection`（被示好）实测是两条 probe 臂里最差的场景——
    # 立希中位 2 字（该场景参照中位 12）＝过度沉默，所以需要场景级指引，长度目标压不住。
    # 必须排在 scene_mode_adapter **之前**（后者按设计最末注入）。
    try:
        from idiolect.general_scenes import build_general_scene_blocks
        blocks.extend(build_general_scene_blocks(
            "立希", user_text, session_id=session_id, max_blocks=1,
            is_developer=is_developer))
    except Exception as _err:
        print(f"[TakiTurnLogic/general_scenes] error: {_err}", flush=True)

    # ─── 子系统 7: 场景模式适配器（Mode A/B/C 切档） ───
    # 多路加权检测用户当下场景、决定要不要从默认 Mode A 切到 Mode B（平铺）或 Mode C（短温度）
    # 必须**最末**注入：让 panda / 灯 / Afterglow / 凌晨 / 熬夜 等卸防御 block 先决定
    if user_text and scene_context:
        try:
            from .scene_mode_adapter import build_scene_mode_adapter_block
            _scene_blk = build_scene_mode_adapter_block(
                user_text,
                session_id=session_id,
                is_developer=is_developer,
                context=scene_context,
            )
            if _scene_blk:
                blocks.append(_scene_blk)
        except Exception as _err:
            print(f"[TakiTurnLogic/scene_mode_adapter] error: {_err}", flush=True)

    # TODO 后续子系统：
    #   - daytime_drowsy: 白天没精神（凌晨窗口的镜像、捕捉熬夜后白天的低能量）
    #   - family_school_anchor: 姐姐 / 祥子 / 花咲川转校 硬约束

    # 双线包装：每个 block 独立加 ═════ 上下边界、让 LLM 视觉上把它们当独立 fence 看待
    return _wrap_blocks(blocks)


# ─────────────────────────────────────────────────────────────
# 双线包装 helper（5 角色 turn_logic 共用形态）
# ─────────────────────────────────────────────────────────────
_BLOCK_BORDER = "═" * 72


def _wrap_blocks(blocks: list[str]) -> str:
    """每个 block 加双线上下边界、之间用空行隔开。"""
    if not blocks:
        return ""
    wrapped = [f"{_BLOCK_BORDER}\n{b.rstrip()}\n{_BLOCK_BORDER}" for b in blocks if b]
    return "\n\n".join(wrapped)
