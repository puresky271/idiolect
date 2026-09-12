"""场景模块共用框架（素世 / 乐奈 turn_logic 用）。

为什么抽出来：taki / tomori 的每个模块都各自实现「触发正则 + per-session 去重 +
env flag + block 构建」，6 个场景就要抄 6 遍。这里把这层样板抽成一个引擎，
各场景只声明「触发词 + 正文」，减少漂移与维护成本。

设计约束（对齐既有 turn_logic 约定）：
  · 窄入口：只暴露 `build_scene_block(user_text, scene_key, ...)`
  · 可关闭：env flag `<PREFIX>_TURN_LOGIC_<SCENE>_ENABLED=0`
  · per-session 去重：同一场景在同一 session 内只注入一次，避免每轮复读
  · 无副作用：不读写全局状态（去重状态按 session 存于模块内字典）
"""
from __future__ import annotations

import os
import re
import threading
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class SceneModule:
    key: str                       # 场景 key（与 scenes.py 对齐）
    cn: str                        # 中文名
    triggers: tuple[str, ...]      # **正则片段**（不是纯字面量；来自语料实证）
    body: str                      # 注入正文
    # all_required=True → 所有 triggers 必须同时命中（用 lookahead 实现与逻辑）
    all_required: bool = False
    env_prefix: str = ""
    # 本场景该用的口癖（可选）。**必须**来自场景检索实证（tic_by_scene.py 的 lift），
    # 不能凭感觉填；lift < 1.4 或 cell 内不足 5 次的一律不填。
    tics: tuple[str, ...] = ()

    def pattern(self) -> re.Pattern:
        """把 triggers 编译成一个正则。

        ⚠️ triggers 内容是**正则片段**，不能再 `re.escape`——
        否则 `(昨天|上次)` 会被转义成字面量，匹配永远失败。
        （2026-09-11 踩过：与逻辑下两个 lookahead 全部失效，场景静默不触发。）
        """
        if not self.triggers:
            return re.compile(r"(?!)")  # 永不匹配
        if self.all_required and len(self.triggers) > 1:
            expr = "".join(f"(?=.*(?:{t}))" for t in self.triggers) + r"[\s\S]*"
        else:
            expr = "|".join(f"(?:{t})" for t in self.triggers)
        return re.compile(expr, re.IGNORECASE)

    def render(self) -> str:
        """实际注入的文本：正文 +（可选）本场景口癖提示。"""
        if not self.tics:
            return self.body
        hint = "、".join(f"「{t}」" for t in self.tics)
        return self.body + f"\n  口癖（自然带出、不要硬塞）：{hint}"


_lock = threading.Lock()
_fired: dict[str, set[str]] = {}          # session -> {scene_key}


# ── 反照抄脚注（深模块统一追加）────────────────────────────────────────
# 依据：2026-09-12 真实探针发现「模块里的正例被逐字复制」——
#   `rana.cat_talk` 6 条回复里 5 条完全相同（都等于模块正例），
#   `soyo.wind_ensemble` 6 条里 4 条都带同一句正例。
# 正例是给人的语义锚、不是给模型的台词库；照抄会直接退化成复读。
NO_LITERAL_COPY = "  · 上面的「正例」只示**形态**：按本轮情境自己造句，不要照抄示例字面。"


def _normalize_session(session_id: Optional[str]) -> str:
    sid = str(session_id or "").strip()
    return sid or "__shared__"


def _mark_fired(session_id: Optional[str], key: str) -> bool:
    """标记已注入；返回 True 表示**本次之前已注入过**（即应当跳过）。"""
    sid = _normalize_session(session_id)
    with _lock:
        bucket = _fired.setdefault(sid, set())
        if key in bucket:
            return True
        bucket.add(key)
        return False


def reset_session(session_id: Optional[str] = None) -> None:
    """清空去重状态（测试与诊断用）。"""
    sid = _normalize_session(session_id)
    with _lock:
        if session_id is None:
            _fired.clear()
        else:
            _fired.pop(sid, None)


def _enabled(module: SceneModule) -> bool:
    env = f"{module.env_prefix or 'TURN_LOGIC'}_{module.key.upper()}_ENABLED"
    raw = os.environ.get(env)
    if raw is None:
        return True
    return str(raw).strip() not in ("0", "false", "False", "off", "no", "")


def match_scenes(user_text: str, modules: list[SceneModule]) -> list[SceneModule]:
    """返回本条 user_text 命中的场景模块（不改状态，供诊断/测试用）。"""
    if not user_text:
        return []
    return [m for m in modules if m.pattern().search(user_text)]


def build_scene_blocks(
    user_text: str,
    modules: list[SceneModule],
    *,
    session_id: Optional[str] = None,
    max_blocks: int = 2,
) -> list[str]:
    """按命中场景产出 block 文本。

    max_blocks：一轮最多注入几个场景，避免多个场景叠加把 prompt 撑爆
      （场景词表有重叠，例如「雨」同时属 rana_cat 与 rana_guitar）。
    """
    if not user_text:
        return []
    blocks: list[str] = []
    for module in modules:
        if len(blocks) >= max_blocks:
            break
        if not _enabled(module):
            continue
        if not module.pattern().search(user_text):
            continue
        if _mark_fired(session_id, module.key):
            continue
        blocks.append(module.render())
    return blocks
