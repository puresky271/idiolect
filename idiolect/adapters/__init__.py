"""证据上下文 adapter：把调用方显式交来的材料投影成 `evidence-context/v1`。

adapter 只做三件事：校验来源声明（脱敏、权限、观察者）、按可见性过滤、映射成合同。
它**不**打开数据库、不读聊天历史、不启动服务、不推断 current/history——这些属于
上游宿主系统（它的世界状态、记忆与设定库是各自的唯一真相来源）。
"""
from __future__ import annotations

from .explicit_snapshot import (
    SNAPSHOT_SCHEMA,
    AdapterResult,
    ContractPassthroughAdapter,
    EvidenceContextAdapter,
    ExplicitSnapshotAdapter,
    get_adapter,
)

__all__ = [
    "SNAPSHOT_SCHEMA", "AdapterResult", "ContractPassthroughAdapter",
    "EvidenceContextAdapter", "ExplicitSnapshotAdapter", "get_adapter",
]
