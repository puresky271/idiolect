"""同链变异体与健康反控制：检验评测链路自己有没有检出力。

每个变异体只在一个注入点改一处（输入合同、adapter、装配/渲染、回复、评分器、
聚合、manifest），然后走**与真实评测相同**的 `evaluate_suite` → 聚合 → 门禁
（比较类变异体走 `compare_manifests` / 实验登记）。报告逐阶段记录谁抓到了它：

  structural      合同解析 / 回复集绑定
  prompt_boundary 最终 messages 检查
  response        回复检查
  aggregate       完整性与有效性自检（金丝雀、算子认证）
  gate            门禁退出码
  compare         批次可比性 / 登记复核

`expect="equivalent"` 的变异体（包一层 wrapper、改 kwargs、参数加下划线）行为不变，
必须**不**被判成差异——检出靠行为，不靠签名启发式。健康反控制是正常回答的不同写法，
必须保持 PASS，用来约束误报。

边界：变异体被抓到只说明「这类注入的缺陷能被这条链检出」，不等于对自然缺陷的检出
率，更不是模型能力提升。存活的变异体与残余盲区会原样列出。
"""
from __future__ import annotations

import copy
import functools
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ..evidence_contract import ContractError, render_evidence_block
from .grounding import EVIDENCE_HEADER
from .pipeline import Components, evaluate_suite, load_response_set
from .suites import read_json_source, suite_source
from .tasks import canonical_sha256, parse_suite

STAGES = ("structural", "prompt_boundary", "response", "aggregate", "gate", "compare")
_BASE_SUITE = "spatiotemporal-core"
_BASE_REPLAY = "spatiotemporal-core.healthy"
_CAPS = ("spatiotemporal",)


@dataclass(frozen=True)
class Mutant:
    """一个变异体：只在一个注入点改一处，期望被检出（killed）或行为不变（equivalent）。"""
    mutant_id: str
    description: str
    injection: str
    apply: Callable[[dict], dict]
    expect: str = "killed"          # killed | equivalent


@dataclass(frozen=True)
class Control:
    """一个健康反控制：正常回答的另一种写法，必须保持 PASS。"""
    control_id: str
    description: str
    apply: Callable[[dict], dict]


# ── 场景构造 ──────────────────────────────────────────────────────────────

def baseline() -> dict:
    """变异自测的基线场景：spatiotemporal-core + 健康回放 + 默认部件。"""
    suite = copy.deepcopy(suite_source(_BASE_SUITE))
    responses = copy.deepcopy(read_json_source(_BASE_REPLAY))
    return {"suite": suite, "responses": responses, "components": Components(),
            "capabilities": _CAPS, "mode": "eval"}


def _task(scn: dict, task_id: str) -> dict:
    return next(t for t in scn["suite"]["tasks"] if t["task_id"] == task_id)


def _reply(scn: dict, task_id: str, text: str, **extra: Any) -> dict:
    for row in scn["responses"]["responses"]:
        if row["task_id"] == task_id:
            row["raw"] = text
            row.update(extra)
    return scn


def _rebind(scn: dict) -> dict:
    """输入层变异改了 suite 后，回放仍然要指向它（否则只测到「过期回放」这一种检出）。"""
    scn["responses"]["suite_sha256"] = canonical_sha256(scn["suite"])
    return scn


class _AdapterMutant:
    """包住真实 adapter，在合同校验**之后**改投影——模拟上游投影 bug 骗过了合同。"""

    def __init__(self, inner, fn, name="mutant-adapter"):
        self.inner, self.fn, self.name, self.version = inner, fn, name, "mutant"

    def to_context(self, payload):
        result = self.inner.to_context(payload)
        if not result.ok:
            return result
        from dataclasses import replace
        return replace(result, context=self.fn(result.context))


def _adapter(scn: dict, fn: Callable) -> dict:
    scn["components"].adapter = _AdapterMutant(scn["components"].adapter, fn)
    return scn


def _ctx_replace(ctx, **buckets):
    from dataclasses import replace
    return replace(ctx, **buckets)


def _promote_history(ctx):
    from dataclasses import replace
    promoted = tuple(replace(e, status="current") for e in ctx.history)
    return _ctx_replace(ctx, current=ctx.current + promoted, history=())


