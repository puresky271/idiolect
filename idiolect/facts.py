"""角色结构化事实的读取口（本仓库不带事实库，默认空）。

原项目里这些事实由 `character_profiles.MYGO_CHARACTER_FACTS` 拥有。
本仓库只保留蒸馏与注入方法，不含结构化事实，所以默认返回空；
需要时把事实放进 `data/character_facts.json`（`{"爱音": {...}, ...}`）即可。
"""
from __future__ import annotations

import json
from pathlib import Path

_FACTS_PATH = Path(__file__).resolve().parents[1] / "data" / "character_facts.json"


def get_facts(character: str) -> dict:
    try:
        raw = json.loads(_FACTS_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - 文件缺失即视为无事实
        return {}
    value = raw.get(character) if isinstance(raw, dict) else None
    return dict(value) if isinstance(value, dict) else {}
