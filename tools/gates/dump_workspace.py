"""workspace 路径的确定性 prompt dump：补 `dump_prompt.py` 覆盖不到的那一段。

`dump_prompt.py` 只装配四层（persona 位），看不到 `build_workspace_messages`
在四层之外挂的上下文层、对话历史、执行包位置、预算尾裁和证据块。改这条路径的
代码同样要留 before/after 证据，所以这里固定一组输入，逐例落盘完整 messages。

用法（与 prompt diff 门禁同纪律：改动前后同输入、同时钟、不同输出目录）：

    $env:IDIOLECT_REPORT_DIR = "report/<改动>/before"
    py -X utf8 tools/gates/dump_workspace.py
    # 修改代码后
    $env:IDIOLECT_REPORT_DIR = "report/<改动>/after"
    py -X utf8 tools/gates/dump_workspace.py
    Remove-Item Env:\\IDIOLECT_REPORT_DIR

两组用例：

  · `legacy.*`   —— 不带证据的老路径（12 层、历史、执行包、预算裁剪）。代码升级后
                    这组必须零漂移。
  · `evidence.*` —— `fixtures/temporal_evidence_cases.json` 里的三态证据（旧的无版本
                    字典写法，经兼容层进入）。证据渲染的有意改动在这组 diff 里审。
  · `contract.*` —— 版本化证据合同（`--contract` 才导出；旧代码没有这条路径，
                    没有 before 产物，需在报告里明确说明）。

产物：`workspace_<case>.json`（原样 messages）+ `workspace_<case>.txt`（逐条带角色与
字符数的人读版）+ `workspace_dump_index.json`。
"""
from __future__ import annotations

# ── idiolect 路径引导：仓库根 + 各 tools 子目录上 sys.path ──
import sys as _sys
from pathlib import Path as _Path
_ROOT = _Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "tools",
           *(_ROOT / "tools" / _d for _d in ("corpus", "distill", "probe", "score", "gates"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))
from _paths import REPORT, ROOT  # noqa: E402

import argparse
import hashlib
import json

import mock_clock as MOCK  # noqa: E402

_HISTORY = [
    {"role": "user", "content": "在干嘛"},
    {"role": "assistant", "content": "练习。"},
]
_BLOCKS = [
    ("current_state", "乐奈在 RiNG 排练室，下午没课"),
    ("fact_workspace", "用户上周提过想养猫"),
    ("memory_recall", "上次聊到屋檐下的野猫"),
    ("recent_dialogue_guard", "别重复上一轮的「练习。」"),
]
_PACKET = "【本轮执行】回复 ≤19 字"


def _legacy_cases() -> list[tuple[str, str, str, dict]]:
    return [
        ("legacy.blocks", "乐奈", "你今天又想去哪找猫",
         {"blocks": _BLOCKS, "history": _HISTORY, "execution_packet": _PACKET}),
        ("legacy.no_turn_logic", "灯", "我一直在哭，快撑不住了",
         {"blocks": _BLOCKS[:2], "include_turn_logic": False}),
        # persona 约 1.5 万字；预算卡在 persona + 少量外部块之间，触发整块尾裁
        ("legacy.budget_trim", "乐奈", "你今天又想去哪找猫",
         {"blocks": _BLOCKS, "history": _HISTORY, "execution_packet": _PACKET,
          "max_chars": 15590}),
        ("legacy.custom_layer", "立希", "明天几点上课",
         {"blocks": [("current_state", "立希在 RiNG 打工"), ("x_custom", "自定义层排在 12 层之后")]}),
    ]


def _evidence_cases() -> list[tuple[str, str, str, dict]]:
    path = ROOT / "fixtures" / "temporal_evidence_cases.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    rows: list[tuple[str, str, str, dict]] = []
    for case in data.get("cases", []):
        rows.append((f"evidence.{case['id']}", "乐奈", case["user"],
                     {"evidence_context": case["context"], "include_turn_logic": False,
                      "blocks": [("current_state", "合成场景")]}))
    first = (data.get("cases") or [None])[0]
    if first:
        rows.append(("evidence.no_provenance", "乐奈", first["user"],
                     {"evidence_context": first["context"], "include_turn_logic": False,
                      "include_evidence_provenance": False}))
    return rows


def _contract_cases() -> list[tuple[str, str, str, dict]]:
    """版本化合同路径：只在新代码上存在。"""
    from idiolect.evals.suites import load_suite

    suite = load_suite("spatiotemporal-core")
    rows = []
    for task in suite.tasks[:4]:
        rows.append((f"contract.{task.task_id}", task.actor_for_prompt(), task.user,
                     {"evidence_context": task.evidence_context, "include_turn_logic": False,
                      "blocks": list(task.blocks), "execution_packet": task.execution_packet or ""}))
    return rows


def _render_txt(case: str, char: str, user: str, messages: list[dict]) -> str:
    lines = [f"# workspace dump · {case}", f"- 角色：{char}", f"- 本轮 user：{user}",
             f"- 时钟：{MOCK.describe()}", f"- messages：{len(messages)} 条", ""]
    for idx, msg in enumerate(messages):
        body = str(msg.get("content", ""))
        lines += ["=" * 72, f"## [{idx}] {msg.get('role')} · {len(body)} 字符", "=" * 72, body, ""]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="workspace 路径的确定性 prompt dump")
    ap.add_argument("--contract", action="store_true", help="额外导出版本化证据合同用例（仅新代码）")
    ap.add_argument("--only", default="", help="只导出这些前缀（逗号分隔，如 legacy,evidence）")
    args = ap.parse_args()

    from idiolect.scene_engine import isolated_session_state
    from idiolect.workspace import build_workspace_messages

    cases = _legacy_cases() + _evidence_cases()
    if args.contract:
        cases += _contract_cases()
    if args.only:
        prefixes = tuple(p.strip() + "." for p in args.only.split(",") if p.strip())
        cases = [c for c in cases if c[0].startswith(prefixes)]
    REPORT.mkdir(parents=True, exist_ok=True)
    index = []
    now = MOCK.mock_now()
    for case, char, user, kwargs in cases:
        with isolated_session_state():
            messages = build_workspace_messages(
                char, user, session_id=f"dump_workspace:{case}", now=now, **kwargs)
        blob = json.dumps(messages, ensure_ascii=False, indent=2)
        (REPORT / f"workspace_{case}.json").write_text(blob, encoding="utf-8")
        (REPORT / f"workspace_{case}.txt").write_text(_render_txt(case, char, user, messages),
                                                      encoding="utf-8")
        row = {"case": case, "char": char, "messages": len(messages),
               "roles": [m["role"] for m in messages],
               "system_chars": sum(len(m["content"]) for m in messages if m["role"] == "system"),
               "sha256": hashlib.sha256(blob.encode("utf-8")).hexdigest()}
        index.append(row)
        print(f"[dump_ws] {case:<34} msgs={row['messages']:>2} system={row['system_chars']:>6} "
              f"sha={row['sha256'][:12]}")
    (REPORT / "workspace_dump_index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[dump_ws] {len(index)} 例 -> {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