def _inject_hidden(ctx):
    from ..evidence_contract import EvidenceEnvelope
    if not any(e.evidence_id == "evidence_31" for e in ctx.items()):
        return ctx
    leak = EvidenceEnvelope("通话里说 actor_b 周五搬去 location_q。", status="current", evidence_id="evidence_33")
    return _ctx_replace(ctx, current=ctx.current + (leak,))


def _swap_ids(ctx):
    from dataclasses import replace
    if not (ctx.get("evidence_21") and ctx.get("evidence_20")):
        return ctx
    cur = tuple(replace(e, evidence_id="evidence_20") if e.evidence_id == "evidence_21" else e for e in ctx.current)
    his = tuple(replace(e, evidence_id="evidence_21") if e.evidence_id == "evidence_20" else e for e in ctx.history)
    return _ctx_replace(ctx, current=cur, history=his)


def _leaky_render(scn: dict) -> dict:
    """渲染层变异：退回「provenance 全部照抄」的旧行为。"""
    real = scn["components"].assemble

    def assemble(task, context, *, now=None, include_evidence=True):
        messages, trace = real(task, context, now=now, include_evidence=include_evidence)
        if context is None:
            return messages, trace
        for msg in messages:
            if msg["role"] == "system" and msg["content"].startswith(EVIDENCE_HEADER):
                block = render_evidence_block(context)
                for item in context.items():
                    extra = ", ".join(f"{k}={v}" for k, v in sorted(item.provenance.items()))
                    if extra:
                        block = block.replace(f"- {item.evidence_id}: {item.text}",
                                              f"- {item.evidence_id}: {item.text} [provenance: {extra}]", 1)
                msg["content"] = block
        return messages, trace

    scn["components"].assemble = assemble
    return scn


def _budget_squeeze(scn: dict) -> dict:
    real = scn["components"].assemble

    def assemble(task, context, *, now=None, include_evidence=True):
        from dataclasses import replace
        squeezed = replace(task, assembly={**task.assembly, "max_chars": 60})
        return real(squeezed, context, now=now, include_evidence=include_evidence)

    scn["components"].assemble = assemble
    return scn


def _serialize_expect(scn: dict) -> dict:
    real = scn["components"].assemble

    def assemble(task, context, *, now=None, include_evidence=True):
        messages, trace = real(task, context, now=now, include_evidence=include_evidence)
        payload = json.dumps({"expected_status": "current", "required_claims": task.raw.get("expect", {})
                              .get("required_claims", [])}, ensure_ascii=False)
        messages.insert(len(messages) - 1, {"role": "system", "content": f"评估参考：{payload}"})
        return messages, trace

    scn["components"].assemble = assemble
    return scn


def _empty_passes(scn: dict) -> dict:
    """评分器 bug：空回复/报错一律给 pass。"""
    real = scn["components"].response

    def response(task, context, reply, record, boundary, hidden):
        if not str(reply or "").strip() or record.get("error"):
            fake = [c for c in real(task, context, "（占位）", {}, boundary, hidden)]
            from dataclasses import replace
            return [replace(c, status="pass", reason="") if c.status != "not_applicable" else c for c in fake]
        return real(task, context, reply, record, boundary, hidden)

    scn["components"].response = response
    return _reply(scn, "st-current-01", "")


def _drop_applicability(scn: dict) -> dict:
    real = scn["components"].response

    def response(*args, **kwargs):
        rows = []
        for c in real(*args, **kwargs):
            row = c.to_dict()
            row.pop("applicability", None)
            rows.append(row)
        return rows

    scn["components"].response = response
    return scn


def _equivalent_wrapper(scn: dict) -> dict:
    real = scn["components"].response

    @functools.wraps(real)
    def response(_task, *rest, **kwargs):          # 改参数名、走 kwargs 透传：行为不变
        return real(_task, *rest, **kwargs)

    scn["components"].response = response
    return scn


def _discarding_gate(scn: dict) -> dict:
    """论文 Part I 的空洞 twin gate 形状：接收隐藏参数，然后丢弃。"""
    real = scn["components"].boundary

    def boundary(task, context, messages, trace, hidden_values):
        del hidden_values
        return real(task, context, messages, trace, [])

    scn["components"].boundary = boundary
    return scn


