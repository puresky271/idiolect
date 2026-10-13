"""评测子包（标准库实现，随 wheel 发布）：grounding 与风格双轴、可选能力、实验 manifest、
同链变异自测、长上下文压力计划与离线 inspect 报告。

入口在 `python -m idiolect` 的 `contract / bench / eval / run / compare / report /
selftest / capabilities` 子命令；方法与边界见 docs/09-evidence-grounding.md 与
docs/10-long-context-stress.md。
"""
from __future__ import annotations

from .pipeline import Components, evaluate_suite, load_response_set
from .suites import list_builtins, load_responses, load_suite
from .tasks import parse_suite, validate_suite

__all__ = ["Components", "evaluate_suite", "list_builtins", "load_response_set", "load_responses",
           "load_suite", "parse_suite", "validate_suite"]
