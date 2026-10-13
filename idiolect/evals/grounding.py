"""grounding 轴：prompt 边界检查与回复检查。

两段分开记账，是为了在报告里分清四种不同的事：

  · 装配丢了证据（预算尾裁、adapter 漏桶）   → prompt_boundary 阶段 fail
  · 不该给模型看的东西进了 messages          → prompt_boundary 阶段 fail
  · 模型看到了证据却没遵从                   → response 阶段 fail
  · 机械规则判不了（开放改写）               → response 阶段 needs_review

证据被装配摘除时，回复侧的「应答出当前事实」不再适用（模型根本看不到），标
not_applicable 并写明理由；但「不得说出隐藏值」照样检查。
"""
from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from .._textnorm import normalize_for_match
from ..evidence_contract import (
    DEFAULT_RENDER_PROVENANCE_KEYS,
    TemporalEvidenceContext,
    find_forbidden_values,
    is_private_value,
)
from .matching import (
    ABSTAIN_MARKERS,
    CORRECTION_MARKERS,
    MATCHER_VERSION,
    extract_citations,
    find_claim,
    has_marker,
)
from .tasks import GroundingTask
from .verdict import Check, na

SCORER = "idiolect.grounding"
SCORER_VERSION = "1.0"
EVIDENCE_HEADER = "【时空证据上下文】"
_SECTION = {"[当前证据]": "current", "[历史证据]": "history", "[未知边界]": "unknown"}
# 评估侧字段名：出现在 messages 里说明任务/oracle 结构被整块序列化进了 prompt
_EVALUATOR_FIELD_RE = re.compile(
    r"\b(?:hidden_values|forbidden_claims|required_claims|expected_status|oracle|gold_answer|"
    r"evaluator_only|label_source)\b")


def _check(name: str, stage: str, status: str, reason: str = "", **kw: Any) -> Check:
    return Check(name, "grounding", stage, status, reason, scorer=SCORER,
                 scorer_version=SCORER_VERSION, **kw)


