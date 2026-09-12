"""角色包注册表：把「角色名」解析成具体角色包，再分发到它的窄入口。

对应原项目 `character_role_packages.py`，去掉项目专属的 `character_profile_runtime`
依赖（名称归一化改为本地实现）。

调用方只依赖本模块的这几个函数，不要按角色名堆 if/elif，
也不要直接 import `idiolect.characters.<key>.*`。
"""
from __future__ import annotations

from importlib import import_module
from typing import Any

# canonical 名 → 角色包 api 模块
_PACKAGE_NAMES = {
    "爱音": "idiolect.characters.anon.api",
    "灯": "idiolect.characters.tomori.api",
    "立希": "idiolect.characters.taki.api",
    "素世": "idiolect.characters.soyo.api",
    "乐奈": "idiolect.characters.rana.api",
}

# 别名 → canonical 名（含罗马字、日文、常见误写）
_ALIASES = {
    "anon": "爱音", "千早爱音": "爱音", "あのん": "爱音", "Anon": "爱音",
    "tomori": "灯", "高松灯": "灯", "ともり": "灯", "Tomori": "灯",
    "taki": "立希", "椎名立希": "立希", "りき": "立希", "Taki": "立希",
    "rikki": "立希", "Rikki": "立希", "りっきー": "立希",
    "soyo": "素世", "爽世": "素世", "長崎そよ": "素世", "长崎素世": "素世", "Soyo": "素世",
    "rana": "乐奈", "楽奈": "乐奈", "要楽奈": "乐奈", "要乐奈": "乐奈", "Rana": "乐奈",
}


def canonicalize_name(character: str) -> str:
    """角色名 → canonical 中文名；无法识别返回 ""。"""
    raw = str(character or "").strip()
    if raw in _PACKAGE_NAMES:
        return raw
    return _ALIASES.get(raw, _ALIASES.get(raw.lower(), ""))


def get_role_package(character: str):
    """返回角色包 api 模块；未知角色返回 None。"""
    name = canonicalize_name(character)
    module_name = _PACKAGE_NAMES.get(name)
    return import_module(module_name) if module_name else None


def render_turn_special_block(character: str, user_text: str, **kwargs: Any) -> str:
    """本轮 turn_logic 拼装。

    这是**唯一**的动态 prompt 入口：命中场景/主题时返回该注入的文本，否则返回 ""。
    """
    package = get_role_package(character)
    if package is None:
        return ""
    renderer = getattr(package, "render_supplemental_blocks", None)
    if renderer is None:
        return ""
    context = dict(kwargs.pop("context", None) or {})
    now = kwargs.pop("now", kwargs.pop("now_jst", None))
    scene_context = kwargs.pop("scene_context", None)
    if isinstance(scene_context, dict):
        context.update(scene_context)
    for key in ("session_id", "is_developer", "ledger", "mode"):
        if key in kwargs:
            context[key] = kwargs.pop(key)
    return str(renderer(character=character, last_user_text=user_text,
                        context=context, now=now) or "")


def get_voice_manifest(character: str) -> str:
    package = get_role_package(character)
    getter = getattr(package, "get_voice_manifest", None) if package else None
    return str(getter() if getter else "")


def get_canon_profile(character: str) -> str:
    package = get_role_package(character)
    getter = getattr(package, "get_canon_profile", None) if package else None
    return str(getter() if getter else "")


def get_canon_facts(character: str) -> dict:
    package = get_role_package(character)
    getter = getattr(package, "get_canon_facts", None) if package else None
    result = getter() if getter else {}
    return dict(result) if isinstance(result, dict) else {}


def postprocess_reply(character: str, reply_text: str, history: list | None = None) -> dict:
    """出站后处理（每个角色包自己实现；未实现的角色原样返回）。"""
    package = get_role_package(character)
    processor = getattr(package, "postprocess_reply", None) if package else None
    if processor is None:
        return {"text": str(reply_text or ""), "violations": [], "ok": True, "skipped": True}
    result = processor(character=character, reply_text=reply_text, history=history)
    if not isinstance(result, dict):
        return {"text": str(reply_text or ""), "violations": [], "ok": True, "skipped": True}
    result.setdefault("text", str(reply_text or ""))
    return result


__all__ = [
    "canonicalize_name", "get_canon_facts", "get_canon_profile", "get_role_package",
    "get_voice_manifest", "postprocess_reply", "render_turn_special_block",
]
