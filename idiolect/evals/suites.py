"""内置 suite / 回放 / 快照样例的注册与加载（随 wheel 发布的 package data）。

名字解析规则：存在的文件路径优先；否则按内置名查 `idiolect/benchmarks/`。
`long-context-plan/v1` 文件会被确定性展开成 suite（见 `longctx.generate_suite`）。
回放写作 `builtin:<suite>.<policy>`；长上下文回放由期望现场生成（合成，只测链路）。
"""
from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any, Mapping

from .longctx import PLAN_SCHEMA, generate_suite, synthetic_replay
from .pipeline import ResponseSet, load_response_set
from .tasks import Suite, canonical_sha256, parse_suite

BUILTIN_SUITES = {
    "language-only": "language-only.json",
    "spatiotemporal-core": "spatiotemporal-core.json",
    "mygo-five-showcase": "mygo-five-showcase.json",
    "long-context-smoke": "long-context-smoke.plan.json",
}
BUILTIN_REPLAYS = {
    "language-only.healthy": "language-only.replay.healthy.json",
    "spatiotemporal-core.healthy": "spatiotemporal-core.replay.healthy.json",
    "spatiotemporal-core.defects": "spatiotemporal-core.replay.defects.json",
    "mygo-five-showcase.healthy": "mygo-five-showcase.replay.healthy.json",
    "long-context-smoke.healthy": None,
    "long-context-smoke.lost_middle": None,
    "long-context-smoke.failure_controls": None,
}
BUILTIN_EXAMPLES = {"snapshot.example": "snapshot.example.json"}


def _read_builtin(filename: str) -> Any:
    ref = resources.files("idiolect.benchmarks").joinpath(filename)
    return json.loads(ref.read_text(encoding="utf-8"))


def read_json_source(spec: str) -> Any:
    """文件路径或内置名 → JSON。"""
    path = Path(spec)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    name = spec.removeprefix("builtin:")
    for table in (BUILTIN_SUITES, BUILTIN_REPLAYS, BUILTIN_EXAMPLES):
        if name in table and table[name]:
            return _read_builtin(table[name])
    raise FileNotFoundError(f"找不到 {spec!r}：既不是文件，也不是内置名（见 `idiolect bench list`）")


def suite_source(spec: str) -> dict:
    """返回 suite 的原始字典（plan 会先展开）。"""
    raw = read_json_source(spec)
    if isinstance(raw, Mapping) and raw.get("schema_version") == PLAN_SCHEMA:
        return generate_suite(raw)
    return raw


def load_suite(spec: str) -> Suite:
    """按文件路径或内置名加载并严格解析 suite。"""
    return parse_suite(suite_source(spec))


def load_responses(spec: str, suite: Suite) -> ResponseSet:
    """`builtin:<suite>.<policy>` 或文件路径 → ResponseSet。"""
    name = spec.removeprefix("builtin:")
    if spec.startswith("builtin:") and name in BUILTIN_REPLAYS and BUILTIN_REPLAYS[name] is None:
        policy = name.split(".", 1)[1]
        raw = synthetic_replay(suite.raw, policy)
    else:
        # 手写回放登记了生成时的 suite 指纹；suite 改了而回放没重录，完整性检查会 fail closed
        raw = read_json_source(spec)
    return load_response_set(raw)


def list_builtins() -> dict:
    """列出内置 suite、回放与样例的名字。"""
    return {"suites": sorted(BUILTIN_SUITES), "replays": sorted(BUILTIN_REPLAYS),
            "examples": sorted(BUILTIN_EXAMPLES)}


def builtin_sha256(name: str) -> str:
    """内置数据的规范化指纹。"""
    return canonical_sha256(read_json_source(name))


__all__ = ["BUILTIN_EXAMPLES", "BUILTIN_REPLAYS", "BUILTIN_SUITES", "builtin_sha256", "list_builtins",
           "load_responses", "load_suite", "read_json_source", "suite_source"]