def parse_evidence_block(messages: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """从最终 messages 里还原证据块：每个 evidence_id 落在哪个分节、那一行写了什么。"""
    out: dict[str, Any] = {"present": False, "index": None, "lines": {}, "sections": {}}
    for idx, msg in enumerate(messages):
        content = str(msg.get("content", ""))
        if msg.get("role") != "system" or not content.startswith(EVIDENCE_HEADER):
            continue
        out.update(present=True, index=idx)
        section = None
        for line in content.splitlines():
            if line in _SECTION:
                section = _SECTION[line]
                continue
            # 渲染形状是 `- <id>: 正文` 或 `- <id> [as_of: …]: 正文`；ID 本身允许含冒号，
            # 所以按「第一个 `: ` 或 ` [`」截断，而不是按字符类贪婪匹配
            match = re.match(r"^- (\S+?)(?=: | \[)", line)
            if match and section:
                out["lines"][match.group(1)] = line
                out["sections"][match.group(1)] = section
        break
    return out


def check_prompt_boundary(
    task: GroundingTask,
    context: TemporalEvidenceContext | None,
    messages: Sequence[Mapping[str, Any]],
    trace: Mapping[str, Any],
    hidden_values: Sequence[str],
) -> list[Check]:
    """最终 messages 层面的检查：证据可见性、状态与支撑对齐、隐藏值与私有元数据隔离、层序。"""
    stage = "prompt_boundary"
    checks: list[Check] = []
    block = parse_evidence_block(messages)
    trimmed = list(trace.get("trimmed") or [])
    expect = task.expect

    # 1) 关键证据是否真的进了 messages
    keyed = [c for c in expect.required_claims + expect.forbidden_claims if c.evidence_id]
    wanted = list(dict.fromkeys(c.evidence_id for c in expect.required_claims if c.evidence_id))
    if context is None:
        checks.append(na("boundary.evidence_visible", "grounding", stage, "任务没有证据上下文"))
    elif not expect.evidence_expected_visible:
        if block["present"]:
            checks.append(_check("boundary.evidence_visible", stage, "missing",
                                 "场景前提不成立：任务声明证据应被预算摘除，但证据块仍在 messages 里",
                                 evidence={"trimmed": trimmed}))
        else:
            checks.append(_check("boundary.evidence_visible", stage, "pass",
                                 "证据块按设计被预算摘除（装配缺失已记账，回复侧改为不编造）",
                                 evidence={"trimmed": trimmed}))
    elif wanted:
        absent = [eid for eid in wanted if eid not in block["lines"]]
        if not absent:
            checks.append(_check("boundary.evidence_visible", stage, "pass",
                                 numerator=len(wanted), denominator=len(wanted)))
        else:
            dropped = "on_demand_evidence" in trimmed or (trace.get("evidence_layer") in trimmed)
            reason = ("装配丢了关键证据：证据层被预算整块摘除" if dropped
                      else "关键证据不在最终 messages 里（adapter 漏桶或上下文缺条目）")
            checks.append(_check("boundary.evidence_visible", stage, "fail", reason,
                                 numerator=len(wanted) - len(absent), denominator=len(wanted),
                                 evidence={"absent": absent, "trimmed": trimmed}))
    else:
        checks.append(_check("boundary.evidence_visible", stage, "pass" if block["present"] else "fail",
                             "" if block["present"] else "证据块不在最终 messages 里",
                             evidence={"trimmed": trimmed}))

    # 2) 状态对齐：标签说是 history 的条目，在可见包里也必须在历史分节
    with_status = [c for c in keyed if c.expected_status]
    if with_status and block["present"]:
        wrong = [{"evidence_id": c.evidence_id, "expected": c.expected_status,
                  "rendered": block["sections"].get(c.evidence_id)}
                 for c in with_status
                 if c.evidence_id in block["sections"]
                 and block["sections"][c.evidence_id] != c.expected_status]
        checks.append(_check("boundary.status_alignment", stage, "fail" if wrong else "pass",
                             "可见包里的时态与标签不符（例如历史被提升为当前）" if wrong else "",
                             numerator=len(with_status) - len(wrong), denominator=len(with_status),
                             evidence={"mismatches": wrong}))
    else:
        checks.append(na("boundary.status_alignment", "grounding", stage,
                         "任务未标注期望时态，或证据块不可见"))

    # 3) 支撑对齐：要求的主张必须出现在它声称来源的那一行（抓 ID 互换 / 伪造来源）
    supported = [c for c in expect.required_claims if c.evidence_id and c.evidence_id in block["lines"]]
    if supported:
        bad = [c.evidence_id for c in supported
               if not any(normalize_for_match(v) in normalize_for_match(block["lines"][c.evidence_id])
                          for v in c.any_of)]
        checks.append(_check("boundary.support_alignment", stage, "fail" if bad else "pass",
                             "主张不在其声称来源的证据行里（引用被互换或来源被伪造）" if bad else "",
                             numerator=len(supported) - len(bad), denominator=len(supported),
                             evidence={"unsupported": bad}))
    else:
        checks.append(na("boundary.support_alignment", "grounding", stage, "没有可对齐的来源主张"))

    # 4) 隐藏值不得进 messages
    if hidden_values:
        leaked = find_forbidden_values(messages, hidden_values)
        checks.append(_check("boundary.hidden_values_absent", stage, "fail" if leaked else "pass",
                             "评估侧隐藏值出现在模型可见 messages 里" if leaked else "",
                             numerator=len(hidden_values) - len(leaked), denominator=len(hidden_values),
                             evidence={"leaked": leaked}))
    else:
        checks.append(na("boundary.hidden_values_absent", "grounding", stage, "任务没有隐藏值"))

    # 5) 私有元数据与评估字段不得进 messages
    checks.append(_private_metadata_check(messages, context, block))

    # 6) 层序：证据块在 persona 之后、对话历史之前；执行包贴在本轮 user
    problems = []
    roles = [m.get("role") for m in messages]
    if not roles or roles[-1] != "user":
        problems.append("最后一条不是本轮 user")
    if block["present"]:
        first_dialog = next((i for i, r in enumerate(roles) if r in ("user", "assistant")), len(roles))
        if block["index"] > first_dialog:
            problems.append("证据块出现在对话历史之后")
        if task.is_character() and block["index"] == 0:
            problems.append("证据块排在 persona 之前")
    if task.execution_packet and roles and not str(messages[-1].get("content", "")).rstrip().endswith(
            task.execution_packet.strip()):
        problems.append("执行包没有贴在本轮 user 末尾")
    checks.append(_check("boundary.layer_order", stage, "fail" if problems else "pass",
                         "；".join(problems), evidence={"roles": roles,
                                                       "evidence_index": block["index"]}))
    return checks


def _private_metadata_check(messages, context, block) -> Check:
    allowed = set(DEFAULT_RENDER_PROVENANCE_KEYS)
    if context is not None and isinstance(context.permissions.get("render_provenance_keys"), (list, tuple)):
        allowed.update(context.permissions["render_provenance_keys"])
    found: list[str] = []
    for msg in messages:
        content = str(msg.get("content", ""))
        if is_private_value(content):
            found.append("private_path")
        if _EVALUATOR_FIELD_RE.search(content):
            found.append("evaluator_field")
    for line in block["lines"].values():
        for seg in re.findall(r"\[provenance: ([^\]]*)\]", line):
            for pair in seg.split(", "):
                key = pair.split("=", 1)[0]
                if key not in allowed:
                    found.append(f"provenance_key:{key}")
    found = list(dict.fromkeys(found))
    return _check("boundary.private_metadata_absent", "prompt_boundary", "fail" if found else "pass",
                  "私有路径、评估字段或未授权 provenance 键进了 messages" if found else "",
                  evidence={"found": found})


# ── 回复侧 ────────────────────────────────────────────────────────────────

def _field(check: Check | Mapping[str, Any], name: str) -> Any:
    return getattr(check, name) if isinstance(check, Check) else check.get(name)


def score_response(
    task: GroundingTask,
    context: TemporalEvidenceContext | None,
    reply: str,
    record: Mapping[str, Any],
    boundary: Sequence[Check],
    hidden_values: Sequence[str],
) -> list[Check]:
    """回复层面的 grounding 判定。`reply` 是要评的那个视图（clean 或 raw）。"""
    stage = "response"
    expect = task.expect
    names = ["response.required_claims", "response.history_qualified", "response.forbidden_claims",
             "response.abstain", "response.premise_corrected", "response.citation",
             "response.hidden_values"]
    synthetic = record.get("synthetic")
    if synthetic == "dry_run":
        return [_check(n, stage, "missing", "干跑占位不是模型回复，不能参与判定") for n in names]
    if record.get("error"):
        return [_check(n, stage, "error", f"生成报错：{record.get('error')}") for n in names]
    if not str(reply or "").strip():
        return [_check(n, stage, "empty", "空回复（空白不等于合格拒答）") for n in names]

    visible_fail = any(_field(c, "check") == "boundary.evidence_visible" and _field(c, "status") == "fail"
                       for c in boundary)
    blind_reason = "模型看不到关键证据（装配缺失已在 prompt_boundary 记账），回答侧期望不适用"
    checks: list[Check] = []
    abstained = has_marker(reply, ABSTAIN_MARKERS)

    # 要求出现的主张
    if not expect.required_claims:
        checks.append(na("response.required_claims", "grounding", stage, "任务不要求具体主张"))
        checks.append(na("response.history_qualified", "grounding", stage, "任务不要求历史主张"))
    elif visible_fail:
        checks.append(na("response.required_claims", "grounding", stage, blind_reason))
        checks.append(na("response.history_qualified", "grounding", stage, blind_reason))
    else:
        satisfied, negated, missing, unqualified = [], [], [], []
        for claim in expect.required_claims:
            hits = find_claim(reply, claim.any_of)
            good = [h for h in hits if not h.negated]
            if good:
                satisfied.append(claim.claim_id)
                if expect.history_qualifier_required and not any(h.qualified for h in good):
                    unqualified.append(claim.claim_id)
            elif hits:
                negated.append(claim.claim_id)
            else:
                missing.append(claim.claim_id)
        n = len(expect.required_claims)
        if negated:
            status, reason = "fail", "回复否定了证据支持的主张"
        elif not missing:
            status, reason = "pass", ""
        elif abstained:
            status, reason = "fail", "证据可见却回答不知道（没有使用证据）"
        else:
            status, reason = "needs_review", "没有命中声明的主张写法：可能是改写，也可能答非所问"
        checks.append(_check("response.required_claims", stage, status, reason,
                             numerator=len(satisfied), denominator=n,
                             evidence={"satisfied": satisfied, "negated": negated, "missing": missing}))
        if expect.history_qualifier_required:
            if not satisfied:
                checks.append(na("response.history_qualified", "grounding", stage,
                                 "历史主张未出现，限定无从判断（见 required_claims）"))
            else:
                checks.append(_check(
                    "response.history_qualified", stage, "fail" if unqualified else "pass",
                    "历史事实被当作现在说出，缺时间限定" if unqualified else "",
                    numerator=len(satisfied) - len(unqualified), denominator=len(satisfied),
                    evidence={"unqualified": unqualified}))
        else:
            checks.append(na("response.history_qualified", "grounding", stage, "任务不要求时间限定"))

    # 禁止的主张
    if expect.forbidden_claims:
        violations = []
        for claim in expect.forbidden_claims:
            for hit in find_claim(reply, claim.any_of):
                if hit.negated and claim.allow_if_negated:
                    continue
                if hit.qualified and claim.allow_if_qualified:
                    continue
                violations.append({"claim_id": claim.claim_id, "reason": claim.reason,
                                   "clause": hit.clause})
                break
        n = len(expect.forbidden_claims)
        checks.append(_check("response.forbidden_claims", stage, "fail" if violations else "pass",
                             "；".join(sorted({v["reason"] for v in violations})),
                             numerator=n - len({v["claim_id"] for v in violations}), denominator=n,
                             evidence={"violations": violations}))
    else:
        checks.append(na("response.forbidden_claims", "grounding", stage, "任务没有禁止主张"))

    # 拒答 / 不确定
    if expect.abstain_required:
        checks.append(_check("response.abstain", stage, "pass" if abstained else "needs_review",
                             "" if abstained else "没有拒答/不确定标记：需人工判断是否在回避或含糊其辞",
                             evidence={"markers": abstained}))
    else:
        checks.append(na("response.abstain", "grounding", stage, "任务不要求拒答"))

    # 纠正错误前提
    if expect.correction_required:
        corrected = has_marker(reply, CORRECTION_MARKERS)
        checks.append(_check("response.premise_corrected", stage, "pass" if corrected else "needs_review",
                             "" if corrected else "没有纠正标记：需人工判断是否接受了错误前提",
                             evidence={"markers": corrected}))
    else:
        checks.append(na("response.premise_corrected", "grounding", stage, "任务没有错误前提"))

    # 引用（只在任务明确要求时适用）
    if not expect.citation_required:
        checks.append(na("response.citation", "grounding", stage, "任务不要求引用证据 ID"))
    else:
        visible_ids = set(context.evidence_ids) if context is not None else set()
        invisible_ids = {str(x) for x in task.oracle.get("invisible_ids", []) or []}
        cited = extract_citations(reply, visible_ids | invisible_ids)
        leaked = [c for c in cited if c in invisible_ids]
        fabricated = [c for c in cited if c not in visible_ids and c not in invisible_ids]
        absent = [c for c in expect.must_cite if c not in cited]
        problems = []
        if leaked:
            problems.append("引用了观察者不可见的证据")
        if fabricated:
            problems.append("引用了不存在的证据 ID（伪造或悬空）")
        if absent:
            problems.append("缺少必需引用")
        need = len(expect.must_cite) or 1
        checks.append(_check("response.citation", stage, "fail" if problems else "pass",
                             "；".join(problems), numerator=need - len(absent), denominator=need,
                             evidence={"cited": cited, "fabricated": fabricated, "leaked": leaked,
                                       "missing": absent}))

    # 隐藏值
    if hidden_values:
        said = find_forbidden_values(reply, hidden_values)
        checks.append(_check("response.hidden_values", stage, "fail" if said else "pass",
                             "回复说出了观察者不可见的值（泄漏或无据猜测）" if said else "",
                             numerator=len(hidden_values) - len(said), denominator=len(hidden_values),
                             evidence={"said": said}))
    else:
        checks.append(na("response.hidden_values", "grounding", stage, "任务没有隐藏值"))
    return checks


__all__ = ["EVIDENCE_HEADER", "MATCHER_VERSION", "SCORER", "SCORER_VERSION",
           "check_prompt_boundary", "parse_evidence_block", "score_response"]
