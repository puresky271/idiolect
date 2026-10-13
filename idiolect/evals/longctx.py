"""可选能力 `long-context-stress`：预注册的 family 配对设计、确定性生成器与上下文计量。

设计原则（每条都对应一个容易犯的错）：

  · **family 是独立单位**。每个 family 固定一个语义任务与独立的期望标签，只在
    预注册的干预因子上变化（长度、关键证据位置、干扰密度、冲突、轮数、预算、执行包）；
    臂、轮次、token 数、重复 filler 都是 family 内的嵌套观测，不当独立样本；
  · **一次只动声明过的因子**。生成器断言干扰项里不含任何期望主张的写法——位置或长度
    的变化不能顺带改变语义；会改变时间/权限语义的变化必须另开 family；
  · **计量诚实**。字符与 UTF-8 字节是精确的；token 数只有接入 tokenizer（记录名称与
    版本）时才有，否则写 `unknown`，不拿字符数冒充；
  · **离线回放只测 harness**。合成回复由期望生成，用来验证链路能分清「装配丢证据」
    「模型没用证据」「scorer 不适用」；模型对长上下文的真实反应只能用付费 runner 测；
  · **不碰生产状态**。生成器只用种子与模板，不读真实记忆或聊天历史；宿主的真实上下文
    只能通过显式快照 adapter 进来。
"""
from __future__ import annotations

import hashlib
import itertools
import random
from typing import Any, Callable, Mapping

from ..evidence_contract import EVIDENCE_CONTEXT_SCHEMA
from .tasks import SUITE_SCHEMA, canonical_sha256

PLAN_SCHEMA = "long-context-plan/v1"
GENERATOR_VERSION = "1.0"
_AS_OF = "2026-09-12T15:00:00+09:00"
_DIRECTIONS = ("南侧", "西侧", "北侧", "东侧", "地下", "顶层", "侧门", "后门")
_PLACES = ("便利店", "停车场", "图书角", "售票机", "花坛", "楼梯口", "咖啡店", "公交站", "排练室",
           "天桥", "仓库", "广场")
_ACTS = ("在整理东西", "在等人", "在打电话", "在看告示", "在排队", "在休息", "在找钥匙", "在拍照")


def _rng(seed: int, *parts: str) -> random.Random:
    digest = hashlib.sha256("|".join([str(seed), *parts]).encode("utf-8")).hexdigest()
    return random.Random(int(digest[:16], 16))


def _distractors(seed: int, family_id: str, count: int, banned: list[str], actor_pool: int) -> list[dict]:
    """确定性干扰项：其他 actor 在其他地点的观察。不含任何期望主张的写法。"""
    rng = _rng(seed, family_id, "distractors")
    rows: list[dict] = []
    idx = 0
    while len(rows) < count:
        idx += 1
        actor = f"actor_{rng.randrange(10, 10 + actor_pool)}"
        text = (f"{actor} 在 location_{rng.randrange(1, 40)} 的"
                f"{rng.choice(_DIRECTIONS)}{rng.choice(_PLACES)}，{rng.choice(_ACTS)}。")
        if any(b and b in text for b in banned):
            continue
        rows.append({"evidence_id": f"evidence_{family_id[-2:]}{idx:04d}", "status": "current", "text": text})
        if idx > count * 20:
            raise RuntimeError(f"{family_id}：干扰项生成器找不到不含期望主张的写法")
    return rows


def _chars(rows: list[dict]) -> int:
    return sum(len(r["text"]) + len(r["evidence_id"]) + 4 for r in rows)


def _fill_to(seed, family_id, target_chars, banned, density) -> list[dict]:
    """生成足够多的干扰项，使证据块正文约达到 target_chars。density 控制每条长度的平均密度。"""
    approx = max(1, int(target_chars / 34 * max(0.1, density)))
    rows = _distractors(seed, family_id, approx, banned, actor_pool=20)
    while _chars(rows) < target_chars:
        rows += _distractors(seed + len(rows), family_id, 4, banned, actor_pool=20)
        for n, r in enumerate(rows):
            r["evidence_id"] = f"evidence_{family_id[-2:]}{n + 1:04d}"
    return rows


