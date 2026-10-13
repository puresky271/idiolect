"""回复生成：离线回放、干跑、显式付费的 OpenAI 兼容 runner。

  · 离线（replay / dry-run）：零密钥、零网络、确定性。dry-run 只产生占位记录
    （`synthetic: dry_run`），评分时一律 missing，永远不能通过正式门禁；
  · 付费（openai-compatible）：必须显式 `allow_paid=True`，调用量超过 `max_calls`
    直接拒绝；先估算调用量与输入字符数（token 与费用只有给了单价/tokenizer 才估），
    不会自动开始大批量或跨模型压测。每条记录绑定生成时 messages 的 SHA——事后
    prompt 变了，评分会判产物过期。

生成用的 messages 走 `pipeline.assemble_task`，与评分时重建的是同一条装配链。
"""
from __future__ import annotations

import os
import time
from typing import Any, Mapping

from ..adapters import ContractPassthroughAdapter
from ..capabilities import resolve_capabilities, task_applicability
from .pipeline import RESPONSE_SCHEMA, assemble_task, eval_now, messages_sha256
from .tasks import Suite


def plan_requests(suite: Suite, *, capabilities=None, runs: int = 1, now=None) -> list[dict]:
    """按评分时同样的规则装配每个任务的 messages（能力未启用就不挂证据块）。"""
    enabled = resolve_capabilities(capabilities)
    now = now or eval_now()
    adapter = ContractPassthroughAdapter()
    rows = []
    for task in suite.tasks:
        applicable, _ = task_applicability([c for c in task.capabilities if c != "style"], enabled)
        context = None
        if applicable and task.evidence_context is not None:
            result = adapter.to_context(task.evidence_context)
            context = result.context if result.ok else None
        messages, _trace = assemble_task(task, context, now=now, include_evidence=applicable)
        for k in range(runs):
            rows.append({"task_id": task.task_id, "k": k, "messages": messages,
                         "messages_sha256": messages_sha256(messages)})
    return rows


def estimate(requests: list[dict], *, max_tokens: int, price_in_per_1k: float | None = None,
             price_out_per_1k: float | None = None, chars_per_token: float | None = None) -> dict:
    """调用量与输入规模估算。没有 tokenizer 时 token 只按调用方给的字符/token 比例粗估。"""
    chars = sum(len(m["content"]) for r in requests for m in r["messages"])
    out: dict[str, Any] = {"calls": len(requests), "input_chars": chars,
                           "max_output_tokens_total": len(requests) * max_tokens,
                           "input_tokens": "unknown", "cost": "unknown（未提供单价）"}
    if chars_per_token:
        tokens_in = chars / chars_per_token
        out["input_tokens"] = f"≈{tokens_in:.0f}（按 {chars_per_token} 字符/token 粗估，不是 tokenizer 计数）"
        if price_in_per_1k is not None and price_out_per_1k is not None:
            cost = tokens_in / 1000 * price_in_per_1k + out["max_output_tokens_total"] / 1000 * price_out_per_1k
            out["cost"] = f"≤{cost:.4f}（输出按上限计）"
    return out


def dry_run_responses(suite: Suite, requests: list[dict]) -> dict:
    """干跑占位回复集：不调模型，评分时一律 missing。"""
    return {"schema_version": RESPONSE_SCHEMA, "suite_id": suite.suite_id, "suite_sha256": suite.sha256,
            "arm": "dry-run", "runner": {"kind": "dry-run", "synthetic": "dry_run",
                                         "note": "占位：不调模型，不能升格为实测"},
            "responses": [{"task_id": r["task_id"], "raw": "", "synthetic": "dry_run",
                           "messages_sha256": r["messages_sha256"]} for r in requests if r["k"] == 0]}


def run_openai_compatible(suite: Suite, requests: list[dict], *, allow_paid: bool, max_calls: int,
                          model: str, temperature: float, max_tokens: int, arm: str,
                          client: Any = None) -> dict:
    """真实调用。`client` 可注入（测试用假客户端）；不注入时按环境变量建 OpenAI 客户端。"""
    if not allow_paid:
        raise PermissionError("付费 runner 需要显式 allow_paid=True（CLI：--yes）")
    if len(requests) > max_calls:
        raise PermissionError(f"本次计划 {len(requests)} 次调用，超过上限 --max-calls {max_calls}")
    if any(r["k"] > 0 for r in requests):
        raise ValueError("response-set/v1 每个任务一条回复；多次重复请分多个臂分别运行")
    if client is None:
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - 取决于是否安装 extras
            raise RuntimeError('付费 runner 需要 openai：pip install "idiolect[llm]"') from exc
        key = os.environ.get("LLM_API_KEY", "").strip()
        base = os.environ.get("LLM_BASE_URL", "").strip()
        if not (key and base and model):
            raise RuntimeError("需要环境变量 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL")
        client = OpenAI(api_key=key, base_url=base)
    rows = []
    for req in requests:
        t0 = time.time()
        try:
            resp = client.chat.completions.create(model=model, messages=req["messages"],
                                                  temperature=temperature, max_tokens=max_tokens)
            choice = resp.choices[0]
            text = (choice.message.content or "").strip()
            row = {"task_id": req["task_id"], "raw": text,
                   "finish_reason": getattr(choice, "finish_reason", None),
                   "error": "" if text else "EMPTY_CONTENT"}
        except Exception as exc:  # noqa: BLE001 - 逐条记录，不中断整批
            row = {"task_id": req["task_id"], "raw": "", "error": f"{type(exc).__name__}: {exc}"}
        row["messages_sha256"] = req["messages_sha256"]
        row["sec"] = round(time.time() - t0, 2)
        rows.append(row)
    return {"schema_version": RESPONSE_SCHEMA, "suite_id": suite.suite_id, "suite_sha256": suite.sha256,
            "arm": arm, "runner": {"kind": "openai-compatible", "model": model, "temperature": temperature,
                                   "max_tokens": max_tokens, "paid": True, "synthetic": None,
                                   "note": "密钥与 base_url 不写入产物"},
            "responses": rows}


def runner_summary(responses: Mapping[str, Any]) -> dict:
    """回复集的运行统计：总数、报错、空回复、因长度截断。"""
    rows = responses.get("responses", [])
    return {"total": len(rows), "errors": sum(1 for r in rows if r.get("error")),
            "empty": sum(1 for r in rows if not str(r.get("raw", "")).strip()),
            "length_finish": sum(1 for r in rows if r.get("finish_reason") == "length")}


__all__ = ["dry_run_responses", "estimate", "plan_requests", "run_openai_compatible", "runner_summary"]
