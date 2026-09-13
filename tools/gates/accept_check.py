"""验收门禁：before/after 两臂的**多指标独立判定**——任一退化即整体 FAIL。

为什么存在（2026-09-13 外部方法论评审）：此前所有验收压在一个复合分上，
而真实退化单指标抓不到——立希名词直出率 39%→62%（方向反了）是人工跑
_noun_initial.py 才发现的；「变冷淡刷分」也要靠中性对照场景才看得见。
教训：**长度、内容、复读、破功各有各的病灶，必须各留一个独立指标，
任一退化都让总分无法通过。**

四条指标（数据源都是 probe/probe_report 已落盘的产物，本脚本不再调 LLM）：
  · composite 均值   probe_<label>_summary.json   头号指标（风格 0.65 + 锚点 0.35），降 > 1.0 分判退化
  · distill 均值     scene_distill_<label>.json   逐场景长度分布贴合，降 > 0.02 判退化
  · 硬规则 V 级率    probe_<label>_summary.json   破功红线，升 > 1pp 判退化
  · 同格重复度       probe_<label>.jsonl 现场算    1 − distinct/n（逐格再平均），升 > 5pp 判退化

阈值都可用命令行调（--tol-*）；判断口径「after 相对 before 退化」。
缺产物文件是 rc 2 的明确报错——半截证据不许当「通过」。

用法：
  py -X utf8 tools/gates/accept_check.py --before gen_off2 --after gen_on10
  py -X utf8 tools/gates/accept_check.py --before b1 --after a1 --tol-composite 2.0
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
from _paths import REPORT  # noqa: E402

import argparse  # noqa: E402
import json  # noqa: E402
import statistics  # noqa: E402
import sys  # noqa: E402


def _load_artifacts(label: str) -> dict:
    """读一个臂的三份产物；缺任何一份都是明确报错（rc 2 由调用方给出）。"""
    paths = {
        "jsonl": REPORT / f"probe_{label}.jsonl",
        "summary": REPORT / f"probe_{label}_summary.json",
        "distill": REPORT / f"scene_distill_{label}.json",
    }
    missing = [str(p) for p in paths.values() if not p.exists()]
    if missing:
        raise FileNotFoundError(
            f"臂 {label} 的产物不齐，缺：{'; '.join(missing)}。"
            f"先跑 probe_runner + probe_report（或 scene_distill）再验收。")
    rows = [json.loads(l) for l in paths["jsonl"].read_text(encoding="utf-8").splitlines() if l.strip()]
    return {
        "rows": rows,
        "summary": json.loads(paths["summary"].read_text(encoding="utf-8")),
        "distill": json.loads(paths["distill"].read_text(encoding="utf-8")),
    }


def composite_mean(art: dict) -> float | None:
    vals = [s["composite"] for s in art["summary"].get("summary", {}).values()
            if isinstance(s, dict) and "composite" in s]
    return statistics.fmean(vals) if vals else None


def hard_v_mean(art: dict) -> float | None:
    vals = [s["hard_v_rate"] for s in art["summary"].get("summary", {}).values()
            if isinstance(s, dict) and "hard_v_rate" in s]
    return statistics.fmean(vals) if vals else None


def distill_mean(art: dict) -> float | None:
    vals = [c["distill"] for c in art["distill"] if isinstance(c, dict) and "distill" in c]
    return statistics.fmean(vals) if vals else None


def repeat_rate(art: dict) -> float | None:
    """同格重复度：逐 (char, scenario) 格算 1 − distinct/n，再对格数平均。

    0 = 每条都不同；越大越复读。只统计 ≥2 条有效回复的格。
    """
    cells: dict[tuple[str, str], list[str]] = {}
    for r in art["rows"]:
        if r.get("reply") and not r.get("error"):
            cells.setdefault((r.get("char", ""), r.get("scenario", "")), []).append(r["reply"])
    rates = [1.0 - len(set(reps)) / len(reps) for reps in cells.values() if len(reps) >= 2]
    return statistics.fmean(rates) if rates else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", required=True, help="基线臂 label（改前）")
    ap.add_argument("--after", required=True, help="待验收臂 label（改后）")
    ap.add_argument("--tol-composite", type=float, default=1.0, help="composite 允许下降幅度（分）")
    ap.add_argument("--tol-distill", type=float, default=0.02, help="distill 均值允许下降幅度")
    ap.add_argument("--tol-hard-v", type=float, default=0.01, help="硬规则 V 级率允许上升幅度")
    ap.add_argument("--tol-repeat", type=float, default=0.05, help="同格重复度允许上升幅度")
    args = ap.parse_args()

    try:
        before = _load_artifacts(args.before)
        after = _load_artifacts(args.after)
    except FileNotFoundError as exc:
        print(f"[accept_check] 找不到验收产物：{exc}", file=sys.stderr)
        return 2

    checks = [
        # (指标名, before 值, after 值, 阈值, 方向: lower_is_regression / higher_is_regression, 单位)
        ("composite 均值", composite_mean(before), composite_mean(after), args.tol_composite, "lower", "分"),
        ("distill 均值", distill_mean(before), distill_mean(after), args.tol_distill, "lower", ""),
        ("硬规则 V 级率", hard_v_mean(before), hard_v_mean(after), args.tol_hard_v, "higher", ""),
        ("同格重复度", repeat_rate(before), repeat_rate(after), args.tol_repeat, "higher", ""),
    ]

    print(f"[accept_check] {args.before} → {args.after}（任一指标退化即整体 FAIL）")
    failed = False
    for name, b, a, tol, direction, unit in checks:
        if b is None or a is None:
            print(f"  [SKIP] {name}：数据缺失（before={b} after={a}）——"
                  f"缺证据不算通过，请补齐产物后重跑")
            failed = True
            continue
        delta = a - b
        regression = (delta < -tol) if direction == "lower" else (delta > tol)
        verdict = "FAIL" if regression else "PASS"
        failed = failed or regression
        print(f"  [{verdict}] {name}：{b:.4g} → {a:.4g}（Δ {delta:+.4g}{unit}，容差 {tol:g}）")

    if failed:
        print("[accept_check] 整体 FAIL——先修退化项再谈收益（单指标绿灯不代表「更像」）")
        return 1
    print("[accept_check] 整体 PASS：四条指标无一退化")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
