"""可预注册的评测任务 schema（`benchmark-suite/v1`）与结构校验。

一个 suite = 一组任务 + 预注册信息 + 独立的标签来源声明。任务分三块：

  · **模型可见输入**：`user`、`history`、`blocks`、`execution_packet`、
    `evidence_context`（`evidence-context/v1`）、`assembly`（预算等装配参数）；
  · **评估侧期望** `expect`：要求出现的主张、禁止出现的主张、是否必须拒答/纠正/
    引用/带时间限定、证据是否应可见；
  · **评估侧 Oracle** `oracle`：隐藏真值、禁止泄漏的值、备注。

`expect` 与 `oracle` 永远不进 messages——prompt 边界检查会扫最终 messages，确认
这些值没有混进去。期望由任务作者**先于回复**写定（`label_source.independent_of_responses`），
评分侧不从被测回复反推 gold。

任务类型（`TASK_KINDS`）与它们检验的风险：

  current_fact         当前事实能否直接回答
  history_qualified    历史事实保留，且带时间限定
  unknown_abstain      未知：不编造、也不说成已被否定
  false_premise        错误前提要纠正，不能照单接受
  citation             要求引用时，引用是否存在、可见、支撑主张
  invisible_isolation  对方历史 / 其他场景的不可见信息不得出现
  stale_as_current     过期历史不得冒充当前
  conflict_correction  冲突与更正：以更正后的记录为准
  budget_trim          证据被预算摘除后：期望改为不编造，装配缺失单独记账
  private_metadata     评估元数据、私有 provenance 不得进 messages
  style_only           只评风格（默认语言工作流，不需要任何时空 schema）
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping

from ..evidence_contract import ContractIssue, ValidationReport

SUITE_SCHEMA = "benchmark-suite/v1"
TASK_KINDS = (
    "current_fact", "history_qualified", "unknown_abstain", "false_premise", "citation",
    "invisible_isolation", "stale_as_current", "conflict_correction", "budget_trim",
    "private_metadata", "style_only",
)
POLICIES = ("answer_current", "answer_history_qualified", "abstain", "correct_premise",
            "withhold_invisible", "use_latest", "style_only")
FORBIDDEN_REASONS = ("history_as_current", "superseded_as_current", "premise_accepted",
                     "unknown_affirmed", "unknown_denied", "invisible_leak", "fabricated")
_TASK_KEYS = {"task_id", "family_id", "kind", "capabilities", "actor", "user", "history",
              "blocks", "execution_packet", "evidence_context", "assembly", "expect", "oracle",
              "long_context", "arm", "note"}
_EXPECT_KEYS = {"policy", "required_claims", "forbidden_claims", "citation", "abstain_required",
                "correction_required", "history_qualifier_required", "evidence_expected_visible"}
_SUITE_KEYS = {"schema_version", "suite_id", "suite_version", "description", "preregistration",
               "label_source", "capabilities", "tasks", "generated_from", "note"}


def canonical_sha256(value: Any) -> str:
    """JSON 值的规范化指纹（键排序、紧凑分隔符）。"""
    blob = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Claim:
    """一条可机械匹配的主张：写法列表、来源证据、期望时态与放行条件。"""
    claim_id: str
    any_of: tuple[str, ...]
    evidence_id: str | None = None
    expected_status: str | None = None
    reason: str = ""
    allow_if_qualified: bool = False
    allow_if_negated: bool = True

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "Claim":
        return cls(
            claim_id=str(raw.get("claim_id", "")),
            any_of=tuple(str(x) for x in raw.get("any_of", ()) or ()),
            evidence_id=raw.get("evidence_id"),
            expected_status=raw.get("expected_status"),
            reason=str(raw.get("reason", "") or ""),
            allow_if_qualified=bool(raw.get("allow_if_qualified", False)),
            allow_if_negated=bool(raw.get("allow_if_negated", True)),
        )


@dataclass(frozen=True)
class Expectation:
    """评估侧期望：要求/禁止的主张、拒答、纠正、引用与时间限定要求。"""
    policy: str
    required_claims: tuple[Claim, ...] = ()
    forbidden_claims: tuple[Claim, ...] = ()
    citation_required: bool = False
    must_cite: tuple[str, ...] = ()
    abstain_required: bool = False
    correction_required: bool = False
    history_qualifier_required: bool = False
    evidence_expected_visible: bool = True

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "Expectation":
        citation = raw.get("citation") or {}
        return cls(
            policy=str(raw.get("policy", "")),
            required_claims=tuple(Claim.from_dict(c) for c in raw.get("required_claims", ()) or ()),
            forbidden_claims=tuple(Claim.from_dict(c) for c in raw.get("forbidden_claims", ()) or ()),
            citation_required=bool(citation.get("required", False)),
            must_cite=tuple(citation.get("must_cite", ()) or ()),
            abstain_required=bool(raw.get("abstain_required", False)),
            correction_required=bool(raw.get("correction_required", False)),
            history_qualifier_required=bool(raw.get("history_qualifier_required", False)),
            evidence_expected_visible=bool(raw.get("evidence_expected_visible", True)),
        )


@dataclass(frozen=True)
class GroundingTask:
    """一个评测任务：模型可见输入 + 评估侧期望 + evaluator-only oracle。"""
    task_id: str
    family_id: str
    kind: str
    capabilities: tuple[str, ...]
    actor: str
    user: str
    expect: Expectation
    evidence_context: Mapping[str, Any] | None = None
    history: tuple[Mapping[str, str], ...] = ()
    blocks: tuple[tuple[str, str], ...] = ()
    execution_packet: str = ""
    assembly: Mapping[str, Any] = field(default_factory=dict)
    oracle: Mapping[str, Any] = field(default_factory=dict)
    long_context: Mapping[str, Any] | None = None
    arm: str | None = None
    raw: Mapping[str, Any] = field(default_factory=dict, compare=False, repr=False)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "GroundingTask":
        return cls(
            task_id=str(raw.get("task_id", "")),
            family_id=str(raw.get("family_id", "") or raw.get("task_id", "")),
            kind=str(raw.get("kind", "")),
            capabilities=tuple(raw.get("capabilities", ()) or ()),
            actor=str(raw.get("actor", "")),
            user=str(raw.get("user", "")),
            expect=Expectation.from_dict(raw.get("expect") or {}),
            evidence_context=raw.get("evidence_context"),
            history=tuple(dict(m) for m in raw.get("history", ()) or ()),
            blocks=tuple((str(k), str(v)) for k, v in raw.get("blocks", ()) or ()),
            execution_packet=str(raw.get("execution_packet", "") or ""),
            assembly=dict(raw.get("assembly") or {}),
            oracle=dict(raw.get("oracle") or {}),
            long_context=raw.get("long_context"),
            arm=raw.get("arm"),
            raw=dict(raw),
        )

    def hidden_values(self) -> list[str]:
        """评估侧禁止进入 messages 的值：oracle.hidden_values + invisible_leak 类主张。"""
        values = [str(v) for v in self.oracle.get("hidden_values", ()) or ()]
        for claim in self.expect.forbidden_claims:
            if claim.reason == "invisible_leak":
                values.extend(claim.any_of)
        return list(dict.fromkeys(v for v in values if v))

    def actor_for_prompt(self) -> str:
        """装配用的角色名：认识的角色给 canonical 名，opaque actor 原样返回（persona 为空）。"""
        from ..registry import canonicalize_name

        return canonicalize_name(self.actor) or self.actor

    def is_character(self) -> bool:
        from ..registry import canonicalize_name

        return bool(canonicalize_name(self.actor))


@dataclass(frozen=True)
class Suite:
    """严格解析后的 suite：任务、预注册信息、标签来源与内容指纹。"""
    suite_id: str
    suite_version: str
    tasks: tuple[GroundingTask, ...]
    capabilities: tuple[str, ...]
    preregistration: Mapping[str, Any]
    label_source: Mapping[str, Any]
    sha256: str
    raw: Mapping[str, Any] = field(default_factory=dict, compare=False, repr=False)

    @property
    def families(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(t.family_id for t in self.tasks))

    def task(self, task_id: str) -> GroundingTask:
        for t in self.tasks:
            if t.task_id == task_id:
                return t
        raise KeyError(task_id)


def validate_suite(raw: Any, *, known_capabilities: tuple[str, ...] | None = None) -> ValidationReport:
    """结构校验：schema、ID、任务类型、期望与证据的一致性、Oracle 不得出现在可见输入里。"""
    from ..evidence_contract import find_forbidden_values, validate_evidence_context
    from ..capabilities import CAPABILITIES

    known = known_capabilities or tuple(CAPABILITIES)
    issues: list[ContractIssue] = []

    def err(code: str, path: str, msg: str, severity: str = "error") -> None:
        issues.append(ContractIssue(code, path, msg, severity))

    if not isinstance(raw, Mapping):
        return ValidationReport(SUITE_SCHEMA, (ContractIssue("type_error", "$", "suite 必须是对象"),))
    if raw.get("schema_version") != SUITE_SCHEMA:
        err("schema_unknown", "$.schema_version", f"需要 {SUITE_SCHEMA!r}，收到 {raw.get('schema_version')!r}")
        return ValidationReport(SUITE_SCHEMA, tuple(issues))
    for key in raw:
        if key not in _SUITE_KEYS:
            err("unknown_field", f"$.{key}", f"未知字段 {key!r}")
    for key in ("suite_id", "suite_version"):
        if not isinstance(raw.get(key), str) or not raw.get(key):
            err("missing_field", f"$.{key}", f"缺少 {key}")
    label = raw.get("label_source")
    if not isinstance(label, Mapping) or label.get("independent_of_responses") is not True:
        err("label_source", "$.label_source",
            "必须声明 label_source.independent_of_responses = true（期望先于回复写定）")
    tasks = raw.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        err("missing_field", "$.tasks", "suite 至少要有一个任务")
        return ValidationReport(SUITE_SCHEMA, tuple(issues))
    seen: set[str] = set()
    for idx, task in enumerate(tasks):
        path = f"$.tasks[{idx}]"
        if not isinstance(task, Mapping):
            err("type_error", path, "任务必须是对象")
            continue
        for key in task:
            if key not in _TASK_KEYS:
                err("unknown_field", f"{path}.{key}", f"未知字段 {key!r}")
        tid = task.get("task_id")
        if not isinstance(tid, str) or not tid:
            err("missing_field", f"{path}.task_id", "缺少 task_id")
        elif tid in seen:
            err("duplicate_id", f"{path}.task_id", f"task_id {tid!r} 重复")
        else:
            seen.add(tid)
        if not task.get("family_id"):
            err("missing_field", f"{path}.family_id", "缺少 family_id（独立分析单位）")
        if task.get("kind") not in TASK_KINDS:
            err("bad_kind", f"{path}.kind", f"kind 必须是 {TASK_KINDS} 之一")
        caps = task.get("capabilities", [])
        if not isinstance(caps, list) or any(c not in known for c in caps):
            err("unknown_capability", f"{path}.capabilities", f"capabilities 必须取自 {known}")
        if not isinstance(task.get("user"), str) or not task.get("user", "").strip():
            err("missing_field", f"{path}.user", "缺少本轮 user")
        if not isinstance(task.get("actor"), str) or not task.get("actor"):
            err("missing_field", f"{path}.actor", "缺少 actor")
        expect = task.get("expect")
        if not isinstance(expect, Mapping):
            err("missing_field", f"{path}.expect", "缺少 expect（评估侧期望）")
            continue
        for key in expect:
            if key not in _EXPECT_KEYS:
                err("unknown_field", f"{path}.expect.{key}", f"未知字段 {key!r}")
        if expect.get("policy") not in POLICIES:
            err("bad_policy", f"{path}.expect.policy", f"policy 必须是 {POLICIES} 之一")
        ctx = task.get("evidence_context")
        ctx_ids: dict[str, str] = {}
        if ctx is not None:
            report = validate_evidence_context(ctx)
            for issue in report.issues:
                issues.append(ContractIssue(issue.code, f"{path}.evidence_context{issue.path[1:]}",
                                            issue.message, issue.severity))
            if isinstance(ctx, Mapping):
                for status in ("current", "history", "unknown"):
                    for item in ctx.get(status) or []:
                        if isinstance(item, Mapping) and isinstance(item.get("evidence_id"), str):
                            ctx_ids[item["evidence_id"]] = status
        elif task.get("kind") not in ("style_only",):
            err("missing_evidence", f"{path}.evidence_context", "该任务类型需要 evidence_context")
        for group in ("required_claims", "forbidden_claims"):
            for cidx, claim in enumerate(expect.get(group, []) or []):
                cpath = f"{path}.expect.{group}[{cidx}]"
                if not isinstance(claim, Mapping) or not claim.get("any_of"):
                    err("bad_claim", cpath, "主张必须带非空 any_of")
                    continue
                eid = claim.get("evidence_id")
                if eid is not None and eid not in ctx_ids:
                    err("dangling_ref", f"{cpath}.evidence_id", f"{eid!r} 不在本任务的证据上下文里")
                status = claim.get("expected_status")
                if status is not None and eid in ctx_ids and ctx_ids[eid] != status:
                    err("label_status_mismatch", f"{cpath}.expected_status",
                        f"标签说 {eid} 应是 {status}，可见上下文里是 {ctx_ids[eid]}")
                if group == "forbidden_claims" and claim.get("reason") not in FORBIDDEN_REASONS:
                    err("bad_reason", f"{cpath}.reason", f"reason 必须是 {FORBIDDEN_REASONS} 之一")
        citation = expect.get("citation") or {}
        for cid in citation.get("must_cite", []) or []:
            if cid not in ctx_ids:
                err("dangling_ref", f"{path}.expect.citation.must_cite", f"{cid!r} 不在证据上下文里")
        hidden = [str(v) for v in (task.get("oracle") or {}).get("hidden_values", []) or []]
        hidden += [v for c in expect.get("forbidden_claims", []) or []
                   if isinstance(c, Mapping) and c.get("reason") == "invisible_leak"
                   for v in c.get("any_of", [])]
        visible_text = json.dumps({k: task.get(k) for k in
                                   ("user", "history", "blocks", "execution_packet", "evidence_context")},
                                  ensure_ascii=False)
        leaked = find_forbidden_values(visible_text, hidden)
        if leaked:
            err("oracle_in_visible_input", path, f"评估侧隐藏值出现在模型可见输入里：{leaked}")
    return ValidationReport(SUITE_SCHEMA, tuple(issues))


def parse_suite(raw: Mapping[str, Any]) -> Suite:
    """严格解析：任何 error 级问题都抛 `ContractError`。"""
    from ..evidence_contract import ContractError

    report = validate_suite(raw)
    if not report.ok:
        raise ContractError(report.errors, SUITE_SCHEMA)
    return Suite(
        suite_id=raw["suite_id"], suite_version=raw["suite_version"],
        tasks=tuple(GroundingTask.from_dict(t) for t in raw["tasks"]),
        capabilities=tuple(raw.get("capabilities", ()) or ()),
        preregistration=dict(raw.get("preregistration") or {}),
        label_source=dict(raw.get("label_source") or {}),
        sha256=canonical_sha256(raw), raw=dict(raw),
    )


__all__ = ["FORBIDDEN_REASONS", "POLICIES", "SUITE_SCHEMA", "TASK_KINDS", "Claim", "Expectation",
           "GroundingTask", "Suite", "canonical_sha256", "parse_suite", "validate_suite"]