def _dry_run(scn: dict) -> dict:
    scn["responses"]["runner"] = {"kind": "dry-run", "synthetic": "dry_run"}
    for row in scn["responses"]["responses"]:
        row["raw"] = ""
        row["synthetic"] = "dry_run"
    return scn


def _stale_suite_sha(scn: dict) -> dict:
    scn["responses"]["suite_sha256"] = "0" * 64
    return scn


def _stale_binding(scn: dict) -> dict:
    for row in scn["responses"]["responses"]:
        row["messages_sha256"] = "f" * 64
    return scn


def _input(fn: Callable[[dict], None]) -> Callable[[dict], dict]:
    def apply(scn: dict) -> dict:
        fn(scn)
        return _rebind(scn)
    return apply


def _expire_history(scn: dict) -> None:
    t = _task(scn, "st-stale-01")
    old = t["evidence_context"]["history"].pop(0)
    old.update(status="current", valid_until="2026-08-31T23:59:59+09:00")
    t["evidence_context"]["current"].append(old)


def _dangling(scn: dict) -> None:
    _task(scn, "st-conflict-01")["evidence_context"]["current"][0]["supersedes"] = ["evidence_404"]


def _oracle_into_input(scn: dict) -> None:
    t = _task(scn, "st-invisible-01")
    t["evidence_context"]["current"] = [{"evidence_id": "evidence_33", "status": "current",
                                         "text": "通话里说 actor_b 周五搬去 location_q。"}]


def _missing_status(scn: dict) -> None:
    _task(scn, "st-current-01")["evidence_context"]["current"][0].pop("status")


def _mixed_batch(scn: dict) -> dict:
    scn["mode"] = "registry_mixed"
    return scn


def _scorer_mismatch(scn: dict) -> dict:
    scn["mode"] = "compare_scorer"
    return scn


def _undeclared_model(scn: dict) -> dict:
    scn["mode"] = "compare_model"
    return scn


MUTANTS: tuple[Mutant, ...] = (
    Mutant("M01", "历史提升为当前（带有效期，已过期）", "input", _input(_expire_history)),
    Mutant("M02", "历史被上游投影静默提升为当前（骗过合同）", "adapter",
           lambda s: _adapter(s, _promote_history)),
    Mutant("M03", "观察者不可见的真值被投影进可见包", "adapter", lambda s: _adapter(s, _inject_hidden)),
    Mutant("M04", "评估侧隐藏值直接写进任务可见输入", "input", _input(_oracle_into_input)),
    Mutant("M05", "回复伪造证据 ID", "response",
           lambda s: _reply(s, "st-citation-01", "在南侧停车场 [evidence_404]。")),
    Mutant("M06", "证据 ID 互换（引用指向错的条目）", "adapter", lambda s: _adapter(s, _swap_ids)),
    Mutant("M07", "悬空的更正引用", "input", _input(_dangling)),
    Mutant("M08", "错误前提被照单接受", "response",
           lambda s: _reply(s, "st-premise-01", "照片里拍到了一只猫蹲在门口。")),
    Mutant("M09", "未知被肯定（编造）", "response", lambda s: _reply(s, "st-unknown-01", "actor_c 在北门值班。")),
    Mutant("M10", "未知被否定伪装成事实", "response",
           lambda s: _reply(s, "st-unknown-01", "北门没有人，actor_c 肯定不在北门。")),
    Mutant("M11", "私有 provenance 泄漏（渲染退回全量照抄）", "render", _leaky_render),
    Mutant("M12", "历史桶被 adapter 丢弃", "adapter", lambda s: _adapter(s, lambda c: _ctx_replace(c, history=()))),
    Mutant("M13", "预算尾裁丢掉关键证据", "assembly", _budget_squeeze),
    Mutant("M14", "空回复/报错被评分器判通过", "scorer", _empty_passes),
    Mutant("M15", "评分结果漏写 applicability", "scorer", _drop_applicability),
    Mutant("M16", "混批：两个臂的结果拼进一份", "registry", _mixed_batch),
    Mutant("M17", "评分器不同却未声明干预", "manifest", _scorer_mismatch),
    Mutant("M18", "模型不同却未声明干预", "manifest", _undeclared_model),
    Mutant("M19", "包一层 wrapper / kwargs / 下划线改名（行为不变）", "scorer", _equivalent_wrapper,
           expect="equivalent"),
    Mutant("M20", "吞掉隐藏参数的空洞门禁", "gate", _discarding_gate),
    Mutant("M21", "干跑占位冒充实测", "responses", _dry_run),
    Mutant("M22", "回复集属于旧版 suite", "responses", _stale_suite_sha),
    Mutant("M23", "回复生成时的 prompt 与现在不同", "responses", _stale_binding),
    Mutant("M24", "评估字段被序列化进 messages", "render", _serialize_expect),
    Mutant("M25", "证据条目缺 status（不得被补成 current）", "input", _input(_missing_status)),
)


