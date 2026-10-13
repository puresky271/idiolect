"""idiolect —— 从原作语料蒸馏角色的「个人语型」，落成可验证的 prompt 约束。

四个层次：

1. **观察**（`tools/distill/`）：从原作台词里量出这个角色怎么说话——长度分布、
   句数、标点习惯、自称率、口癖、场景差异。
2. **约束**（`idiolect/`）：把观察写成模型能执行、人能验证的 prompt 文本。
   五类载体：场景分类、每场景长度目标、句式结构与口癖、物品与话题词表、称呼。
3. **动态注入**（`idiolect/scene_engine.py` + 角色包 `turn_logic/`）：只有命中的轮次
   才注入对应场景或主题的指引；命中越具体，注入越具体。
4. **兜底**（角色包 `voice_check/`）：模型漏写的、多写的，在出站前做无损清洗
   （标点配额、省略号归一）与可关闭的风格改写。

每一层都配一个可跑的门禁（`tools/gates/`），改 prompt 必须留下 before/after 证据。

v0.1.2 起另有一条与风格并列、彼此独立的评测轴（`idiolect.evals`，标准库实现）：
证据合同（`idiolect.evidence_contract`）约束「这一轮允许模型看到什么」，grounding
评测检查回答是否受可见证据约束；时空与长上下文压力是显式启用的可选能力
（`idiolect.capabilities`），不启用时默认的语言/风格工作流完全不受影响。

本包不含任何原作台词。随仓库发布的 `data/` 只有派生统计量。
"""
from __future__ import annotations

__version__ = "0.1.2"

__all__ = ["__version__"]
