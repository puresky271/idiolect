"""离线 inspect 报告：把已落盘的评测结果渲染成一个不联网的 HTML 文件。

只做展示，不重算评分：页面里的每个数字都来自 `eval-results/v1` / 比较结果 / 自测报告。
数据以 JSON 嵌在 `<script type="application/json">` 里，序列化时转义 `<`、`>`、`&` 与
行分隔符，页面脚本只用 `textContent` 写入，回复里的标签或脚本不会被执行。
`tools/score/report_html.py` 复用同一个 `safe_json_for_script`。
"""
from __future__ import annotations

import json
from importlib import resources
from typing import Any, Mapping, Sequence

_TEMPLATE = "inspect_template.html"


def safe_json_for_script(value: Any) -> str:
    """可安全嵌入 HTML `<script>` 的 JSON。"""
    text = json.dumps(value, ensure_ascii=False, allow_nan=False)
    return (text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
            .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def render_inspect_html(results: Sequence[Mapping[str, Any]], *, manifests: Sequence[Mapping[str, Any]] = (),
                        comparison: Mapping[str, Any] | None = None,
                        selftest: Mapping[str, Any] | None = None,
                        meters: Mapping[str, Any] | None = None) -> str:
    """把评测结果、manifest、比较与自测渲染成离线 HTML（只展示，不重算）。"""
    if not results and not selftest:
        raise ValueError("至少需要一份评测结果或自测报告")
    payload = {"results": list(results), "manifests": list(manifests), "comparison": comparison,
               "selftest": selftest, "meters": meters or {}}
    template = resources.files("idiolect.evals").joinpath(_TEMPLATE).read_text(encoding="utf-8")
    return template.replace("__INSPECT_DATA__", safe_json_for_script(payload))


__all__ = ["render_inspect_html", "safe_json_for_script"]
