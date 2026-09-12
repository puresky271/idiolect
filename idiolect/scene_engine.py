"""场景模块共用框架（五个角色包的 turn_logic 共用）。

为什么抽出来：taki / tomori 的每个模块都各自实现「触发正则 + per-session 去重 +
env flag + block 构建」，6 个场景就要抄 6 遍。这里把这层样板抽成一个引擎，
各场景只声明「触发词 + 正文」，减少漂移与维护成本。

2026-09-12 第二轮下沉（评审驱动）：五个角色包的 `__init__.py` 之间还复制着
另外四样东西，也一并收进本模块——
  · `env_enabled` / `ENV_FALSE_VALUES`：env 回退开关的同一张假值表
    （anon/tomori/taki 曾只认 "0"/"false"，soyo/rana 多认 "off"/"no"，两套语义）；
  · `wrap_blocks` / `BLOCK_BORDER`：双线 fence 包装（原先五份逐字相同）；
  · `run_modules`：深模块统一执行器（原先每包一串 try/except 复制体）；
  · `SessionStore`：带 LRU 上限的 session 去重表（原先裸 dict 只增不减、
    常驻进程缓慢漏内存）。

设计约束（对齐既有 turn_logic 约定）：
  · 窄入口：只暴露 `build_scene_block(user_text, scene_key, ...)`
  · 可关闭：env flag `<PREFIX>_TURN_LOGIC_<SCENE>_ENABLED=0`
  · per-session 去重：同一场景在同一 session 内只注入一次，避免每轮复读
  · 状态集中：模块级状态只有 `_fired` 去重表（`SessionStore`，有上限、
    `reset_session()` 可清空），此外不读写任何调用方状态
"""
from __future__ import annotations

import logging
import os
import re
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Callable, Optional

_log = logging.getLogger(__name__)


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


# ── env 回退开关的统一假值表 ─────────────────────────────────────────
# 全仓只有这一份：角色根开关、场景级开关、引擎内部判定都查它。
ENV_FALSE_VALUES = ("0", "false", "False", "off", "no", "")


def env_enabled(raw: str | None) -> bool:
    """env 回退开关判定：未设置 = 启用；命中 `ENV_FALSE_VALUES` = 关闭。"""
    if raw is None:
        return True
    return str(raw).strip() not in ENV_FALSE_VALUES


# ── per-session 去重表（带 LRU 上限）─────────────────────────────────
class SessionStore:
    """session → {key} 的去重表。

    旧实现是裸 `dict[str, set[str]]`、只增不减：常驻进程里 session 不淘汰
    就是缓慢漏内存（2026-09-12 评审抓到）。这里用 OrderedDict 做 LRU：
    mark 即触及提到最新，超过 `max_sessions` 淘汰最久未用的桶。
    """

    def __init__(self, max_sessions: int = 4096) -> None:
        self._max_sessions = max(1, int(max_sessions))
        self._buckets: OrderedDict[str, set[str]] = OrderedDict()
        self._lock = threading.Lock()

    def mark(self, session_id: str, key: str) -> bool:
        """标记已注入；返回 True 表示**本次之前已注入过**（即应当跳过）。"""
        with self._lock:
            bucket = self._buckets.get(session_id)
            if bucket is None:
                bucket = set()
                self._buckets[session_id] = bucket
            self._buckets.move_to_end(session_id)
            while len(self._buckets) > self._max_sessions:
                self._buckets.popitem(last=False)
            if key in bucket:
                return True
            bucket.add(key)
            return False

    def has(self, session_id: str, key: str) -> bool:
        """只读判定：不新增桶、不触及 LRU 顺序（给「先看再决定」的调用方）。"""
        with self._lock:
            return key in self._buckets.get(session_id, ())

    def reset(self, session_id: Optional[str] = None) -> None:
        """清空去重状态（测试与诊断用）；None = 全清。"""
        with self._lock:
            if session_id is None:
                self._buckets.clear()
            else:
                self._buckets.pop(session_id, None)

    def __len__(self) -> int:
        return len(self._buckets)


class SessionValues:
    """session → 值字典 的 LRU 表（SessionStore 的值版兄弟）。

    SessionStore 管「这个 session 注入过哪些块」的集合状态；另一些深模块要
    跨轮的**计数器 / 余波标记**（上一轮触发了什么、这轮是第几轮），那是
    session → 小 dict 的值状态。裸 dict 同样只增不减——与 2026-09-12 抓到的
    _SESSION_FIRED 泄漏是同一类，所以沿用同一套 LRU + 锁 + reset 形状。

    值以**本体**返回（get_or_create / peek / pop），调用方就地改可见——与旧裸
    dict 行为一致；进程内的锁只护表结构，跨线程并发改值由调用方自理。
    """

    def __init__(self, max_sessions: int = 4096) -> None:
        self._max_sessions = max(1, int(max_sessions))
        self._buckets: OrderedDict[str, dict] = OrderedDict()
        self._lock = threading.Lock()

    def get_or_create(self, session_id: str, factory: Callable[[], dict]) -> dict:
        """取 session 的值字典；没有就用 factory 建一个。访问即触及（LRU）。"""
        with self._lock:
            bucket = self._buckets.get(session_id)
            if bucket is None:
                bucket = factory()
            self._buckets[session_id] = bucket
            self._buckets.move_to_end(session_id)
            while len(self._buckets) > self._max_sessions:
                self._buckets.popitem(last=False)
            return bucket

    def put(self, session_id: str, value: dict) -> None:
        """写入 / 覆盖 session 的值字典（余波标记的落点）。"""
        with self._lock:
            self._buckets[session_id] = value
            self._buckets.move_to_end(session_id)
            while len(self._buckets) > self._max_sessions:
                self._buckets.popitem(last=False)

    def peek(self, session_id: str) -> Optional[dict]:
        """只读窥视：不消费、不触及 LRU 顺序、不建桶。"""
        with self._lock:
            return self._buckets.get(session_id)

    def pop(self, session_id: str) -> Optional[dict]:
        """消费：取出并删除；没有返回 None。"""
        with self._lock:
            return self._buckets.pop(session_id, None)

    def reset(self, session_id: Optional[str] = None) -> None:
        """清状态；None = 全清。"""
        with self._lock:
            if session_id is None:
                self._buckets.clear()
            else:
                self._buckets.pop(session_id, None)

    def __len__(self) -> int:
        return len(self._buckets)


