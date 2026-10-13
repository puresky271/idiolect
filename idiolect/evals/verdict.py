"""评测结果的状态词表与单项判定结构。

每一项判定都必须回答五件事：适不适用、结论是什么、为什么、分子分母是多少、
凭什么（证据与版本）。缺任何一项，聚合层按完整性违规处理，不当作通过。

状态（`STATUSES`）：

  · pass / fail      —— 适用且有机械结论；
  · not_applicable   —— 本任务或本能力不涉及这一项（能力未启用、角色没有风格目标、
                        任务不要求引用……）。**不进分母，也不算通过**；
  · missing          —— 应该有却没有：必需的输入合同、样本或证据缺席；
  · needs_review     —— 开放语言超出机械判定范围，等人工（盲评）标签；
  · error / empty    —— 生成侧报错 / 空回复。空白不等于合格拒答；
  · underpowered     —— 只出现在聚合层：样本单位（family）不足以支撑结论。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

STATUSES = ("pass", "fail", "not_applicable", "missing", "needs_review", "error", "empty",
            "underpowered")
APPLICABILITY = ("applicable", "not_applicable")
# 汇总一个任务内多项判定时的严重度（高者胜）；not_applicable 不参与。
SEVERITY = {"fail": 6, "error": 5, "empty": 5, "missing": 4, "needs_review": 3,
            "underpowered": 2, "pass": 1}
STAGES = ("structural", "prompt_boundary", "response", "aggregate", "gate")
AXES = ("style", "grounding")


@dataclass(frozen=True)
class Check:
    """一项判定。`stage` 标出它发生在链路的哪一段，用于变异检出归因。"""

    check: str
    axis: str
    stage: str
    status: str
    reason: str = ""
    applicability: str = "applicable"
    numerator: int | None = None
    denominator: int | None = None
    evidence: Mapping[str, Any] = field(default_factory=dict)
    scorer: str = ""
    scorer_version: str = ""
    label_source: str = "mechanical"

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError(f"未知状态 {self.status!r}")
        if self.axis not in AXES:
            raise ValueError(f"未知轴 {self.axis!r}")
        if self.stage not in STAGES:
            raise ValueError(f"未知阶段 {self.stage!r}")
        applicability = "not_applicable" if self.status == "not_applicable" else self.applicability
        object.__setattr__(self, "applicability", applicability)
        object.__setattr__(self, "evidence", dict(self.evidence or {}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "check": self.check, "axis": self.axis, "stage": self.stage,
            "status": self.status, "applicability": self.applicability,
            "reason": self.reason, "numerator": self.numerator,
            "denominator": self.denominator, "evidence": dict(self.evidence),
            "scorer": self.scorer, "scorer_version": self.scorer_version,
            "label_source": self.label_source,
        }


def worst_status(statuses: Iterable[str]) -> str:
    """任务级汇总：取最严重的状态；全部 not_applicable 或为空时返回 not_applicable。"""
    ranked = [s for s in statuses if s != "not_applicable"]
    if not ranked:
        return "not_applicable"
    return max(ranked, key=lambda s: SEVERITY.get(s, 0))


def na(check: str, axis: str, stage: str, reason: str, **kw: Any) -> Check:
    """构造一条 not_applicable 判定（必须写明理由）。"""
    return Check(check, axis, stage, "not_applicable", reason, "not_applicable", **kw)


__all__ = ["APPLICABILITY", "AXES", "Check", "SEVERITY", "STAGES", "STATUSES", "na",
           "worst_status"]