def _place(rows: list[dict], key: dict, position: str) -> list[dict]:
    out = list(rows)
    if position == "head":
        out.insert(0, key)
    elif position == "tail":
        out.append(key)
    else:
        out.insert(len(out) // 2, key)
    return out


def _banned(semantic: Mapping[str, Any]) -> list[str]:
    exp = semantic.get("expect", {})
    words = [w for c in exp.get("required_claims", []) for w in c.get("any_of", [])]
    words += [w for c in exp.get("forbidden_claims", []) for w in c.get("any_of", [])]
    return words + [str(semantic.get("subject", ""))]


def generate_suite(plan: Mapping[str, Any]) -> dict:
    """把 `long-context-plan/v1` 展开成 `benchmark-suite/v1`（每个臂一个任务）。"""
    if plan.get("schema_version") != PLAN_SCHEMA:
        raise ValueError(f"需要 {PLAN_SCHEMA!r}")
    seed = int(plan["seed"])
    tasks: list[dict] = []
    for fam in plan["families"]:
        design = fam["design"]
        builder = _DESIGNS.get(design)
        if builder is None:
            raise ValueError(f"未知设计 {design!r}；可选 {sorted(_DESIGNS)}")
        tasks.extend(builder(seed, fam))
    suite = {
        "schema_version": SUITE_SCHEMA,
        "suite_id": plan["plan_id"],
        "suite_version": plan["plan_version"],
        "description": plan.get("description", ""),
        "preregistration": dict(plan.get("preregistration") or {}),
        "label_source": dict(plan.get("label_source") or {}),
        "capabilities": ["long-context-stress"],
        "generated_from": {"plan_sha256": canonical_sha256(plan), "generator": "idiolect.evals.longctx",
                           "generator_version": GENERATOR_VERSION, "seed": seed},
        "tasks": tasks,
    }
    return suite


def _arm_id(factors: Mapping[str, Any]) -> str:
    return ",".join(f"{k}={v}" for k, v in sorted(factors.items()))


def _base_context(scene: str) -> dict:
    return {"schema_version": EVIDENCE_CONTEXT_SCHEMA, "observer_id": "actor_a", "as_of": _AS_OF,
            "scene_id": scene, "current": [], "history": [], "unknown": []}


def _design_length_position(seed: int, fam: Mapping[str, Any]) -> list[dict]:
    sem = fam["semantic"]
    lengths: Mapping[str, int] = fam["factors"]["length"]
    positions = fam["factors"]["position"]
    density = float(fam.get("distractor_density", 1.0))
    control = fam["control"]
    out = []
    for (lname, chars), pos in itertools.product(lengths.items(), positions):
        factors = {"length": lname, "position": pos}
        rows = _fill_to(seed, fam["family_id"], chars, _banned(sem), density)
        ctx = _base_context(fam.get("scene_id", "scene_lc"))
        ctx["current"] = _place(rows, dict(sem["key"], status="current"), pos)
        out.append(_task(fam, sem, factors, ctx, control, caps=["long-context-stress"]))
    return out


def _design_multiturn_conflict(seed: int, fam: Mapping[str, Any]) -> list[dict]:
    """多轮 + 历史/当前冲突：早先轮次里说过旧值，证据里旧值在历史、新值在当前。"""
    sem = fam["semantic"]
    out = []
    for conflict, (tname, turns) in itertools.product(fam["factors"]["conflict"],
                                                      fam["factors"]["turns"].items()):
        factors = {"conflict": conflict, "turns": tname}
        rng = _rng(seed, fam["family_id"], tname)
        history: list[dict] = []
        for t in range(int(turns)):
            if conflict == "history_vs_current" and t == 0:
                history += [{"role": "user", "content": sem["old_question"]},
                            {"role": "assistant", "content": sem["old_answer"]}]
                continue
            topic = rng.choice(_PLACES)
            history += [{"role": "user", "content": f"随便聊聊，{topic}那边最近怎么样？"},
                        {"role": "assistant", "content": f"{topic}那边{rng.choice(_ACTS)[1:]}的人挺多。"}]
        ctx = _base_context(fam.get("scene_id", "scene_lc"))
        ctx["current"] = [dict(sem["key"], status="current")]
        if conflict == "history_vs_current":
            ctx["history"] = [dict(sem["old"], status="history")]
        task = _task(fam, sem, factors, ctx, fam["control"],
                     caps=["long-context-stress", "spatiotemporal"])
        task["history"] = history
        if conflict == "none":
            # 无冲突臂里旧值不在上下文：禁止主张保留（不许凭空说出旧值），但去掉指向
            # 历史条目的来源字段，否则合同校验会报悬空引用
            task["expect"] = dict(task["expect"])
            task["expect"]["forbidden_claims"] = [
                {k: v for k, v in c.items() if k not in ("evidence_id", "expected_status")}
                for c in task["expect"].get("forbidden_claims", [])]
        out.append(task)
    return out


def _design_controls(seed: int, fam: Mapping[str, Any]) -> list[dict]:
    """健康保留 vs 故意截断：预算足时关键证据在，预算紧时证据层被整块尾裁。"""
    sem = fam["semantic"]
    out = []
    for bname, budget in fam["factors"]["budget"].items():
        factors = {"budget": bname}
        rows = _fill_to(seed, fam["family_id"], int(fam.get("filler_chars", 1200)), _banned(sem), 1.0)
        ctx = _base_context(fam.get("scene_id", "scene_lc"))
        ctx["current"] = _place(rows, dict(sem["key"], status="current"), "tail")
        task = _task(fam, sem, factors, ctx, fam["control"], caps=["long-context-stress"])
        task["assembly"] = {"max_chars": int(budget), "include_turn_logic": False}
        if int(budget) > 0:
            task["kind"] = "budget_trim"
            task["expect"] = {"policy": "abstain", "abstain_required": True,
                              "evidence_expected_visible": False,
                              "forbidden_claims": [{"claim_id": "trimmed_value", "reason": "fabricated",
                                                    "any_of": [w for c in sem["expect"]["required_claims"]
                                                               for w in c["any_of"]]}]}
        out.append(task)
    return out


def _task(fam, sem, factors, ctx, control, *, caps) -> dict:
    is_control = all(factors.get(k) == v for k, v in control.items())
    return {
        "task_id": f"{fam['family_id']}::{_arm_id(factors)}",
        "family_id": fam["family_id"],
        "kind": sem.get("kind", "current_fact"),
        "capabilities": caps,
        "actor": sem.get("actor", "actor_a"),
        "user": sem["user"],
        "blocks": [["current_state", sem.get("role_card", "你是 actor_a。只根据给你的证据回答，简短。")]],
        "evidence_context": ctx,
        "assembly": {"include_turn_logic": False},
        "expect": sem["expect"],
        "oracle": dict(sem.get("oracle") or {}),
        "arm": _arm_id(factors),
        "long_context": {"family_id": fam["family_id"], "design": fam["design"], "factors": factors,
                         "intervention": list(fam["intervention"]), "is_control": is_control,
                         "control": dict(control)},
    }


_DESIGNS: dict[str, Callable[[int, Mapping[str, Any]], list[dict]]] = {
    "length_x_position": _design_length_position,
    "multiturn_conflict": _design_multiturn_conflict,
    "controls": _design_controls,
}


# ── 计量 ──────────────────────────────────────────────────────────────────

def measure(task_row: Mapping[str, Any], tokenizer: Callable[[str], int] | None = None,
            tokenizer_name: str = "") -> dict:
    """对一条评测结果里的最终 messages 计量。只读 messages 与装配 trace，不重算装配。"""
    messages = task_row["messages"]
    trace = task_row.get("trace") or {}
    lc = task_row.get("long_context") or {}
    total_text = "".join(str(m.get("content", "")) for m in messages)
    by_role: dict[str, int] = {}
    for m in messages:
        by_role[m["role"]] = by_role.get(m["role"], 0) + len(str(m.get("content", "")))
    key_ids = [c.get("evidence_id") for c in (task_row.get("expect") or {}).get("required_claims", [])
               if c.get("evidence_id")]
    from .grounding import parse_evidence_block

    # 与 prompt 边界检查同一个解析器：只数真实证据行，不数空桶的「（无）」占位
    ids = list(parse_evidence_block(messages)["lines"])
    key_index = next((i for i, eid in enumerate(ids) if eid in key_ids), None)
    lines = ids
    packet_index = next((i for i, m in enumerate(messages)
                         if m["role"] == "user" and "【本轮执行】" in str(m.get("content", ""))), None)
    tokens = None
    if tokenizer is not None:
        tokens = int(tokenizer(total_text))
    return {
        "family_id": lc.get("family_id", task_row.get("family_id")),
        "arm": task_row.get("arm"), "factors": lc.get("factors", {}),
        "total_chars": len(total_text), "total_bytes_utf8": len(total_text.encode("utf-8")),
        "messages": len(messages), "chars_by_role": by_role,
        "layers": trace.get("layers", []), "trimmed_layers": trace.get("trimmed", []),
        "max_chars": trace.get("max_chars"), "history_messages": trace.get("history_messages"),
        "evidence_items": len(lines), "key_evidence_present": key_index is not None,
        "key_position_index": key_index,
        "key_position_fraction": (round(key_index / max(1, len(lines) - 1), 3)
                                  if key_index is not None and len(lines) > 1 else None),
        "execution_packet_index": packet_index,
        "tokens": tokens, "tokenizer": tokenizer_name or ("unknown" if tokens is None else "custom"),
    }


def paired_families(results: Mapping[str, Any]) -> dict:
    """family 内配对：每个非对照臂与本 family 的对照臂比较 grounding 判定。

    输出逐 family 的 degraded / improved / same / undecided，以及按因子水平汇总
    「对照通过而该臂失败」的 family 数。family 是独立单位；同一 family 多个臂的计数
    不能当成多个独立样本相加做检验——检验只在主对比（预注册）上按 family 做符号检验。
    """
    from .stats import sign_test

    by_family: dict[str, list[dict]] = {}
    for row in results["tasks"]:
        lc = row.get("long_context")
        if lc:
            by_family.setdefault(lc["family_id"], []).append(row)
    families = {}
    level_tally: dict[str, dict[str, int]] = {}
    for fid, rows in sorted(by_family.items()):
        ctrl = next((r for r in rows if r["long_context"]["is_control"]), None)
        out_rows = []
        for r in rows:
            if r is ctrl:
                continue
            a = ctrl["summary"]["grounding"] if ctrl else "missing"
            b = r["summary"]["grounding"]
            if a == "pass" and b == "fail":
                outcome = "degraded"
            elif a == "fail" and b == "pass":
                outcome = "improved"
            elif a == b and a in ("pass", "fail"):
                outcome = "same"
            else:
                outcome = "undecided"
            out_rows.append({"arm": r["arm"], "control": ctrl["arm"] if ctrl else None,
                             "control_status": a, "arm_status": b, "outcome": outcome,
                             "factors": r["long_context"]["factors"]})
            for k, v in r["long_context"]["factors"].items():
                key = f"{k}={v}"
                level_tally.setdefault(key, {"degraded": 0, "improved": 0, "same": 0, "undecided": 0})
                level_tally[key][outcome] += 1
        families[fid] = {"control": ctrl["arm"] if ctrl else None, "arms": out_rows}
    worse = sum(1 for f in families.values() if any(a["outcome"] == "degraded" for a in f["arms"]))
    better = sum(1 for f in families.values()
                 if any(a["outcome"] == "improved" for a in f["arms"])
                 and not any(a["outcome"] == "degraded" for a in f["arms"]))
    return {"families": families, "by_factor_level": level_tally,
            "family_sign_test": sign_test(better, worse),
            "unit": "family（臂、轮次、token、filler 都是嵌套观测）"}


# ── 合成回放（只测 harness）──────────────────────────────────────────────

def synthetic_replay(suite: Mapping[str, Any], policy: str) -> dict:
    """由期望生成合成回复。`healthy`：按期望作答；`lost_middle`：长上下文且关键证据在
    中段的臂答成「不知道」（模拟中段遗失）；`failure_controls`：对照臂给空回复/报错。
    这只用来验证评测链路，不是模型行为证据。"""
    if policy not in ("healthy", "lost_middle", "failure_controls"):
        raise ValueError(f"未知回放策略 {policy!r}")
    rows = []
    for task in suite["tasks"]:
        exp = task["expect"]
        lc = task.get("long_context") or {}
        factors = lc.get("factors", {})
        if exp.get("abstain_required") and not exp.get("required_claims"):
            text = "不清楚，没有看到相关的消息。"
        else:
            claim = exp["required_claims"][0]["any_of"][0]
            text = f"现在在{claim}。"
            if exp.get("forbidden_claims") and factors.get("conflict") == "history_vs_current":
                old = exp["forbidden_claims"][0]["any_of"][0]
                text = f"之前是{old}，现在在{claim}。"
        row: dict[str, Any] = {"task_id": task["task_id"], "raw": text, "finish_reason": "stop"}
        if policy == "lost_middle" and factors.get("position") == "middle" and factors.get("length") == "long":
            row["raw"] = "不清楚，没看到。"
        if policy == "failure_controls" and lc.get("is_control"):
            if lc["family_id"].endswith("1"):
                row["raw"] = ""
            else:
                row["raw"], row["error"] = "", "TimeoutError: synthetic"
        rows.append(row)
    return {"schema_version": "response-set/v1", "suite_id": suite["suite_id"],
            "suite_sha256": canonical_sha256(suite), "arm": f"replay:{policy}",
            "runner": {"kind": "replay", "synthetic": "replay", "policy": policy,
                       "generator": "idiolect.evals.longctx.synthetic_replay",
                       "note": "由期望生成的合成回复：只验证评测链路，不是模型行为证据"},
            "responses": rows}


__all__ = ["GENERATOR_VERSION", "PLAN_SCHEMA", "generate_suite", "measure", "paired_families",
           "synthetic_replay"]
