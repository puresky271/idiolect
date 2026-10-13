"""风格轴：逐条回复的风格检查，承接仓库已有的评分口径，不另造一套。

两档来源：

  · **运行时自带**（装了包就有）：`style.length_cap`——回复字数不超过本轮
    style_target 块写给模型的硬上限（`style_target.style_caps`，同一个数），字数口径
    与 `style_features.turn_features.length` 相同（`len(text)`）；
  · **仓库 tools/ 在场时**：`style.sentence_cap`（turn_features 的句数）、
    `style.oob_high`（oob_check 高危档）、`style.canon_fact`（evidence_check 的
    fact 档）、`style.leak`（reply_clean 的思考标签/内心独白/说话人回显）。
    装成 wheel、没有 tools/ 时，这几项是 not_applicable（`scorer_unavailable`）并写明
    原因——不进分母、不算通过，门禁 notes 与 manifest 都会列出来。

分布级指标（composite / distill / 同格重复 / 复述审计）需要探针批次与每格 ≥6 条，
仍由 `tools/probe` + `tools/score` 产出；实验 manifest 可以登记那些批次产物。
opaque actor 没有风格目标，风格轴整体 not_applicable。
"""
from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping

from .tasks import GroundingTask
from .verdict import Check, na

SCORER = "idiolect.style_axis"
SCORER_VERSION = "1.0"
_TOOL_DIRS = ("", "corpus", "distill", "probe", "score", "gates")


def _check(name: str, status: str, reason: str = "", **kw: Any) -> Check:
    return Check(name, "style", "response", status, reason, scorer=SCORER,
                 scorer_version=SCORER_VERSION, **kw)


@lru_cache(maxsize=1)
def load_tools() -> SimpleNamespace | None:
    """找仓库 tools/（`IDIOLECT_TOOLS_DIR` 优先，其次包旁边的仓库根）并导入评分模块。

    `IDIOLECT_STYLE_TOOLS=0` 可显式关闭（用于验证 wheel-only 行为）。找不到返回 None。
    """
    if os.environ.get("IDIOLECT_STYLE_TOOLS", "").strip() == "0":
        return None
    root = os.environ.get("IDIOLECT_TOOLS_DIR", "").strip()
    tools = Path(root) if root else Path(__file__).resolve().parents[2] / "tools"
    if not (tools / "gates" / "oob_check.py").exists():
        return None
    for sub in _TOOL_DIRS:
        path = str(tools / sub) if sub else str(tools)
        if path not in sys.path:
            sys.path.insert(0, path)
    try:
        import evidence_check  # type: ignore[import-not-found]
        import oob_check  # type: ignore[import-not-found]
        import reply_clean  # type: ignore[import-not-found]
        import style_features  # type: ignore[import-not-found]

        # 只导入成功还不够：style_features 在第一次用 cn 分词时才导入 jieba。
        # 先真跑一次，依赖缺失就当作 tools 不在场，而不是评分到一半崩掉
        style_features.turn_features("测试一下。", "cn")
        reply_clean.clean_reply("测试一下。")
    except Exception:  # noqa: BLE001 - tools 不完整就当作不在场
        return None
    return SimpleNamespace(root=str(tools), oob=oob_check, evidence=evidence_check,
                           clean=reply_clean, features=style_features)


def describe_scorers() -> dict[str, Any]:
    """本次环境实际可用的风格检查清单（写进 manifest，用来阻止跨环境自动比较）。"""
    tools = load_tools()
    return {"scorer": SCORER, "version": SCORER_VERSION, "tools_present": tools is not None,
            "checks": ["style.length_cap"] + (["style.sentence_cap", "style.oob_high",
                                                "style.canon_fact", "style.leak"] if tools else [])}


