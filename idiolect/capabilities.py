"""可选评测能力的注册表。

默认工作流只有 `style`（语言/风格），普通 prompt 不需要提交任何时空 schema。
`spatiotemporal` 与 `long-context-stress` 是显式启用的扩展能力：

  · 未启用时，相应任务的 grounding 轴显示 not_applicable，不阻塞风格评测；
  · 启用却缺必要合同或样本时报 missing，不降级成通过；
  · 两个能力可以同时启用；需要两者的任务只有在两者都启用时才适用。

每个能力声明版本、输入合同、适用任务类型、scorer、fixture、依赖与覆盖边界——
这些字段原样进实验 manifest，换了能力版本的两批结果不会被自动比较。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class Capability:
    """一个评测能力的声明：版本、输入合同、适用任务、scorer、fixture、依赖与覆盖边界。"""
    name: str
    version: str
    summary: str
    input_contracts: tuple[str, ...]
    task_kinds: tuple[str, ...]
    scorers: tuple[str, ...]
    fixtures: tuple[str, ...]
    requires: tuple[str, ...]
    covers: tuple[str, ...]
    not_covered: tuple[str, ...]
    default_enabled: bool = False

    def to_dict(self) -> dict:
        return {k: (list(v) if isinstance(v, tuple) else v) for k, v in self.__dict__.items()}


CAPABILITIES: dict[str, Capability] = {
    "style": Capability(
        name="style", version="1.0", default_enabled=True,
        summary="角色语言/风格：四层装配 + 风格轴评分（默认工作流，无需时空 schema）",
        input_contracts=("benchmark-suite/v1",),
        task_kinds=("style_only", "*"),
        scorers=("style.length_cap", "style.sentence_cap", "style.oob_high",
                 "style.canon_fact", "style.leak"),
        fixtures=("language-only", "mygo-five-showcase"),
        requires=("stdlib",),
        covers=("本轮说话尺度硬上限（字数，与 style_target 块同一数字）",
                "仓库 tools/ 在场时：句数上限、越界高危特征、canon 事实、思考标签泄漏"),
        not_covered=("分布级贴合（composite / distill 需要探针批次与每格 ≥6 条）",
                     "人工盲评；opaque actor 没有风格目标，风格轴为 not_applicable"),
    ),
    "spatiotemporal": Capability(
        name="spatiotemporal", version="1.0",
        summary="观察者可见证据下的时态 grounding：current / history / unknown、引用、错误前提、可见性隔离",
        input_contracts=("evidence-context/v1", "explicit-snapshot/v1", "benchmark-suite/v1"),
        task_kinds=("current_fact", "history_qualified", "unknown_abstain", "false_premise",
                    "citation", "invisible_isolation", "stale_as_current",
                    "conflict_correction", "budget_trim", "private_metadata"),
        scorers=("grounding.contract", "grounding.prompt_boundary", "grounding.response"),
        fixtures=("spatiotemporal-core", "mygo-five-showcase"),
        requires=("stdlib",),
        covers=("合成受控事实上的主张出现/否定/时间限定", "隐藏值与私有元数据不进 messages",
                "引用存在、可见、支撑主张", "预算摘除证据时区分装配缺失与模型未遵从"),
        not_covered=("任意改写的语义理解（给 needs_review）", "图像/音视频解码、定位与地理投影",
                     "世界模拟与记忆存储", "current/history 的推导（由上游投影给出）"),
    ),
    "long-context-stress": Capability(
        name="long-context-stress", version="1.0",
        summary="长上下文压力：长度 × 关键证据位置 × 干扰密度 × 冲突 × 多轮 × 预算的预注册配对设计",
        input_contracts=("long-context-plan/v1", "benchmark-suite/v1", "evidence-context/v1"),
        task_kinds=("current_fact", "conflict_correction", "budget_trim", "style_only"),
        scorers=("grounding.prompt_boundary", "grounding.response", "longctx.meter",
                 "longctx.paired_family"),
        fixtures=("long-context-smoke",),
        requires=("stdlib", "可选 tokenizer（记录名称与版本；缺省 token 数为 unknown）"),
        covers=("字符/字节计量与被裁剪项", "family 内配对比较（family 是独立单位）",
                "离线 replay 只测 harness；真实模型反应需显式付费 runner"),
        not_covered=("模型精确 token 数（除非接入 tokenizer）", "记忆系统能力",
                     "生产上下文的自动检索（只接受显式快照）"),
    ),
}


def capability_names() -> tuple[str, ...]:
    """全部已注册能力的名字（按注册顺序）。"""
    return tuple(CAPABILITIES)


def resolve_capabilities(enabled: Iterable[str] | str | None) -> tuple[str, ...]:
    """把用户传入的能力名规整成有序元组（总是包含默认能力）；未知名直接报错。"""
    if isinstance(enabled, str):
        enabled = [x.strip() for x in enabled.split(",")]
    names = [x for x in (enabled or ()) if x]
    unknown = [x for x in names if x not in CAPABILITIES]
    if unknown:
        raise ValueError(f"未知能力 {unknown}；可选 {list(CAPABILITIES)}")
    out = [name for name, cap in CAPABILITIES.items() if cap.default_enabled or name in names]
    return tuple(out)


def task_applicability(required: Iterable[str], enabled: Iterable[str]) -> tuple[bool, str]:
    """任务所需能力是否全部启用；返回 (是否适用, 理由)。"""
    missing = [c for c in required if c not in set(enabled)]
    if missing:
        return False, f"能力未启用：{', '.join(missing)}"
    return True, ""


__all__ = ["CAPABILITIES", "Capability", "capability_names", "resolve_capabilities",
           "task_applicability"]
