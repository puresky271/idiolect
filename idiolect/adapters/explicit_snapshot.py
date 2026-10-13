"""显式快照 adapter：消费调用方导出的、已脱敏且带权限声明的 snapshot。

典型来源是宿主聊天系统的导出：宿主自己决定 current/history/unknown
（时间与空间判断属于宿主的世界状态），把结果连同脱敏与权限声明一起写成
`explicit-snapshot/v1` 交过来。adapter 的边界：

  · 只接收内存里的 mapping（CLI 读的也是调用方显式给出的文件路径），不自动打开
    生产 SQLite、ledger、聊天历史或密钥；
  · `redaction.applied` 不是 true 就拒收；没有 `permissions.observer_id` /
    `declared_by` 就拒收；顶层出现评估侧或生产状态字段（oracle / gold / ledger …）
    就拒收；
  · 每条记录的 `status` 必须由上游给出——adapter 不从时间戳推导，缺了就报
    `status_not_projected`，不补默认值；
  · 对观察者不可见、或不在授权场景范围内的记录直接丢弃，只在报告里留 ID 与原因，
    正文不进任何输出。

输出是严格校验过的 `TemporalEvidenceContext`，与手写的 v1 合同走同一条下游链路。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

from ..evidence_contract import (
    EVIDENCE_CONTEXT_SCHEMA,
    EVIDENCE_STATUSES,
    ContractError,
    ContractIssue,
    TemporalEvidenceContext,
    ValidationReport,
    is_private_value,
    parse_evidence_context,
    validate_evidence_context,
)

SNAPSHOT_SCHEMA = "explicit-snapshot/v1"
_SNAPSHOT_KEYS = {"schema_version", "snapshot_id", "producer", "exported_at", "as_of",
                  "scene_id", "redaction", "permissions", "records"}
_RECORD_KEYS = {"record_id", "status", "text", "observed_at", "valid_until", "scene_id",
                "modality", "locator", "visible_to", "supersedes", "provenance"}
# 顶层出现这些字段说明导出物混入了评估侧真值或生产状态，整份拒收。
_REFUSED_TOP_LEVEL = ("oracle", "gold", "expected", "answers", "world_state", "ledger",
                      "sqlite", "secrets", "api_key", "chat_history", "memory_db")


def _sha256(value: Any) -> str:
    blob = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AdapterResult:
    """adapter 的产出：合同对象 + 校验报告 + 被丢弃记录（只有 ID 与原因）。"""

    context: TemporalEvidenceContext | None
    report: ValidationReport
    adapter: str
    adapter_version: str
    input_sha256: str
    dropped: tuple[dict, ...] = ()
    source: Mapping[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.context is not None and self.report.ok

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter": self.adapter, "adapter_version": self.adapter_version,
            "input_sha256": self.input_sha256, "ok": self.ok,
            "report": self.report.to_dict(), "dropped": list(self.dropped),
            "source": dict(self.source),
            "context": self.context.to_contract() if self.ok else None,
        }


class EvidenceContextAdapter(Protocol):
    """adapter 插件接口：名字与版本进 manifest，`to_context` 不得有副作用。"""

    name: str
    version: str

    def to_context(self, payload: Mapping[str, Any] | None) -> AdapterResult: ...


class ContractPassthroughAdapter:
    """默认 adapter：输入本身就是 `evidence-context/v1`，严格校验后原样投影。"""

    name = "contract-passthrough"
    version = "1.0"

    def to_context(self, payload: Mapping[str, Any] | None) -> AdapterResult:
        sha = _sha256(payload)
        if payload is None:
            report = ValidationReport(EVIDENCE_CONTEXT_SCHEMA, (
                ContractIssue("missing_input", "$", "没有证据上下文"),))
            return AdapterResult(None, report, self.name, self.version, sha)
        report = validate_evidence_context(payload)
        context = parse_evidence_context(payload) if report.ok else None
        return AdapterResult(context, report, self.name, self.version, sha)


class ExplicitSnapshotAdapter:
    """`explicit-snapshot/v1` → `evidence-context/v1`。规则见模块 docstring。"""

    name = "explicit-snapshot"
    version = "1.0"

    def to_context(self, payload: Mapping[str, Any] | None) -> AdapterResult:
        sha = _sha256(payload)
        issues: list[ContractIssue] = []

        def err(code: str, path: str, msg: str) -> None:
            issues.append(ContractIssue(code, path, msg))

        if not isinstance(payload, Mapping):
            err("type_error", "$", "snapshot 必须是对象")
            return self._fail(issues, sha)
        if payload.get("schema_version") != SNAPSHOT_SCHEMA:
            err("schema_unknown", "$.schema_version",
                f"需要 {SNAPSHOT_SCHEMA!r}，收到 {payload.get('schema_version')!r}")
            return self._fail(issues, sha)
        for key in payload:
            if any(bad in key.lower() for bad in _REFUSED_TOP_LEVEL):
                err("evaluator_or_production_payload", f"$.{key}",
                    f"顶层字段 {key!r} 属于评估侧真值或生产状态，整份拒收")
            elif key not in _SNAPSHOT_KEYS:
                err("unknown_field", f"$.{key}", f"未知字段 {key!r}")
        redaction = payload.get("redaction")
        if not isinstance(redaction, Mapping) or redaction.get("applied") is not True:
            err("not_redacted", "$.redaction.applied", "快照未声明已脱敏（redaction.applied 必须为 true）")
        perms = payload.get("permissions")
        observer = None
        scopes: list[str] = []
        if not isinstance(perms, Mapping):
            err("permissions_missing", "$.permissions", "缺少权限声明")
        else:
            observer = perms.get("observer_id")
            if not isinstance(observer, str) or not observer:
                err("permissions_missing", "$.permissions.observer_id", "缺少观察者 ID")
            if not isinstance(perms.get("declared_by"), str) or not perms.get("declared_by"):
                err("permissions_missing", "$.permissions.declared_by", "缺少权限声明者")
            raw_scopes = perms.get("scopes", [])
            if not isinstance(raw_scopes, list) or not all(isinstance(s, str) for s in raw_scopes):
                err("type_error", "$.permissions.scopes", "scopes 必须是字符串列表")
            else:
                scopes = list(raw_scopes)
        records = payload.get("records")
        if not isinstance(records, list):
            err("type_error", "$.records", "records 必须是列表")
            records = []
        if issues:
            return self._fail(issues, sha)

        buckets: dict[str, list[dict]] = {s: [] for s in EVIDENCE_STATUSES}
        dropped: list[dict] = []
        for idx, rec in enumerate(records):
            path = f"$.records[{idx}]"
            if not isinstance(rec, Mapping):
                err("type_error", path, "记录必须是对象")
                continue
            for key in rec:
                if key not in _RECORD_KEYS:
                    err("unknown_field", f"{path}.{key}", f"未知字段 {key!r}")
            rid = rec.get("record_id")
            status = rec.get("status")
            if status in (None, ""):
                err("status_not_projected", f"{path}.status",
                    "status 必须由上游投影给出；adapter 不从时间戳推导 current/history")
                continue
            visible = rec.get("visible_to") or []
            if visible and observer not in visible:
                dropped.append({"record_id": rid, "reason": "not_visible_to_observer"})
                continue
            if scopes and rec.get("scene_id") and rec.get("scene_id") not in scopes:
                dropped.append({"record_id": rid, "reason": "scene_out_of_scope"})
                continue
            locator = rec.get("locator")
            if locator is not None and is_private_value(locator):
                err("private_locator", f"{path}.locator", "locator 像本机/私有路径；导出前应换成 opaque ID")
                continue
            item: dict[str, Any] = {
                "evidence_id": rid, "status": status, "text": rec.get("text"),
            }
            for src, dst in (("observed_at", "as_of"), ("valid_until", "valid_until"),
                             ("scene_id", "scene_id"), ("modality", "modality"),
                             ("supersedes", "supersedes"), ("visible_to", "visible_to"),
                             ("provenance", "provenance")):
                if rec.get(src) is not None:
                    item[dst] = rec[src]
            if locator:
                item["evidence_refs"] = [locator]
            if status in buckets:
                buckets[status].append(item)
            else:
                buckets.setdefault("current", []).append(item)  # 让合同校验报 status_invalid
        if issues:
            return self._fail(issues, sha, dropped)

        contract: dict[str, Any] = {
            "schema_version": EVIDENCE_CONTEXT_SCHEMA,
            "context_id": payload.get("snapshot_id"),
            "observer_id": observer,
            "as_of": payload.get("as_of"),
            "scene_id": payload.get("scene_id"),
            "permissions": {"declared_by": perms.get("declared_by"),
                            "render_provenance_keys": list(perms.get("render_provenance_keys") or []),
                            "scopes": scopes},
            **buckets,
        }
        report = validate_evidence_context(contract)
        context = parse_evidence_context(contract) if report.ok else None
        producer = payload.get("producer") if isinstance(payload.get("producer"), Mapping) else {}
        source = {"snapshot_id": payload.get("snapshot_id"),
                  "producer": {k: producer.get(k) for k in ("system", "version") if k in producer},
                  "redaction_rules": list((redaction or {}).get("rules") or [])}
        return AdapterResult(context, report, self.name, self.version, sha, tuple(dropped), source)

    def _fail(self, issues: list[ContractIssue], sha: str, dropped=()) -> AdapterResult:
        report = ValidationReport(SNAPSHOT_SCHEMA, tuple(issues))
        return AdapterResult(None, report, self.name, self.version, sha, tuple(dropped))


_ADAPTERS = {
    ContractPassthroughAdapter.name: ContractPassthroughAdapter,
    ExplicitSnapshotAdapter.name: ExplicitSnapshotAdapter,
}


def get_adapter(name: str) -> EvidenceContextAdapter:
    """按名字取 adapter 实例；未知名字直接报错（不会回退到自动读取生产数据）。"""
    try:
        return _ADAPTERS[name]()
    except KeyError:
        raise ValueError(f"未知 adapter {name!r}；可选 {sorted(_ADAPTERS)}") from None


__all__ = [
    "SNAPSHOT_SCHEMA", "AdapterResult", "ContractError", "ContractPassthroughAdapter",
    "EvidenceContextAdapter", "ExplicitSnapshotAdapter", "get_adapter",
]
