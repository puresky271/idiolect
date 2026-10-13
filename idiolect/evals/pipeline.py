"""评测主链：adapter → 装配 → prompt 边界 → 回复 → 风格 → 聚合 → 门禁。

CLI 的 `eval`、`selftest` 的每个变异体、长上下文矩阵都走 `evaluate_suite` 这一个
函数；变异体只能通过 `Components` 替换某一段，或改输入/回复，不能旁路拿预期值给自己
打分（论文 Part I 的教训：被比较的 artifact 必须真的经过被测链路）。

每次运行自带两类有效性自检，结果进 `validity`，任一失败门禁即 FAIL：

  · **门禁充分性金丝雀**：往边界检查里塞一个已知隐藏值、一个私有路径，往回复检查里
    塞一个已知违规——检查器必须翻转判决。接受参数却丢弃它的「空洞门禁」在这里现形；
  · **表示算子认证**：认证范围内的归一化算子必须保持判决（`matching.certify_operators`）。

聚合与门禁的口径：

  · 分母只算 pass + fail；not_applicable / missing / needs_review / error / empty 分列，
    不并入平均，也不算通过；
  · family 是独立单位：同 family 的臂、轮次、重复都是嵌套观测；
  · 门禁：完整性违规、有效性自检失败、任一 fail/error/empty/missing、启用的能力
    零有效判定、全部 N/A → FAIL；只剩 needs_review → INCONCLUSIVE；否则 PASS。
"""
from __future__ import annotations

import hashlib
import json
import warnings
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from ..adapters import ContractPassthroughAdapter
from ..capabilities import resolve_capabilities, task_applicability
from ..evidence_contract import ContractIssue
from .grounding import check_prompt_boundary, score_response
from .matching import certify_operators
from .style_axis import clean_view, score_style
from .tasks import Expectation, GroundingTask, Suite, canonical_sha256
from .verdict import AXES, STATUSES, Check, na, worst_status

RESULTS_SCHEMA = "eval-results/v1"
RESPONSE_SCHEMA = "response-set/v1"
LABELS_SCHEMA = "labels/v1"
EXIT = {"PASS": 0, "FAIL": 1, "INCONCLUSIVE": 3}
_CANARY_VALUE = "CANARY-HIDDEN-5F2C"
_CANARY_PATH = "D:/private/canary/ledger.sqlite"


