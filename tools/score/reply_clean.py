"""出站清洗（评分前必须做，否则指标口径与清洗规则不一致）。

依赖说明：注释里提到的 `response_contract.*` 是一个**可选**的统一出站管线包。
本仓库不带它，所以下面那些 `try-import` 都会失败、走本地 fallback——这是**预期**
路径，不是缺陷。运行环境如果提供了 `response_contract`，那些 import 会自动生效、
评分口径与该管线一致（这样设计是为了让两处清洗规则不会各自漂移）。

依据：
  - `[sticker:xxx]` 是表情指令，按出站约定会被剥离、**不进正文** → 评分前必须去掉，
    否则虚增长度。
  - `[motion:xxx]` 是合法动作标签（格式约定明确允许），
    保留在正文里，但单独统计出现率（每 2-3 句最多一个）。
  - `[青空]：xxx` 这类说话人回显、`<think>...</think>`、`（心想：...）` 都属于**泄漏**，
    不是正常正文——单独记为 leak，不计入风格分布，避免污染长度/标点指标。
"""
from __future__ import annotations

# ── idiolect 路径引导：仓库根 + 各 tools 子目录上 sys.path ──
import sys as _sys
from pathlib import Path as _Path
_ROOT = _Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "tools",
           *(_ROOT / "tools" / _d for _d in ("corpus", "distill", "probe", "score", "gates"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))
from _paths import CORPUS_DIR, DATA, REPORT, ROOT  # noqa: E402,F401

import re
import sys
from pathlib import Path

# 本模块的多处清洗都靠 try-import `response_contract.*`（可选管线）实现。
# ⚠️ 2026-09-12 踩过：仓库根不在 sys.path 上时那些 import **静默失败**、走 fallback，
# 于是本地正则与管线逐渐漂移（think 标签实测 15 条泄漏一条没清）。
# 这里显式把仓库根加进来，让「能复用管线就复用」真的生效。
_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

RX_STICKER = re.compile(r"\[sticker:[^\]\n]*\]", re.IGNORECASE)
RX_MOTION = re.compile(r"\[motion:([^\]\n]+)\]", re.IGNORECASE)
RX_THINK_TAG = re.compile(r"</?think>", re.IGNORECASE)
RX_SPEAKER_ECHO = re.compile(r"^\s*\[[^\]\n]{1,12}\]\s*[:：]")
RX_INNER_MONOLOGUE = re.compile(r"[（(]\s*心想[:：][^)）]*[)）]")
RX_BRACKET_ACTION_CN = re.compile(r"[（(](?:放下笔|看着屏幕|转头看窗外|顿了一下|停顿了一下)[^)）]{0,20}[)）]")


def normalize_nicknames(char: str, text: str) -> str:
    """按出站规则归一化角色称呼，使「实际输出」与「金标准台词」可以同口径比较。

    管线的 `response_contract.sanitization._enforce_dialogue_nickname_policy` 会把
    爱音说的「素世/立希/灯」改写成「soyorin/rikki/灯灯」，灯说「爱音」→「小爱」等。
    金标准台词没有这层改写，若不归一化，词级 log-odds / 锚点密度会系统性地偏向
    某一方（实测：探针里爱音合法地叫「rikki」，而金标准里写「立希」）。

    优先直接复用管线实现（保证同源）；导入失败时退化为等价的最小映射。
    """
    if not text:
        return text
    try:
        from response_contract.sanitization import _enforce_dialogue_nickname_policy

        return _enforce_dialogue_nickname_policy(char, text)
    except Exception:  # noqa: BLE001 - 可选管线缺失属预期，走本地 fallback
        if char == "爱音":
            return (text.replace("长崎素世", "soyorin").replace("素世", "soyorin")
                        .replace("椎名立希", "rikki").replace("立希", "rikki")
                        .replace("高松灯", "灯灯").replace("灯", "灯灯"))
        if char == "灯":
            return (text.replace("小爱音", "爱音").replace("小爱", "爱音").replace("爱音", "小爱")
                        .replace("小素世", "素世").replace("素世", "小素世")
                        .replace("小立希", "立希").replace("立希", "小立希")
                        .replace("小乐奈", "乐奈").replace("乐奈", "小乐奈"))
        return (text.replace("灯灯", "灯").replace("小爱音", "爱音").replace("小爱", "爱音")
                    .replace("soyorin", "素世").replace("rikki", "立希"))