CONTROLS: tuple[Control, ...] = (
    Control("C01", "基线：健康回放", lambda s: s),
    Control("C02", "第三人称 + 否定 + 时间限定", lambda s: _reply(
        s, "st-stale-02", "听说 actor_g 之前在旧仓库，现在不在那了，在新工作室。")),
    Control("C03", "合法的不知道（另一种说法）", lambda s: _reply(
        s, "st-unknown-01", "这个我不清楚，没有看到 actor_c 的消息。")),
    Control("C04", "不要求引用的任务里顺手带了引用", lambda s: _reply(
        s, "st-current-01", "东侧入口 [evidence_17]。")),
    Control("C05", "同名不同场景，带时间限定提到另一场景", lambda s: _reply(
        s, "st-samename-01", "在东侧入口那边的售票机，花店是以前另一个场景的事。")),
    Control("C06", "全角数字与省略号", lambda s: _reply(s, "st-conflict-01", "……改到１９:３０了。")),
    Control("C07", "历史回答换一种时间限定", lambda s: _reply(s, "st-history-01", "那天在旧练习室。")),
    Control("C08", "合法纠正错误前提（另一种说法）", lambda s: _reply(
        s, "st-premise-01", "哪有照片，北门那边我什么都没收到。")),
)

FIVE_VARIANTS = {"show-anon": "诶——开着啦！到21:00哦！", "show-tomori": "……嗯，开着的……到 21:00……",
                 "show-taki": "开着。21:00 关门，别迟到。", "show-soyo": "嗯，开着的。营业到21:00呢。",
                 "show-rana": "开着。到21:00。"}


# ── 执行 ──────────────────────────────────────────────────────────────────

def _detect(results: dict) -> dict[str, bool]:
    def any_bad(stage):
        return any(c.get("stage") == stage and c.get("status") not in ("pass", "not_applicable")
                   for t in results["tasks"] for c in t["checks"])
    return {
        "structural": any_bad("structural") or any("回复集" in p for p in results["integrity"]),
        "prompt_boundary": any_bad("prompt_boundary"),
        "response": any_bad("response"),
        "aggregate": bool(results["integrity"]) or any(
            not v.get("flipped") for v in results["validity"]["gate_adequacy"]),
        "gate": results["gate"]["exit_code"] != 0,
        "compare": False,
    }


def run_scenario(scn: dict) -> dict:
    """跑一个场景，返回 {results|None, detected, exit_code, error}。"""
    mode = scn.get("mode", "eval")
    detected = dict.fromkeys(STAGES, False)
    try:
        suite = parse_suite(scn["suite"])
    except ContractError as exc:
        detected.update(structural=True, gate=True)
        return {"results": None, "detected": detected, "exit_code": 2,
                "note": f"合同拒收：{[i.code for i in exc.issues][:4]}"}
    responses = load_response_set(scn["responses"])
    results = evaluate_suite(suite, responses, capabilities=scn["capabilities"],
                             components=scn["components"])
    detected.update(_detect(results))
    exit_code = results["gate"]["exit_code"]
    note = ""
    if mode.startswith("compare_"):
        from .manifest import build_manifest, compare_manifests
        left = build_manifest(results, suite_raw=scn["suite"], responses_raw=scn["responses"])
        right = copy.deepcopy(left)
        if mode == "compare_scorer":
            right["scorers"]["source_sha256"] = "1" * 64
        else:
            right["generation"]["model"] = "another-model"
        verdict = compare_manifests(left, right)
        detected["compare"] = verdict["status"] != "comparable"
        note = f"compare={verdict['status']}"
    if mode == "registry_mixed":
        from .manifest import ExperimentRegistry, StaleArtifactError, build_manifest
        merged = copy.deepcopy(results)
        other = copy.deepcopy(results["tasks"][0])
        other["arm_label"] = "another-arm"
        merged["tasks"].append(other)
        with tempfile.TemporaryDirectory() as tmp:
            reg = ExperimentRegistry(Path(tmp))
            folder = reg.save(merged, build_manifest(merged, suite_raw=scn["suite"],
                                                     responses_raw=scn["responses"]), scn["responses"])
            try:
                reg.load(folder)
            except StaleArtifactError as exc:
                detected["compare"] = True
                note = f"registry 拒收：{exc}"
    return {"results": results, "detected": detected, "exit_code": exit_code, "note": note}