def sha256_text(text: str) -> str:
    """UTF-8 文本的 SHA-256。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def messages_sha256(messages: Sequence[Mapping[str, Any]]) -> str:
    """messages 列表的规范化指纹（与 probe_runner 的记录口径一致）。"""
    return sha256_text(json.dumps(list(messages), ensure_ascii=False, sort_keys=True))


# ── 回复集 ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ResponseSet:
    """解析后的回复集：所属 suite 与指纹、臂名、生成方式、逐任务记录与形状问题。"""
    suite_id: str
    suite_sha256: str | None
    arm: str
    runner: Mapping[str, Any]
    responses: Mapping[str, Mapping[str, Any]]
    sha256: str
    issues: tuple[ContractIssue, ...] = ()

    @property
    def synthetic(self) -> str | None:
        return self.runner.get("synthetic") or None


def load_response_set(raw: Mapping[str, Any]) -> ResponseSet:
    """解析 `response-set/v1`。形状错误收进 issues（结构阶段 fail），不在这里抛。"""
    issues: list[ContractIssue] = []
    if not isinstance(raw, Mapping) or raw.get("schema_version") != RESPONSE_SCHEMA:
        issues.append(ContractIssue("schema_unknown", "$.schema_version", f"需要 {RESPONSE_SCHEMA!r}"))
        raw = raw if isinstance(raw, Mapping) else {}
    rows: dict[str, dict] = {}
    for idx, row in enumerate(raw.get("responses", []) or []):
        if not isinstance(row, Mapping) or not isinstance(row.get("task_id"), str):
            issues.append(ContractIssue("type_error", f"$.responses[{idx}]", "每条回复需要 task_id"))
            continue
        if row["task_id"] in rows:
            issues.append(ContractIssue("duplicate_id", f"$.responses[{idx}]", f"{row['task_id']} 重复"))
        rows[row["task_id"]] = dict(row)
    return ResponseSet(
        suite_id=str(raw.get("suite_id", "")), suite_sha256=raw.get("suite_sha256"),
        arm=str(raw.get("arm", "") or "unnamed"), runner=dict(raw.get("runner") or {}),
        responses=rows, sha256=canonical_sha256(raw), issues=tuple(issues))


# ── 可替换部件 ────────────────────────────────────────────────────────────

def assemble_task(task: GroundingTask, context, *, now=None, include_evidence: bool = True):
    """走生产同一个 `build_workspace_messages` 装配；返回 (messages, trace)。"""
    from ..scene_engine import isolated_session_state
    from ..workspace import build_workspace_messages

    trace: dict[str, Any] = {}
    assembly = dict(task.assembly)
    with warnings.catch_warnings(record=True) as caught, isolated_session_state():
        warnings.simplefilter("always")
        messages = build_workspace_messages(
            task.actor_for_prompt(), task.user,
            blocks=list(task.blocks), history=[dict(m) for m in task.history],
            execution_packet=task.execution_packet,
            session_id=f"eval:{task.task_id}",
            include_turn_logic=bool(assembly.get("include_turn_logic", True)),
            max_chars=int(assembly.get("max_chars", 0) or 0), now=now,
            evidence_context=context if include_evidence else None,
            evidence_pinned=bool(assembly.get("evidence_pinned", False)),
            trace=trace)
    trace["warnings"] = [str(w.message) for w in caught if issubclass(w.category, RuntimeWarning)]
    return messages, trace


@dataclass
class Components:
    """链路上可被替换的各段。变异体通过它注入故障；默认值就是真实实现。"""

    adapter: Any = field(default_factory=ContractPassthroughAdapter)
    assemble: Callable = assemble_task
    boundary: Callable = check_prompt_boundary
    response: Callable = score_response
    style: Callable = score_style
    cleaner: Callable = clean_view


# ── 主链 ──────────────────────────────────────────────────────────────────

def _row(check: Check | Mapping[str, Any]) -> dict[str, Any]:
    """部件可能返回 Check 或字典（第三方插件、变异体）；统一成字典，缺字段留给完整性检查抓。"""
    return check.to_dict() if isinstance(check, Check) else dict(check)


def _record_view(record: Mapping[str, Any] | None) -> dict[str, Any]:
    if record is None:
        return {"present": False}
    return {"present": True, "raw": str(record.get("raw", "") or ""),
            "error": str(record.get("error", "") or ""),
            "finish_reason": record.get("finish_reason"),
            "synthetic": record.get("synthetic"),
            "messages_sha256": record.get("messages_sha256")}


def evaluate_task(task: GroundingTask, record: Mapping[str, Any] | None, *, enabled: Sequence[str],
                  components: Components, now=None, response_synthetic: str | None = None) -> dict:
    """对单个任务走完整条链，返回带逐层判定的结果行。"""
    applicable, na_reason = task_applicability(
        [c for c in task.capabilities if c != "style"], enabled)
    checks: list[Check] = []
    context = None
    adapter_view: dict[str, Any] = {}

    # 结构阶段：证据合同
    if task.evidence_context is not None and applicable:
        result = components.adapter.to_context(task.evidence_context)
        adapter_view = {"adapter": result.adapter, "version": result.adapter_version,
                        "input_sha256": result.input_sha256, "dropped": list(result.dropped),
                        "issues": [i.to_dict() for i in result.report.issues]}
        context = result.context if result.ok else None
        checks.append(Check("contract.evidence_context", "grounding", "structural",
                            "pass" if result.ok else "fail",
                            "" if result.ok else "证据上下文不满足 v1 合同",
                            evidence={"errors": [i.to_dict() for i in result.report.errors]},
                            scorer=result.adapter, scorer_version=result.adapter_version))
    elif not applicable:
        checks.append(na("contract.evidence_context", "grounding", "structural", na_reason))
    elif task.kind != "style_only":
        checks.append(Check("contract.evidence_context", "grounding", "structural", "missing",
                            "启用了能力，但任务缺少必要的证据上下文"))

    messages, trace = components.assemble(task, context, now=now, include_evidence=applicable)
    msg_sha = messages_sha256(messages)
    view = _record_view(record)
    synthetic = view.get("synthetic") or response_synthetic
    if view["present"]:
        bound = view.get("messages_sha256")
        if bound and bound != msg_sha:
            checks.append(Check("contract.response_binding", "grounding" if applicable else "style",
                                "structural", "fail",
                                "回复生成时的 messages 与现在装配的不同：产物过期，不能评分",
                                evidence={"generated_with": bound, "assembled": msg_sha}))
        view["prompt_binding"] = "bound" if bound else "unbound（合成回放没有记录生成时的 messages）"
    else:
        checks.append(Check("contract.response_present", "style", "structural", "missing",
                            "回复集里没有这个任务"))
    record_for_scoring = {"error": view.get("error"), "synthetic": synthetic}

    if view["present"]:
        clean, cleaner, clean_info = components.cleaner(view["raw"])
    else:
        clean, cleaner, clean_info = "", "none", {}
    reply_present = view["present"]

    # prompt 边界
    hidden = task.hidden_values()
    if applicable and task.kind != "style_only":
        boundary = components.boundary(task, context, messages, trace, hidden)
        checks.extend(boundary)
    else:
        boundary = []
        if task.kind != "style_only":
            checks.append(na("boundary.*", "grounding", "prompt_boundary", na_reason))

    # 回复：grounding
    if applicable and task.kind != "style_only":
        if not reply_present:
            checks.append(Check("response.*", "grounding", "response", "missing", "没有回复"))
        else:
            primary = components.response(task, context, clean, record_for_scoring, boundary, hidden)
            raw_view = components.response(task, context, view["raw"], record_for_scoring, boundary, hidden)
            checks.extend(primary)
            diverged = [_row(a).get("check") for a, b in zip(primary, raw_view)
                        if _row(a).get("status") != _row(b).get("status")]
            if diverged:
                checks.append(Check("response.raw_clean_consistency", "grounding", "response",
                                    "needs_review", "raw 与 clean 视图的 grounding 判定不一致",
                                    evidence={"checks": diverged}))
    elif task.kind != "style_only":
        checks.append(na("response.*", "grounding", "response", na_reason))

    # 回复：风格（默认能力，始终评估）
    if reply_present:
        checks.extend(components.style(task, record_for_scoring, clean, clean_info))
    else:
        checks.append(Check("style.*", "style", "response", "missing", "没有回复"))

    rows = [_row(c) for c in checks]
    return {
        "task_id": task.task_id, "family_id": task.family_id, "kind": task.kind,
        "actor": task.actor, "arm": task.arm, "user": task.user,
        "required_capabilities": list(task.capabilities),
        "applicable": applicable, "not_applicable_reason": na_reason,
        "messages": messages, "messages_sha256": msg_sha, "trace": trace,
        "adapter": adapter_view,
        "expect": task.raw.get("expect"), "oracle_keys": sorted(task.oracle),
        "long_context": task.long_context,
        "record": {**view, "clean": clean, "cleaner": cleaner,
                   "clean_info": dict(clean_info), "synthetic": synthetic},
        "checks": rows,
        "summary": {axis: worst_status(r["status"] for r in rows if r.get("axis") == axis)
                    for axis in AXES},
    }


def validity_probes(components: Components) -> list[dict]:
    """门禁充分性金丝雀：已知违规必须让检查器翻转判决。"""
    canary = GroundingTask(
        task_id="__canary__", family_id="__canary__", kind="invisible_isolation",
        capabilities=("spatiotemporal",), actor="actor_canary", user="canary",
        expect=Expectation.from_dict({
            "policy": "withhold_invisible",
            "forbidden_claims": [{"claim_id": "f", "any_of": [_CANARY_VALUE], "reason": "invisible_leak"}],
        }),
        oracle={"hidden_values": [_CANARY_VALUE]})
    rows = []
    leak_msgs = [{"role": "system", "content": f"【时空证据上下文】\n[当前证据]\n- ev-1: {_CANARY_VALUE}"},
                 {"role": "user", "content": "canary"}]
    clean_msgs = [{"role": "system", "content": "【时空证据上下文】\n[当前证据]\n- ev-1: 普通内容"},
                  {"role": "user", "content": "canary"}]

    def status_of(checks, name):
        for c in checks:
            c = c.to_dict() if isinstance(c, Check) else c
            if c.get("check") == name:
                return c.get("status")
        return None

    try:
        hot = status_of(components.boundary(canary, None, leak_msgs, {}, [_CANARY_VALUE]),
                        "boundary.hidden_values_absent")
        cold = status_of(components.boundary(canary, None, clean_msgs, {}, [_CANARY_VALUE]),
                         "boundary.hidden_values_absent")
        rows.append({"probe": "boundary.hidden_value_canary", "violation": hot, "control": cold,
                     "flipped": hot == "fail" and cold == "pass"})
        path_msgs = [{"role": "system", "content": f"note {_CANARY_PATH}"}, {"role": "user", "content": "x"}]
        hot = status_of(components.boundary(canary, None, path_msgs, {}, []),
                        "boundary.private_metadata_absent")
        cold = status_of(components.boundary(canary, None, clean_msgs, {}, []),
                         "boundary.private_metadata_absent")
        rows.append({"probe": "boundary.private_path_canary", "violation": hot, "control": cold,
                     "flipped": hot == "fail" and cold == "pass"})
        hot = status_of(components.response(canary, None, f"就是 {_CANARY_VALUE}", {}, [], [_CANARY_VALUE]),
                        "response.hidden_values")
        cold = status_of(components.response(canary, None, "不知道。", {}, [], [_CANARY_VALUE]),
                         "response.hidden_values")
        rows.append({"probe": "response.hidden_value_canary", "violation": hot, "control": cold,
                     "flipped": hot == "fail" and cold == "pass"})
        hot = status_of(components.response(canary, None, "", {}, [], [_CANARY_VALUE]),
                        "response.hidden_values")
        rows.append({"probe": "response.empty_canary", "violation": hot, "control": None,
                     "flipped": hot == "empty"})
    except Exception as exc:  # noqa: BLE001 - 检查器在金丝雀上崩溃同样是有效性失败
        rows.append({"probe": "canary_crashed", "error": f"{type(exc).__name__}: {exc}", "flipped": False})
    return rows


def integrity_violations(task_results: Sequence[Mapping[str, Any]], response_set: ResponseSet | None,
                         suite: Suite | None) -> list[str]:
    """聚合前的完整性检查：抓评分器 bug、混批与过期产物。违规即 fail closed。"""
    problems: list[str] = []
    arms = {r.get("arm_label") for r in task_results}
    if len(arms) > 1:
        problems.append(f"混批：一份结果里有多个臂/实验 {sorted(map(str, arms))}")
    for r in task_results:
        rec = r.get("record") or {}
        dead = rec.get("error") or not str(rec.get("clean", "") or "").strip() or rec.get("synthetic") == "dry_run"
        for c in r.get("checks", []):
            if "applicability" not in c or c.get("applicability") not in ("applicable", "not_applicable"):
                problems.append(f"{r['task_id']}/{c.get('check')} 缺 applicability")
            if c.get("status") not in STATUSES:
                problems.append(f"{r['task_id']}/{c.get('check')} 状态非法：{c.get('status')!r}")
            if c.get("status") == "pass" and c.get("stage") == "response" and dead:
                problems.append(f"{r['task_id']}/{c.get('check')} 空回复/报错/干跑却判 pass")
            num, den = c.get("numerator"), c.get("denominator")
            if isinstance(num, int) and isinstance(den, int) and c.get("check") != "style.length_cap" \
                    and c.get("check") != "style.sentence_cap" and (num > den or num < 0):
                problems.append(f"{r['task_id']}/{c.get('check')} 分子超出分母")
    if response_set is not None:
        for issue in response_set.issues:
            problems.append(f"回复集：{issue.path} {issue.code}")
        if suite is not None:
            if response_set.suite_id and response_set.suite_id != suite.suite_id:
                problems.append(f"回复集属于 {response_set.suite_id}，不是 {suite.suite_id}")
            if response_set.suite_sha256 and response_set.suite_sha256 != suite.sha256:
                problems.append("回复集登记的 suite 指纹与当前 suite 不符（过期产物）")
    return list(dict.fromkeys(problems))


def aggregate(task_results: Sequence[Mapping[str, Any]], *, min_families: int) -> dict:
    """双轴 + 质量 + 覆盖。分母、family 单位与「无结论」都显式给出。"""
    out: dict[str, Any] = {"axes": {}, "quality": {}, "coverage": {}}
    for axis in AXES:
        per_check: dict[str, Counter] = defaultdict(Counter)
        family_status: dict[str, list[str]] = defaultdict(list)
        task_status: Counter = Counter()
        for r in task_results:
            statuses = []
            for c in r.get("checks", []):
                if c.get("axis") != axis:
                    continue
                per_check[c["check"]][c["status"]] += 1
                statuses.append(c["status"])
            worst = worst_status(statuses)
            task_status[worst] += 1
            family_status[r["family_id"]].append(worst)
        checks = {}
        for name, counts in sorted(per_check.items()):
            decided = counts["pass"] + counts["fail"]
            checks[name] = {"counts": dict(counts), "numerator": counts["pass"], "denominator": decided,
                            "rate": (counts["pass"] / decided) if decided else None}
        fam = {f: worst_status(s) for f, s in family_status.items()}
        fam_counts = Counter(fam.values())
        decided_f = fam_counts["pass"] + fam_counts["fail"]
        decided_checks = sum(v["denominator"] for v in checks.values())
        out["axes"][axis] = {
            "checks": checks, "tasks": dict(task_status), "families": dict(fam_counts),
            "family_status": fam, "families_decided": decided_f,
            "family_pass_rate": (fam_counts["pass"] / decided_f) if decided_f else None,
            "decided_checks": decided_checks,
            "power": ("underpowered" if decided_f < min_families else "adequate"),
            "min_families": min_families,
        }
    usable = sum(1 for r in task_results
                 if r["record"].get("present") and not r["record"].get("error")
                 and str(r["record"].get("clean", "")).strip() and r["record"].get("synthetic") != "dry_run")
    out["quality"] = {
        "tasks": len(task_results), "usable": usable,
        "empty": sum(1 for r in task_results if r["record"].get("present") and not r["record"].get("error")
                     and not str(r["record"].get("clean", "")).strip()),
        "error": sum(1 for r in task_results if r["record"].get("error")),
        "dry_run": sum(1 for r in task_results if r["record"].get("synthetic") == "dry_run"),
        "missing_response": sum(1 for r in task_results if not r["record"].get("present")),
        "truncated": sum(1 for r in task_results if r["record"].get("finish_reason") == "length"),
        "synthetic_replay": sum(1 for r in task_results if r["record"].get("synthetic") == "replay"),
    }
    reasons = Counter(r["not_applicable_reason"] for r in task_results if not r["applicable"])
    all_checks = [c for r in task_results for c in r.get("checks", [])]
    out["coverage"] = {
        "tasks": len(task_results), "families": len({r["family_id"] for r in task_results}),
        "grounding_applicable_tasks": sum(1 for r in task_results if r["applicable"] and r["kind"] != "style_only"),
        "not_applicable_reasons": dict(reasons),
        "status_counts": dict(Counter(c["status"] for c in all_checks)),
        "needs_review": sum(1 for c in all_checks if c["status"] == "needs_review"),
        "missing": sum(1 for c in all_checks if c["status"] == "missing"),
        "scorer_unavailable": sorted({c["check"] for c in all_checks
                                      if (c.get("evidence") or {}).get("scorer_unavailable")}),
    }
    return out


def gate(agg: Mapping[str, Any], validity: Sequence[Mapping[str, Any]], integrity: Sequence[str],
         *, enabled: Sequence[str], operators: Sequence[Mapping[str, Any]]) -> dict:
    """按聚合、有效性自检与完整性违规给出 PASS / FAIL / INCONCLUSIVE 与理由。"""
    reasons: list[str] = []
    verdict = "PASS"
    if integrity:
        reasons += [f"完整性：{p}" for p in integrity]
    vacuous = [v["probe"] for v in validity if not v.get("flipped")]
    if vacuous:
        reasons.append(f"有效性：门禁金丝雀没有翻转判决（空洞门禁）{vacuous}")
    broken = [o["operator"] for o in operators if o["claimed"] and not o["preserved"]]
    if broken:
        reasons.append(f"有效性：认证范围内的表示算子改变了判决 {broken}")
    counts = agg["coverage"]["status_counts"]
    for status in ("fail", "error", "empty", "missing"):
        if counts.get(status):
            reasons.append(f"{status} × {counts[status]}")
    extra = [c for c in enabled if c != "style"]
    if extra and agg["axes"]["grounding"]["decided_checks"] == 0:
        reasons.append(f"启用了 {extra}，grounding 轴却没有任何有效判定（零样本不能通过）")
    if all(agg["axes"][axis]["decided_checks"] == 0 for axis in AXES):
        reasons.append("全部判定为 N/A 或缺测：没有可以通过的东西")
    if reasons:
        verdict = "FAIL"
    elif agg["coverage"]["needs_review"]:
        verdict = "INCONCLUSIVE"
        reasons.append(f"needs_review × {agg['coverage']['needs_review']}：机械规则判不了，需人工盲评标签")
    notes = [f"{axis} 轴 family 数 {agg['axes'][axis]['families_decided']} < 预注册下限 "
             f"{agg['axes'][axis]['min_families']}：结论强度不足（即使 PASS 也只表示未检出违规，不支持能力结论）"
             for axis in AXES if agg["axes"][axis]["power"] == "underpowered"
             and agg["axes"][axis]["decided_checks"]]
    if agg["coverage"].get("scorer_unavailable"):
        notes.append(f"本次环境缺评分模块，以下检查未执行（不算通过）：{agg['coverage']['scorer_unavailable']}")
    return {"verdict": verdict, "exit_code": EXIT[verdict], "reasons": reasons, "notes": notes}


def apply_labels(task_results: list[dict], labels: Mapping[str, Any] | None) -> list[dict]:
    """人工（盲评）标签只能改写 needs_review；模型 judge 只作为辅助记录，不改判定。"""
    if not labels:
        return []
    applied = []
    if labels.get("schema_version") != LABELS_SCHEMA:
        raise ValueError(f"标签文件需要 schema_version={LABELS_SCHEMA!r}")
    labeler = str(labels.get("labeler", "unknown"))
    by_key = {(row["task_id"], row["check"]): row for row in labels.get("labels", []) or []}
    judges = defaultdict(list)
    for row in labels.get("judge", []) or []:
        judges[row.get("task_id")].append(dict(row))
    for r in task_results:
        for c in r["checks"]:
            row = by_key.get((r["task_id"], c["check"]))
            if row and c["status"] == "needs_review" and row.get("status") in ("pass", "fail"):
                c["status"] = row["status"]
                c["label_source"] = f"human:{labeler}" + (":blind" if labels.get("blind") else "")
                c["reason"] = (c.get("reason") or "") + f"｜人工标签：{row.get('note', '')}"
                applied.append({"task_id": r["task_id"], "check": c["check"], "status": row["status"]})
        if judges.get(r["task_id"]):
            r["auxiliary_judge"] = judges[r["task_id"]]
        r["summary"] = {axis: worst_status(c["status"] for c in r["checks"] if c["axis"] == axis)
                        for axis in AXES}
    return applied


def evaluate_suite(suite: Suite, responses: ResponseSet | None, *, capabilities=None,
                   components: Components | None = None, labels: Mapping[str, Any] | None = None,
                   now=None, experiment_id: str = "") -> dict:
    """跑完整条链，返回 `eval-results/v1`。不写文件（落盘由 manifest/registry 负责）。"""
    comps = components or Components()
    enabled = resolve_capabilities(capabilities)
    now = now or eval_now()
    rows = []
    for task in suite.tasks:
        record = responses.responses.get(task.task_id) if responses is not None else None
        row = evaluate_task(task, record, enabled=enabled, components=comps, now=now,
                            response_synthetic=(responses.synthetic if responses else None))
        row["arm_label"] = responses.arm if responses is not None else None
        rows.append(row)
    labels_applied = apply_labels(rows, labels)
    validity = validity_probes(comps)
    operators = certify_operators()
    integrity = integrity_violations(rows, responses, suite)
    min_f = int(suite.preregistration.get("min_families_for_claims", 6) or 6)
    agg = aggregate(rows, min_families=min_f)
    verdict = gate(agg, validity, integrity, enabled=enabled, operators=operators)
    return {
        "schema_version": RESULTS_SCHEMA,
        "experiment_id": experiment_id,
        "suite": {"id": suite.suite_id, "version": suite.suite_version, "sha256": suite.sha256,
                  "preregistration": dict(suite.preregistration),
                  "label_source": dict(suite.label_source)},
        "responses": ({"arm": responses.arm, "sha256": responses.sha256, "runner": dict(responses.runner)}
                      if responses is not None else None),
        "capabilities": list(enabled),
        "clock": {"now": now.isoformat() if hasattr(now, "isoformat") else str(now)},
        "tasks": rows,
        "labels_applied": labels_applied,
        "validity": {"gate_adequacy": validity, "operator_certification": operators},
        "integrity": integrity,
        "aggregate": agg,
        "gate": verdict,
    }


DEFAULT_EVAL_NOW = "2026-09-12T15:00:00+09:00"


def eval_now():
    """评测时钟：`IDIOLECT_MOCK_NOW` 优先，否则固定在与 tools/mock_clock 相同的默认时刻。"""
    import os

    from ..evidence_contract import _parse_time

    return _parse_time(os.environ.get("IDIOLECT_MOCK_NOW", "").strip() or DEFAULT_EVAL_NOW)

__all__ = ["DEFAULT_EVAL_NOW", "EXIT", "eval_now", "LABELS_SCHEMA", "RESPONSE_SCHEMA", "RESULTS_SCHEMA",
           "Components", "ResponseSet", "aggregate", "apply_labels", "assemble_task",
           "evaluate_suite", "evaluate_task", "gate", "integrity_violations", "load_response_set",
           "messages_sha256", "validity_probes"]