def clean_reply(text: str) -> tuple[str, dict]:
    """返回 (用于评分的正文, 结构信息)。"""
    if not text:
        return "", {"sticker": 0, "motion": 0, "leak": 0, "leak_kinds": []}
    info = {"sticker": 0, "motion": 0, "leak": 0, "leak_kinds": []}
    t = text

    info["sticker"] = len(RX_STICKER.findall(t))
    t = RX_STICKER.sub(" ", t)

    motions = RX_MOTION.findall(t)
    info["motion"] = len(motions)
    t = RX_MOTION.sub(" ", t)

    if RX_THINK_TAG.search(t):
        info["leak"] += 1
        info["leak_kinds"].append("think_tag")
        t = RX_THINK_TAG.sub(" ", t)

    # 2026-09-12：上面这条本地正则**匹配不到** `[thinking]` / `</thinking>` / `[think]`——
    # 实测 15 条泄漏样本里它一条都没清掉。评分口径必须与管线一致（本模块 docstring 的承诺），
    # 所以管线可用时直接调用管线实现，而不是自己维护一份会漂移的正则。
    try:
        from response_contract.sanitization import strip_model_thinking_text
        _stripped, _thoughts = strip_model_thinking_text(t)
        if _thoughts or _stripped != t:
            if _thoughts:
                info["leak"] += 1
                info["leak_kinds"].append("thinking_block")
            t = _stripped
    except Exception:  # noqa: BLE001 - 可选管线缺失属预期，走本地 fallback
        pass

    if RX_INNER_MONOLOGUE.search(t):
        info["leak"] += 1
        info["leak_kinds"].append("inner_monologue")
        t = RX_INNER_MONOLOGUE.sub(" ", t)

    # 说话人回显（[青空]：...）——按行处理
    lines = []
    for line in t.split("\n"):
        if RX_SPEAKER_ECHO.match(line):
            info["leak"] += 1
            info["leak_kinds"].append("speaker_echo")
            line = RX_SPEAKER_ECHO.sub("", line)
        lines.append(line)
    t = "\n".join(lines)

    # 中文括号动作旁白（出站规约明文禁止）
    if RX_BRACKET_ACTION_CN.search(t):
        info["leak"] += 1
        info["leak_kinds"].append("cn_action_narration")
        t = RX_BRACKET_ACTION_CN.sub(" ", t)

    # 2026-09-12：本地这几条只能清一部分。管线的完整清洗链要接上——
    #   `sanitize_memory_fence` 清 `<part index>` / memory-context 类围栏回显；
    #   `_sanitize_no_markdown` 清 markdown + DSML/工具标签 + 舞台旁白（内部会调
    #   `_strip_stage_action_aside`，所以这里不必再单独调一次）。
    # 不接的话探针指标比管线松：实测 `<part>` 类在 probe 数据里残留、长度被抬高。
    try:
        from response_contract.sanitization import sanitize_memory_fence, _sanitize_no_markdown
        _after_fence = sanitize_memory_fence(t)
        if _after_fence != t:
            info["leak"] += 1
            info["leak_kinds"].append("memory_fence")
            t = _after_fence
        _after_all = _sanitize_no_markdown(t)
        if _after_all != t:
            info["leak"] += 1
            info["leak_kinds"].append("stage_action_aside")
            t = _after_all
    except Exception:  # noqa: BLE001 - 可选管线缺失属预期，走本地 fallback
        pass

    t = re.sub(r"[ \t]+", " ", t).strip()
    t = re.sub(r"\n{2,}", "\n", t)
    return t, info