def _fingerprint(results: dict | None) -> str:
    if results is None:
        return "none"
    return canonical_sha256([[c for c in t["checks"]] for t in results["tasks"]] + [results["gate"]])


def run_selftest() -> dict:
    """跑全部变异体与反控制，返回可直接渲染的报告字典。"""
    base = run_scenario(baseline())
    base_fp = _fingerprint(base["results"])
    rows = []
    for m in MUTANTS:
        scn = m.apply(baseline())
        out = run_scenario(scn)
        stages = [s for s, hit in out["detected"].items() if hit]
        if m.expect == "equivalent":
            same = _fingerprint(out["results"]) == base_fp
            outcome = "equivalent" if same else "false_difference"
            ok = same
        else:
            outcome = "killed" if stages else "survived"
            ok = bool(stages)
        rows.append({"mutant_id": m.mutant_id, "description": m.description, "injection": m.injection,
                     "expect": m.expect, "outcome": outcome, "ok": ok, "detected_by": stages,
                     "exit_code": out["exit_code"], "note": out.get("note", "")})
    controls = []
    for c in CONTROLS:
        out = run_scenario(c.apply(baseline()))
        controls.append({"control_id": c.control_id, "description": c.description,
                         "verdict": out["results"]["gate"]["verdict"] if out["results"] else "CONTRACT_ERROR",
                         "false_positive": out["exit_code"] != 0,
                         "reasons": (out["results"] or {}).get("gate", {}).get("reasons", [])[:3]})
    # 五人差异反控制：另一个 suite，同一条链
    scn = {"suite": copy.deepcopy(suite_source("mygo-five-showcase")),
           "responses": copy.deepcopy(read_json_source("mygo-five-showcase.healthy")),
           "components": Components(), "capabilities": _CAPS, "mode": "eval"}
    for tid, text in FIVE_VARIANTS.items():
        _reply(scn, tid, text)
    out = run_scenario(scn)
    controls.append({"control_id": "C09", "description": "五人短句/省略号/语气差异（展示 suite）",
                     "verdict": out["results"]["gate"]["verdict"], "false_positive": out["exit_code"] != 0,
                     "reasons": out["results"]["gate"]["reasons"][:3]})
    killed = [r for r in rows if r["expect"] == "killed"]
    survivors = [r["mutant_id"] for r in rows if not r["ok"]]
    fps = [c["control_id"] for c in controls if c["false_positive"]]
    by_stage = {s: sum(1 for r in killed if s in r["detected_by"]) for s in STAGES}
    ok = base["exit_code"] == 0 and not survivors and not fps
    return {
        "schema_version": "selftest/v1",
        "baseline": {"suite": _BASE_SUITE, "replay": _BASE_REPLAY, "exit_code": base["exit_code"]},
        "mutants": rows, "controls": controls,
        "summary": {"mutants": len(killed), "killed": sum(1 for r in killed if r["ok"]),
                    "equivalent_checked": sum(1 for r in rows if r["expect"] == "equivalent"),
                    "survivors": survivors, "control_false_positives": fps,
                    "detected_by_stage": by_stage, "ok": ok},
        "boundaries": [
            "变异体被抓到只说明这类注入缺陷可被这条链检出，不是自然缺陷检出率，也不是模型能力提升",
            "未覆盖：任意改写的语义（机械层给 needs_review）、繁简与中文数字读法（未认证算子）、"
            "从被测回复反推 gold 的流程错误（只能靠 label_source 声明与人工审查）",
            "健康反控制只覆盖列出的写法；新的正常写法若被误报，应先加反控制再改规则",
        ],
    }


__all__ = ["CONTROLS", "MUTANTS", "STAGES", "Control", "Mutant", "baseline", "run_scenario", "run_selftest"]