_fired = SessionStore()                     # session -> {scene_key}


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
    return _fired.mark(_normalize_session(session_id), key)


def reset_session(session_id: Optional[str] = None) -> None:
    """清空去重状态（测试与诊断用）。"""
    _fired.reset(None if session_id is None else _normalize_session(session_id))


def _enabled(module: SceneModule) -> bool:
    env = f"{module.env_prefix or 'TURN_LOGIC'}_{module.key.upper()}_ENABLED"
    return env_enabled(os.environ.get(env))


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


# ── 共享 block 包装（原五个角色包各抄一份逐字相同的 `_wrap_blocks`）────
BLOCK_BORDER = "═" * 72


def wrap_blocks(blocks: list[str]) -> str:
    """每个 block 加双线上下边界、之间用空行隔开（五角色 turn_logic 共用形态）。"""
    if not blocks:
        return ""
    wrapped = [f"{BLOCK_BORDER}\n{b.rstrip()}\n{BLOCK_BORDER}" for b in blocks if b]
    return "\n\n".join(wrapped)


# ── 深模块统一执行器（消除五个角色包的 try/except 复制体）──────────────
def run_modules(
    modules,
    user_text: str,
    *,
    label: str,
    shared_kwargs: dict,
    per_module_kwargs: dict[str, dict] | None = None,
    needs_text: tuple[str, ...] = (),
    max_blocks: int | None = None,
    literal_copy_note: bool = False,
) -> tuple[list[str], list[str]]:
    """按序跑一组深模块构建器，返回 (blocks, 命中的模块 key)。

    语义与各角色包的手写复制体逐一对齐：
      · 单个模块异常只记日志、不中断，后续模块照跑（错误日志带 `[label/key]`）；
      · `needs_text` 列出的模块在 user_text 为空时跳过（灯的 text-driven 层）；
      · `max_blocks` 封顶产出块数（None = 不封顶：anon/tomori/taki 的既有行为；
        soyo/rana 传 1）——只数**产出了块**的模块，返 "" 的不占额度；
      · `literal_copy_note=True` 时每块末尾追加 `NO_LITERAL_COPY` 脚注
        （soyo/rana 的既有行为；其余三包没有这条，保持不加）。
    """
    out: list[str] = []
    fired: list[str] = []
    skip_if_empty = set(needs_text)
    extras = per_module_kwargs or {}
    for key, builder in modules:
        if max_blocks is not None and len(out) >= max_blocks:
            break
        if key in skip_if_empty and not user_text:
            continue
        try:
            kwargs = dict(shared_kwargs)
            kwargs.update(extras.get(key, {}))
            blk = builder(user_text, **kwargs)
        except Exception as _err:  # 单模块故障不该拖垮整轮装配
            _log.warning("[%s/%s] error: %s", label, key, _err)
            continue
        if blk:
            if literal_copy_note:
                blk = f"{blk.rstrip()}\n{NO_LITERAL_COPY}"
            out.append(blk)
            fired.append(key)
    return out, fired


def lazy_builder(package: str, module: str, func: str):
    """生成延迟 import 的构建器：目标模块坏掉时只禁用这一个子系统。

    anon / tomori / taki 的旧代码把 `from .x import build_x` 放在各子系统的
    try 块里——单模块 import 失败不影响其它子系统。顶层 import 会把整包
    turn_logic 拖死，所以迁移到 `run_modules` 时用本 helper 保住隔离语义
    （import 发生在执行器 try 内，失败只记日志并跳过）。
    """
    def _builder(user_text, **kwargs):
        from importlib import import_module
        return getattr(import_module(f"{package}.{module}"), func)(user_text, **kwargs)
    _builder.__name__ = f"lazy:{module}.{func}"
    return _builder


def uncovered_scenes(modules, fired, overlap_map):
    """深模块与场景层话题重叠时，压制场景层对应块（避免同一话题两块正文）。"""
    covered = {s for k in fired for s in overlap_map.get(k, ())}
    if not covered:
        return modules
    return [m for m in modules if m.key not in covered]


def append_general_scene_blocks(
    blocks: list[str],
    char: str,
    user_text: str,
    *,
    label: str,
    session_id: Optional[str] = None,
    is_developer: bool = False,
    max_blocks: int = 1,
) -> None:
    """把通用场景层（`idiolect.general_scenes`）的块追加进 `blocks`；异常只记日志。

    原先五个角色包的 `__init__.py` 各抄一份完全相同的 try/except，收拢到这里。
    """
    try:
        from idiolect.general_scenes import build_general_scene_blocks
        blocks.extend(build_general_scene_blocks(
            char, user_text, session_id=session_id, max_blocks=max_blocks,
            is_developer=is_developer))
    except Exception as _err:
        _log.warning("[%s/general_scenes] error: %s", label, _err)