def clean_view(raw: str) -> tuple[str, str, dict]:
    """与 probe_runner 同口径的 clean 视图：tools 在场用 reply_clean，否则原样去首尾空白。"""
    tools = load_tools()
    if tools is None:
        return str(raw or "").strip(), "identity", {}
    cleaned, info = tools.clean.clean_reply(str(raw or ""))
    return cleaned.strip(), "tools/score/reply_clean.clean_reply", info


def score_style(task: GroundingTask, record: Mapping[str, Any], reply: str, clean_info: Mapping) -> list[Check]:
    """逐条风格检查。`reply` 是 clean 视图，`clean_info` 是清洗时记下的泄漏信息。"""
    from ..scene_classifier import classify
    from ..style_target import style_caps

    names = ["style.length_cap", "style.sentence_cap", "style.oob_high", "style.canon_fact",
             "style.leak"]
    if not task.is_character():
        return [na(n, "style", "response", f"{task.actor} 不是已注册角色：没有风格目标") for n in names]
    char = task.actor_for_prompt()
    if record.get("synthetic") == "dry_run":
        return [_check(n, "missing", "干跑占位不是模型回复") for n in names]
    if record.get("error"):
        return [_check(n, "error", f"生成报错：{record.get('error')}") for n in names]
    if not str(reply or "").strip():
        return [_check(n, "empty", "空回复") for n in names]

    checks: list[Check] = []
    scene = classify(task.user, char) or ""
    caps = style_caps(char, scene)
    if caps is None:
        checks.append(na("style.length_cap", "style", "response", "角色没有说话尺度基线"))
    else:
        length = len(reply)
        checks.append(_check("style.length_cap", "pass" if length <= caps["cap_chars"] else "fail",
                             "" if length <= caps["cap_chars"] else "超过本轮写给模型的字数硬上限",
                             numerator=length, denominator=caps["cap_chars"],
                             evidence={"scene": caps["scene"], "cap_chars": caps["cap_chars"],
                                       "length": length}))
    tools = load_tools()
    if tools is None:
        # 评分器不在本次安装里 ≠ 通过：不进分母，计入 coverage.scorer_unavailable，
        # 门禁 notes 里列出；manifest 记录实际跑了哪些 scorer，两种环境的批次不会被自动比较。
        for n in names[1:]:
            checks.append(na(n, "style", "response",
                             "评分模块在仓库 tools/ 里，本次运行不可用（wheel-only 安装）",
                             evidence={"scorer_unavailable": True}))
        return checks
    feats = tools.features.turn_features(reply, "cn")
    if caps is None:
        checks.append(na("style.sentence_cap", "style", "response", "角色没有说话尺度基线"))
    else:
        ok = feats.n_sent <= caps["cap_sentences"]
        checks.append(_check("style.sentence_cap", "pass" if ok else "fail",
                             "" if ok else "超过本轮写给模型的句数硬上限",
                             numerator=feats.n_sent, denominator=caps["cap_sentences"]))
    audit = tools.oob.audit_oob(reply, char)
    checks.append(_check("style.oob_high", "fail" if audit.high_hit else "pass",
                         "越界高危特征命中（AI 自认/系统提示泄漏/第四面墙…）" if audit.high_hit else "",
                         evidence={"features": list(audit.features_hit)}))
    evidence = tools.evidence.audit_evidence(reply, char)
    checks.append(_check("style.canon_fact", "fail" if evidence.fact_violation else "pass",
                         "与角色包明文事实矛盾（担当/学校/CRYCHIC）" if evidence.fact_violation else "",
                         evidence={"violations": list(evidence.violations)}))
    leak = int(clean_info.get("leak", 0) or 0)
    checks.append(_check("style.leak", "fail" if leak else "pass",
                         "回复里有思考标签/内心独白/说话人回显/动作旁白" if leak else "",
                         evidence={"kinds": list(clean_info.get("leak_kinds", []) or [])}))
    return checks


__all__ = ["SCORER", "SCORER_VERSION", "clean_view", "describe_scorers", "load_tools", "score_style"]
