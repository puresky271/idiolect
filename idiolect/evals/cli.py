"""评测相关的子命令：挂在 `python -m idiolect` 下，与 list/prompt/sizes/showcase/chat 并列。

退出码约定（与 tools/gates 一致）：0 通过 / 1 失败或拒绝 / 2 用法或输入错误 / 3 无结论
（needs_review 未标注）。离线命令零密钥、零网络；只有 `run` 在 `--yes` 下才会联网付费。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ..evidence_contract import EVIDENCE_CONTEXT_SCHEMA, ContractError, validate_evidence_context


def _print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def _caps(text: str) -> list[str]:
    return [c.strip() for c in (text or "").split(",") if c.strip()]


# ── capabilities ──

def cmd_capabilities(args: argparse.Namespace) -> int:
    """列出全部评测能力及其版本、输入合同、scorer 与覆盖边界。"""
    from ..capabilities import CAPABILITIES

    if args.json:
        _print_json({k: v.to_dict() for k, v in CAPABILITIES.items()})
        return 0
    for cap in CAPABILITIES.values():
        default = "（默认启用）" if cap.default_enabled else "（显式启用：--capabilities " + cap.name + "）"
        print(f"■ {cap.name} v{cap.version} {default}")
        print(f"  {cap.summary}")
        print(f"  输入合同：{', '.join(cap.input_contracts)}")
        print(f"  适用任务：{', '.join(cap.task_kinds)}")
        print(f"  scorer：{', '.join(cap.scorers)}")
        print(f"  fixture：{', '.join(cap.fixtures)}｜依赖：{', '.join(cap.requires)}")
        print(f"  覆盖：{'；'.join(cap.covers)}")
        print(f"  不覆盖：{'；'.join(cap.not_covered)}\n")
    return 0


# ── contract ──

def _validate_any(raw: Any) -> tuple[str, Any]:
    from ..adapters import SNAPSHOT_SCHEMA, ExplicitSnapshotAdapter
    from .longctx import PLAN_SCHEMA, generate_suite
    from .manifest import MANIFEST_SCHEMA
    from .pipeline import RESPONSE_SCHEMA, load_response_set
    from .tasks import SUITE_SCHEMA, validate_suite

    schema = raw.get("schema_version") if isinstance(raw, dict) else None
    if schema == EVIDENCE_CONTEXT_SCHEMA:
        return schema, validate_evidence_context(raw).to_dict()
    if schema == SNAPSHOT_SCHEMA:
        return schema, ExplicitSnapshotAdapter().to_context(raw).to_dict()
    if schema == SUITE_SCHEMA:
        return schema, validate_suite(raw).to_dict()
    if schema == PLAN_SCHEMA:
        return schema, validate_suite(generate_suite(raw)).to_dict()
    if schema == RESPONSE_SCHEMA:
        rs = load_response_set(raw)
        return schema, {"ok": not rs.issues, "issues": [i.to_dict() for i in rs.issues],
                        "responses": len(rs.responses)}
    if schema == MANIFEST_SCHEMA:
        missing = [k for k in ("code", "suite", "generation", "scorers", "prompt") if k not in raw]
        return schema, {"ok": not missing, "issues": [{"code": "missing_field", "path": f"$.{k}"}
                                                       for k in missing]}
    if schema is None and isinstance(raw, dict) and {"current", "history", "unknown"} & set(raw):
        report = validate_evidence_context(raw).to_dict()
        report["hint"] = "无版本的旧证据字典：严格合同要求 schema_version（兼容层仍可读取，见迁移指南）"
        return "legacy-evidence", report
    return str(schema), {"ok": False, "issues": [{"code": "schema_unknown", "path": "$.schema_version",
                                                   "message": "不认识的合同类型"}]}


def cmd_contract(args: argparse.Namespace) -> int:
    """校验合同文件（自动识别 schema），或把显式快照投影成证据上下文。"""
    from .suites import read_json_source

    try:
        raw = read_json_source(args.file)
    except (OSError, ValueError) as exc:
        print(f"[contract] 读不了 {args.file}：{exc}", file=sys.stderr)
        return 2
    if args.action == "project":
        from ..adapters import ExplicitSnapshotAdapter

        result = ExplicitSnapshotAdapter().to_context(raw)
        _print_json(result.to_dict())
        return 0 if result.ok else 1
    schema, report = _validate_any(raw)
    if args.json:
        _print_json({"schema": schema, **report})
    else:
        ok = report.get("ok")
        print(f"[contract] {args.file} → {schema}：{'OK' if ok else 'INVALID'}")
        for issue in (report.get("report") or report).get("issues", []):
            print(f"  - {issue.get('severity', 'error')} {issue.get('code')} @ {issue.get('path')}："
                  f"{issue.get('message', '')}")
        for drop in report.get("dropped", []) or []:
            print(f"  - dropped {drop.get('record_id')}：{drop.get('reason')}")
    return 0 if report.get("ok") else 1


# ── bench ──

def cmd_bench(args: argparse.Namespace) -> int:
    """列出内置 suite，或查看某个 suite 的任务、模型可见 messages 与上下文计量。"""
    from .suites import list_builtins, load_suite

    if args.action == "list":
        builtins = list_builtins()
        if args.json:
            _print_json(builtins)
            return 0
        print("内置 suite（idiolect bench inspect <名字>）：")
        for name in builtins["suites"]:
            suite = load_suite(name)
            print(f"  {name:<22} {len(suite.tasks):>3} 任务 / {len(suite.families):>2} family｜"
                  f"能力 {','.join(suite.capabilities) or '(仅 style)'}")
        print("内置回放（--responses builtin:<名字>，全部是合成回复，只验证链路）：")
        for name in builtins["replays"]:
            print(f"  builtin:{name}")
        print("样例：" + ", ".join(f"builtin:{n}" for n in builtins["examples"]))
        return 0
    try:
        suite = load_suite(args.suite)
    except (OSError, ContractError) as exc:
        print(f"[bench] {exc}", file=sys.stderr)
        return 2
    tasks = [t for t in suite.tasks if not args.task or t.task_id == args.task]
    if args.messages or args.meter:
        from .longctx import measure
        from .pipeline import Components, evaluate_task, eval_now
        from ..capabilities import resolve_capabilities

        enabled = resolve_capabilities(_caps(args.capabilities) or list(suite.capabilities))
        rows = []
        for task in tasks:
            row = evaluate_task(task, None, enabled=enabled, components=Components(), now=eval_now())
            if args.meter:
                rows.append(measure(row))
            else:
                rows.append({"task_id": task.task_id, "messages": row["messages"], "trace": row["trace"]})
        _print_json(rows)
        return 0
    if args.json:
        _print_json(suite.raw if not args.task else [t.raw for t in tasks])
        return 0
    print(f"{suite.suite_id} v{suite.suite_version}｜{len(suite.tasks)} 任务｜{len(suite.families)} family｜"
          f"指纹 {suite.sha256[:12]}")
    print(f"预注册：{json.dumps(suite.preregistration, ensure_ascii=False)}")
    print(f"标签来源：{json.dumps(suite.label_source, ensure_ascii=False)}\n")
    for t in tasks:
        caps = ",".join(t.capabilities) or "style"
        print(f"- {t.task_id}  [{t.kind}]  family={t.family_id}  actor={t.actor}  能力={caps}")
        print(f"    user：{t.user}")
        print(f"    期望（evaluator-only）：policy={t.expect.policy}"
              f" required={[c.any_of for c in t.expect.required_claims]}"
              f" forbidden={[c.any_of for c in t.expect.forbidden_claims]}"
              f" cite={t.expect.citation_required}")
    print("\n看模型可见 messages：idiolect bench inspect " + args.suite + " --messages [--task ID]")
    return 0


# ── eval ──

def cmd_eval(args: argparse.Namespace) -> int:
    """离线评测：双轴判定 + 门禁，并把结果、manifest、回复集登记到报告目录。"""
    from .manifest import ExperimentRegistry, build_manifest, default_registry_root
    from .pipeline import evaluate_suite
    from .report import render_inspect_html
    from .suites import load_responses, load_suite, read_json_source, suite_source

    try:
        suite = load_suite(args.suite)
        responses = load_responses(args.responses, suite)
        labels = read_json_source(args.labels) if args.labels else None
    except (OSError, ContractError, ValueError) as exc:
        print(f"[eval] 输入不合格：{exc}", file=sys.stderr)
        return 2
    caps = _caps(args.capabilities)
    try:
        results = evaluate_suite(suite, responses, capabilities=caps, labels=labels)
    except ValueError as exc:
        print(f"[eval] {exc}", file=sys.stderr)
        return 2
    gate = results["gate"]
    if args.json:
        _print_json({"gate": gate, "aggregate": results["aggregate"]})
    else:
        _print_eval_summary(results)
    if not args.no_save:
        responses_raw = None
        try:
            from .suites import BUILTIN_REPLAYS
            name = args.responses.removeprefix("builtin:")
            if args.responses.startswith("builtin:") and BUILTIN_REPLAYS.get(name, "") is None:
                from .longctx import synthetic_replay
                responses_raw = synthetic_replay(suite.raw, name.split(".", 1)[1])
            else:
                responses_raw = read_json_source(args.responses)
        except (OSError, ValueError):
            responses_raw = None
        manifest = build_manifest(results, suite_raw=suite_source(args.suite), responses_raw=responses_raw,
                                  labels_raw=labels, intervention=_caps(args.intervention),
                                  intervention_note=args.intervention_note)
        root = Path(args.out_dir) if args.out_dir else default_registry_root()
        folder = ExperimentRegistry(root).save(results, manifest, responses_raw)
        print(f"[eval] 已登记：{folder}（results.json / manifest.json / responses.json）")
        if args.html:
            meters = None
            if any(t.get("long_context") for t in results["tasks"]):
                from .longctx import measure, paired_families
                meters = {"rows": [measure(t) for t in results["tasks"]], "paired": paired_families(results)}
            out = folder / "inspect.html"
            out.write_text(render_inspect_html([results], manifests=[manifest], meters=meters), encoding="utf-8")
            print(f"[eval] inspect 报告：{out}")
    if args.diagnostic:
        print("[eval] --diagnostic：只展示，不以门禁结果作为退出码")
        return 0
    return gate["exit_code"]


def _print_eval_summary(results: dict) -> None:
    gate = results["gate"]
    agg = results["aggregate"]
    runner = (results.get("responses") or {}).get("runner") or {}
    print(f"[eval] suite={results['suite']['id']} 能力={','.join(results['capabilities'])}"
          f" 回复={runner.get('kind')}{'（合成）' if runner.get('synthetic') else ''}")
    for axis in ("style", "grounding"):
        a = agg["axes"][axis]
        rate = "—" if a["family_pass_rate"] is None else f"{a['family_pass_rate'] * 100:.0f}%"
        print(f"  {axis:<9} 已判定检查 {a['decided_checks']:>3}｜family 已判定 {a['families_decided']:>2}"
              f"，通过率 {rate}｜功效 {a['power']}｜family 状态 {a['families']}")
    q = agg["quality"]
    print(f"  质量      可用 {q['usable']}/{q['tasks']}｜空 {q['empty']}｜报错 {q['error']}｜干跑 {q['dry_run']}"
          f"｜缺回复 {q['missing_response']}｜截断 {q['truncated']}｜合成回放 {q['synthetic_replay']}")
    cov = agg["coverage"]
    print(f"  覆盖      状态计数 {cov['status_counts']}｜N/A 原因 {cov['not_applicable_reasons'] or '无'}")
    print(f"[eval] 门禁：{gate['verdict']}（exit {gate['exit_code']}）")
    for reason in gate["reasons"]:
        print(f"  - {reason}")
    for note in gate["notes"]:
        print(f"  · {note}")


# ── run ──

def cmd_run(args: argparse.Namespace) -> int:
    """生成回复集：干跑占位，或在 --yes 与调用上限下显式付费调用。"""
    from .runners import dry_run_responses, estimate, plan_requests, run_openai_compatible, runner_summary
    from .suites import load_suite

    try:
        suite = load_suite(args.suite)
    except (OSError, ContractError) as exc:
        print(f"[run] {exc}", file=sys.stderr)
        return 2
    requests = plan_requests(suite, capabilities=_caps(args.capabilities), runs=1)
    est = estimate(requests, max_tokens=args.max_tokens, price_in_per_1k=args.price_in,
                   price_out_per_1k=args.price_out, chars_per_token=args.chars_per_token)
    print(f"[run] 计划：{est['calls']} 次调用｜输入 {est['input_chars']} 字符｜输入 token {est['input_tokens']}"
          f"｜输出上限合计 {est['max_output_tokens_total']} token｜费用 {est['cost']}")
    out = Path(args.out) if args.out else None
    if args.dry_run:
        data = dry_run_responses(suite, requests)
        print("[run] 干跑：只写占位记录（评分时为 missing，不能通过正式门禁）")
    else:
        if not args.yes:
            print("[run] 付费调用需要显式 --yes（并用 --max-calls 设上限）。本次未调用。", file=sys.stderr)
            return 2
        import os
        model = args.model or os.environ.get("LLM_MODEL", "").strip()
        try:
            data = run_openai_compatible(suite, requests, allow_paid=True, max_calls=args.max_calls,
                                         model=model, temperature=args.temperature,
                                         max_tokens=args.max_tokens, arm=args.arm or f"live:{model}")
        except (PermissionError, RuntimeError, ValueError) as exc:
            print(f"[run] 拒绝执行：{exc}", file=sys.stderr)
            return 2
        print(f"[run] 完成：{runner_summary(data)}")
    if out is None:
        from .manifest import default_registry_root
        out = default_registry_root().parent / f"responses_{suite.suite_id}_{data['arm'].replace(':', '-')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[run] 回复集：{out}\n下一步：idiolect eval --suite {args.suite} --responses {out}"
          + (f" --capabilities {args.capabilities}" if args.capabilities else ""))
    return 0


# ── compare / report / selftest ──

def cmd_compare(args: argparse.Namespace) -> int:
    """读取两个登记过的实验，先判可比性，再做 family 级配对比较。"""
    from .manifest import ExperimentRegistry, StaleArtifactError, compare_manifests, compare_results
    from .report import render_inspect_html

    try:
        left, lm = ExperimentRegistry.load(Path(args.left))
        right, rm = ExperimentRegistry.load(Path(args.right))
    except (OSError, StaleArtifactError) as exc:
        print(f"[compare] 拒绝：{exc}", file=sys.stderr)
        return 1
    verdict = compare_manifests(lm, rm)
    result = compare_results(left, right, verdict)
    if args.json:
        _print_json(result)
    else:
        print(f"[compare] 可比性：{verdict['status']}｜池化 {verdict['pooling_allowed']}｜改善判定 "
              f"{verdict['improvement_claim_allowed']}")
        for reason in verdict["reasons"]:
            print(f"  - {reason}")
        for axis, row in result["axes"].items():
            print(f"  {axis:<9} 改善 {row['improved']}｜退化 {row['regressed']}｜不变 {row['same']}"
                  f"｜无法判定 {row['undecided']}｜结论 {row['judgement']}")
    if args.html:
        Path(args.html).write_text(render_inspect_html([left, right], manifests=[lm, rm], comparison=result),
                                   encoding="utf-8")
        print(f"[compare] inspect 报告：{args.html}")
    return 0 if verdict["status"] == "comparable" else 1


def cmd_report(args: argparse.Namespace) -> int:
    """把登记过的实验（可附自测）导出成离线 inspect HTML。"""
    from .manifest import ExperimentRegistry, StaleArtifactError
    from .report import render_inspect_html

    results, manifests = [], []
    for folder in args.dirs:
        try:
            r, m = ExperimentRegistry.load(Path(folder))
        except (OSError, StaleArtifactError) as exc:
            print(f"[report] 拒绝：{exc}", file=sys.stderr)
            return 1
        results.append(r)
        manifests.append(m)
    selftest = None
    if args.selftest:
        from .mutants import run_selftest
        selftest = run_selftest()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_inspect_html(results, manifests=manifests, selftest=selftest), encoding="utf-8")
    print(f"[report] inspect 报告：{out}")
    return 0


def cmd_selftest(args: argparse.Namespace) -> int:
    """运行同链变异体与健康反控制，任何存活或误报都返回非零。"""
    from .mutants import run_selftest

    report = run_selftest()
    if args.json:
        _print_json(report)
    else:
        s = report["summary"]
        print(f"[selftest] 基线 exit={report['baseline']['exit_code']}｜变异体 {s['killed']}/{s['mutants']} 被检出"
              f"｜等价体 {s['equivalent_checked']}｜反控制误报 {len(s['control_false_positives'])}")
        print(f"  按阶段检出：{s['detected_by_stage']}")
        for row in report["mutants"]:
            mark = "✓" if row["ok"] else "✗"
            print(f"  {mark} {row['mutant_id']} [{row['injection']}] {row['description']} → {row['outcome']}"
                  f"（{', '.join(row['detected_by']) or '无'}）")
        for row in report["controls"]:
            print(f"  {'✗' if row['false_positive'] else '✓'} {row['control_id']} {row['description']}"
                  f" → {row['verdict']}")
        for line in report["boundaries"]:
            print(f"  · {line}")
    if args.html:
        from .report import render_inspect_html
        Path(args.html).parent.mkdir(parents=True, exist_ok=True)
        Path(args.html).write_text(render_inspect_html([], selftest=report), encoding="utf-8")
        print(f"[selftest] inspect 报告：{args.html}")
    return 0 if report["summary"]["ok"] else 1


def register(sub: argparse._SubParsersAction) -> None:
    """把评测子命令挂到 `python -m idiolect` 的子命令解析器上。"""
    p = sub.add_parser("capabilities", help="列出评测能力（默认 style；可选 spatiotemporal / long-context-stress）")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("contract", help="校验合同文件，或把显式快照投影成证据上下文")
    p.add_argument("action", choices=("validate", "project"))
    p.add_argument("file", help="JSON 文件路径或内置名（如 builtin:snapshot.example）")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("bench", help="列出 / 查看评测 suite")
    p.add_argument("action", choices=("list", "inspect"))
    p.add_argument("suite", nargs="?", default="")
    p.add_argument("--task", default="")
    p.add_argument("--messages", action="store_true", help="打印模型可见 messages（同评测装配链）")
    p.add_argument("--meter", action="store_true", help="打印上下文计量（长上下文）")
    p.add_argument("--capabilities", default="")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("eval", help="离线评测：给定 suite 与回复集，双轴判定 + 门禁 + 登记")
    p.add_argument("--suite", required=True)
    p.add_argument("--responses", required=True, help="回复集文件，或 builtin:<名字>")
    p.add_argument("--capabilities", default="", help="spatiotemporal,long-context-stress（style 总是启用）")
    p.add_argument("--labels", default="", help="人工盲评标签（labels/v1）")
    p.add_argument("--intervention", default="", help="预注册的干预变量（逗号分隔，写进 manifest）")
    p.add_argument("--intervention-note", default="")
    p.add_argument("--out-dir", default="", help="实验登记根目录（默认 report/experiments）")
    p.add_argument("--no-save", action="store_true")
    p.add_argument("--html", action="store_true", help="同时写 inspect.html")
    p.add_argument("--diagnostic", action="store_true", help="只展示，退出码恒为 0")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("run", help="生成回复：--dry-run 占位，或 --yes 显式付费调用 OpenAI 兼容端点")
    p.add_argument("--suite", required=True)
    p.add_argument("--capabilities", default="")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--yes", action="store_true", help="确认付费调用")
    p.add_argument("--max-calls", type=int, default=0, help="调用上限；计划超过上限直接拒绝")
    p.add_argument("--model", default="")
    p.add_argument("--temperature", type=float, default=0.75)
    p.add_argument("--max-tokens", type=int, default=420)
    p.add_argument("--arm", default="")
    p.add_argument("--out", default="")
    p.add_argument("--chars-per-token", type=float, default=None)
    p.add_argument("--price-in", type=float, default=None, help="每千输入 token 单价")
    p.add_argument("--price-out", type=float, default=None, help="每千输出 token 单价")

    p = sub.add_parser("compare", help="比较两个登记过的实验（先判可比性，再做 family 配对）")
    p.add_argument("left")
    p.add_argument("right")
    p.add_argument("--json", action="store_true")
    p.add_argument("--html", default="")

    p = sub.add_parser("report", help="把登记过的实验导出成离线 inspect HTML")
    p.add_argument("dirs", nargs="+")
    p.add_argument("--out", default="report/inspect.html")
    p.add_argument("--selftest", action="store_true", help="附上同链变异自测")

    p = sub.add_parser("selftest", help="同链变异体 + 健康反控制：评测链路自己的检出力")
    p.add_argument("--json", action="store_true")
    p.add_argument("--html", default="")


HANDLERS = {"capabilities": cmd_capabilities, "contract": cmd_contract, "bench": cmd_bench,
            "eval": cmd_eval, "run": cmd_run, "compare": cmd_compare, "report": cmd_report,
            "selftest": cmd_selftest}

__all__ = ["HANDLERS", "register"]
