"""LLM 思考模式控制补丁（所有入口共用）。

为什么需要：
  · 本仓库的调用走 OpenAI 兼容端点（默认 deepseek-flash）：DeepSeek 系模型默认开启
    thinking，并把原 max_tokens 叠加 reasoning_budget（默认 +1500）再发给 API；
    Qwen 系通常用 enable_thinking=False 关思考。
  · 这个 patch 必须在 import openai client 之前应用、对所有 entry point 都生效。

2026-05-20 root cause: 这个 patch 曾经只挂在某一个入口模块的顶层、**只在该入口
启动时生效**。其他 entry point（后台 thread / offline smoke / 测试脚本等）不会
加载它，那些路径上的 LLM 调用会带着错误的 thinking 默认行为发出，故障隐蔽且难定位。

修复：把 patch 提取到本独立 module、所有可能调 LLM 的入口都在 import openai 之前
`import llm_nothink_patch`。patch 是 idempotent 的（setdefault 不覆盖已设值）、
重复 import 安全。

用法：
  import llm_nothink_patch  # noqa: F401 — side-effect: patches openai client
  from openai import OpenAI
  client = OpenAI(...)
  client.chat.completions.create(model='deepseek-flash', ...)  # 自动注 thinking controls
"""
from __future__ import annotations

# ── idiolect 路径引导：仓库根 + 各 tools 子目录上 sys.path ──
import sys as _sys
from pathlib import Path as _Path
_ROOT = _Path(__file__).resolve().parents[1]
for _p in (_ROOT, _ROOT / "tools",
           *(_ROOT / "tools" / _d for _d in ("corpus", "distill", "probe", "score", "gates"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import os
import sys


_PATCHED = False
_TRUE_VALUES = {"1", "true", "yes", "on", "y", "enabled", "enable"}
_FALSE_VALUES = {"0", "false", "no", "off", "n", "disabled", "disable"}


def _env_flag(name: str, default: bool) -> bool:
    raw = str(os.getenv(name, "") or "").strip().lower()
    if not raw:
        return bool(default)
    if raw in _TRUE_VALUES:
        return True
    if raw in _FALSE_VALUES:
        return False
    return bool(default)


def _env_int(name: str, default: int) -> int:
    try:
        return int(str(os.getenv(name, "") or default).strip())
    except Exception:
        return int(default)


def _deepseek_reasoning_effort() -> str:
    raw = str(os.getenv("DEEPSEEK_REASONING_EFFORT", "high") or "high").strip().lower()
    return raw if raw in {"high", "max"} else "high"


def _inject_reasoning_controls(kwargs):
    """按模型家族注入思考开关。

    Qwen 系默认关思考；DeepSeek 系默认开思考（`DEEPSEEK_THINKING=0` 可关，
    调用方显式传 `extra_body={"thinking": {"type": "disabled"}}` 也可关），
    开思考时在原 max_tokens 上叠加 reasoning_budget。
    """
    model = str(kwargs.get('model', '') or '').lower()
    eb = kwargs.get('extra_body') or {}
    if 'qwen' in model:
        eb.setdefault('enable_thinking', False)
    elif 'deepseek' in model:
        explicit_thinking = eb.get('thinking')
        explicitly_disabled = (
            isinstance(explicit_thinking, dict)
            and str(explicit_thinking.get('type', '') or '').strip().lower() == 'disabled'
        )
        if _env_flag("DEEPSEEK_THINKING", True) and not explicitly_disabled:
            eb.setdefault('thinking', {'type': 'enabled'})
            eb.setdefault('reasoning_effort', _deepseek_reasoning_effort())
            # 2026-06-26: 不再用硬下限把 max_tokens 统一拉到 1600（这会覆盖角色预算、
            # 让思考开启后内容也变长）。改为在原 max_tokens 基础上叠加 reasoning_budget：
            #   max_tokens = original + reasoning_budget（保底 600）
            # 这样思考 token 从叠加部分走，内容 token 仍受角色预算约束。
            # 例：爱音 base=130 → 130+500=630 total，模型用完 ~500 思考后只剩 ~130 写内容。
            reasoning_budget = _env_int("DEEPSEEK_REASONING_BUDGET", 1500)
            if reasoning_budget > 0 and kwargs.get('max_tokens') is not None:
                try:
                    original = int(kwargs.get('max_tokens') or 0)
                    kwargs['max_tokens'] = max(original + reasoning_budget, 600)
                except Exception:
                    pass
        else:
            eb.setdefault('thinking', {'type': 'disabled'})
    else:
        return kwargs
    kwargs['extra_body'] = eb
    return kwargs


def _apply_patch():
    """Patch openai's Completions.create + AsyncCompletions.create class methods."""
    global _PATCHED
    if _PATCHED:
        return
    try:
        import openai.resources.chat.completions as _oai_cc
        _oai_orig_create = _oai_cc.Completions.create

        def _oai_reasoning_patched(self, **kwargs):
            return _oai_orig_create(self, **_inject_reasoning_controls(kwargs))

        _oai_cc.Completions.create = _oai_reasoning_patched

        # Async 版本
        _oai_orig_acreate = _oai_cc.AsyncCompletions.create

        async def _oai_reasoning_apatched(self, **kwargs):
            return await _oai_orig_acreate(self, **_inject_reasoning_controls(kwargs))

        _oai_cc.AsyncCompletions.create = _oai_reasoning_apatched
        _PATCHED = True
    except Exception as _e:
        # openai 未安装或 API 不兼容 — silent skip、不阻断主流程
        print(f'[llm_nothink_patch] skip: {_e}', file=sys.stderr)


# Auto-apply on import（side-effect by design）
_apply_patch()
