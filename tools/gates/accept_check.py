"""验收门禁：before/after 两臂的**多指标独立判定**——任一退化即整体 FAIL。

为什么存在（2026-09-13 外部方法论评审）：此前所有验收压在一个复合分上，
而真实退化单指标抓不到——立希名词直出率 39%→62%（方向反了）是人工跑
_noun_initial.py 才发现的；「变冷淡刷分」也要靠中性对照场景才看得见。
教训：**长度、内容、复读、破功各有各的病灶，必须各留一个独立指标，
任一退化都让总分无法通过。**

五条指标（数据源都是 probe/probe_report 已落盘的产物，本脚本不再调 LLM）：
  · composite 均值   probe_<label>_summary.json   头号指标（风格 0.65 + 锚点 0.35），降 > 1.0 分判退化
  · 锚点密度         probe_<label>_summary.json   **合并计数**的泊松精确检验（单侧 5% 显著），
                                                   打印可检测下限；逐角色只作诊断列
  · distill 均值     scene_distill_<label>.json   逐场景长度分布贴合，降 > 0.02 判退化
  · 硬规则 V 级率    probe_<label>_summary.json   破功红线，升 > 1pp 判退化
  · 同格重复度       probe_<label>.jsonl 现场算    1 − distinct/n（逐格再平均），升 > 5pp 判退化

为什么锚点密度走「合并计数 + 泊松检验」（2026-09-13 复审 N6/N7 的合力）：
  · composite 的锚点项有封顶 min(ad/ref, 1)——对锚点天然饱和的角色（实测 3/5
    角色的 anchor_score ≈ 100），composite 退化为 0.65×fidelity + 常数，
    内容维度暂时失聪，所以必须有独立的内容退化看守。
  · 但 hits 是小整数计数（实测 repo_standalone 批次：每角色 2~19 次 / 21 条，
    爱音只有 2 次 → 相对标准误 71%）。固定百分比门槛 + 跨角色均值会被量级稀释
    （N6：素世 −25% 被均值 −3.4% 掩盖）；改「逐角色取最差」又等于取噪声极值
    （N7：空比较的误报率被推到 ~95%）。两条路在小计数下都不成立。
  · 唯一诚实的做法：合并全部角色的 hits/chars 做精确的泊松率比较
    （二项条件检验，零第三方依赖），显著性可控（误报 ≤ α），并把**可检测下限**
    打印出来——样本量不够就明说「无结论」，这是仓库自己的纪律（docs/00 §4.4）。
  · 逐角色数字照打（诊断列，无判定）：单角色退化靠人读，21 条/角色的量级
    任何机械门槛都既抓不准也躲不开噪声。

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


def anchor_counts_pooled(art: dict) -> tuple[int, int] | None:
    """合并全部角色的 (hits, chars)。summary 里没有计数（旧批次产物）时返回 None。"""
    hits = chars = 0
    found = False
    for s in art["summary"].get("summary", {}).values():
        if isinstance(s, dict) and "anchor_hits" in s and "anchor_chars" in s:
            hits += s["anchor_hits"]
            chars += s["anchor_chars"]
            found = True
    return (hits, chars) if found else None


def anchor_per_char(art: dict) -> dict[str, tuple[int, int]]:
    """逐角色 (hits, chars)——只作诊断列，不参与判定（小计数，见模块 docstring）。"""
    out: dict[str, tuple[int, int]] = {}
    for char, s in art["summary"].get("summary", {}).items():
        if isinstance(s, dict) and "anchor_hits" in s and "anchor_chars" in s and s["anchor_chars"]:
            out[char] = (s["anchor_hits"], s["anchor_chars"])
    return out


def poisson_decrease_pvalue(hits_b: int, chars_b: int, hits_a: int, chars_a: int) -> float:
    """单侧精确检验：after 的锚点率是否显著低于 before。

    条件检验（两泊松率比较的标准精确做法）：零假设两臂率相同，
    给定总命中 N = hits_a + hits_b，after 的命中数 ~ Binomial(N, p0)，
    p0 = chars_a / (chars_a + chars_b)（按曝光量加权）。math.comb 手算，
    不需要 scipy。N 到几百时浮点足够稳。
    """
    from math import comb

    n = hits_a + hits_b
    if n == 0 or not chars_a or not chars_b:
        return 1.0
    p0 = chars_a / (chars_a + chars_b)
    return sum(comb(n, k) * p0 ** k * (1 - p0) ** (n - k) for k in range(hits_a + 1))


def critical_drop(hits_b: int, chars_b: int, chars_a: int, alpha: float) -> float | None:
    """当前样本量下能判 FAIL 的最小相对降幅（5% 显著临界）。

    找不到（计数太少，任何降幅都不显著）返回 None——调用方照实打印「无结论」。
    """
    rate_b = hits_b / chars_b if chars_b else 0.0
    if not rate_b:
        return None
    best: int | None = None
    for k in range(hits_b + 1):
        if poisson_decrease_pvalue(hits_b, chars_b, k, chars_a) < alpha:
            best = k
        else:
            break
    if best is None:
        return None
    return 1.0 - (best / chars_a) / rate_b


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
    ap.add_argument("--alpha-anchor", type=float, default=0.05, help="锚点密度泊松检验的单侧显著性水平")
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
        # (指标名, before 值, after 值, 阈值, 方向: lower / higher, 单位)
        ("composite 均值", composite_mean(before), composite_mean(after), args.tol_composite, "lower", "分"),
        ("distill 均值", distill_mean(before), distill_mean(after), args.tol_distill, "lower", ""),
        ("硬规则 V 级率", hard_v_mean(before), hard_v_mean(after), args.tol_hard_v, "higher", ""),
        ("同格重复度", repeat_rate(before), repeat_rate(after), args.tol_repeat, "higher", ""),
    ]

    print(f"[accept_check] {args.before} → {args.after}（任一指标退化即整体 FAIL）")
    failed = False
    rows: list[str] = []
    for name, b, a, tol, direction, unit in checks:
        if b is None or a is None:
            rows.append(f"  [SKIP] {name}：数据缺失（before={b} after={a}）——"
                        f"缺证据不算通过，请补齐产物后重跑")
            failed = True
            continue
        delta = a - b
        regression = (delta < -tol) if direction == "lower" else (delta > tol)
        verdict = "FAIL" if regression else "PASS"
        failed = failed or regression
        rows.append(f"  [{verdict}] {name}：{b:.4g} → {a:.4g}（Δ {delta:+.4g}{unit}，容差 {tol:g}）")

    # 锚点密度单独成段：合并计数的泊松精确检验（小计数的教训，见模块 docstring N6/N7 段）
    cb = anchor_counts_pooled(before)
    ca = anchor_counts_pooled(after)
    if cb is None or ca is None:
        anchor_row = ("  [SKIP] 锚点密度（合并泊松检验）：summary 里没有 anchor_hits/anchor_chars"
                      "（旧批次产物？重跑 probe_runner 再验收）——缺证据不算通过")
        failed = True
    else:
        hb, xb = cb
        ha, xa = ca
        p = poisson_decrease_pvalue(hb, xb, ha, xa)
        regression = p < args.alpha_anchor
        verdict = "FAIL" if regression else "PASS"
        failed = failed or regression
        rate_b = hb / xb * 100 if xb else 0.0
        rate_a = ha / xa * 100 if xa else 0.0
        mde = critical_drop(hb, xb, xa, args.alpha_anchor)
        mde_txt = (f"当前样本量可检测下限 ≈ 降 {mde:.0%}" if mde is not None
                   else "样本量过小，任何降幅都不显著（无结论）")
        anchor_row = (f"  [{verdict}] 锚点密度（合并泊松检验）：{rate_b:.2f} → {rate_a:.2f}"
                      f"（hits {hb}→{ha} / chars {xb}→{xa}，p={p:.3f}，α={args.alpha_anchor}；{mde_txt}）")
    # 打印顺序：composite 领衔，锚点其次，其余随后；逐角色锚点只作诊断
    print(rows[0])
    print(anchor_row)
    if cb is not None and ca is not None:
        pb, pa = anchor_per_char(before), anchor_per_char(after)
        diag = []
        for char in sorted(set(pb) & set(pa)):
            hb_, xb_ = pb[char]
            ha_, xa_ = pa[char]
            diag.append(f"{char} {hb_ / xb_ * 100:.2f}→{ha_ / xa_ * 100:.2f}"
                        f"（hits {hb_}→{ha_}）")
        if diag:
            print("      逐角色诊断（小计数，不参与判定）：" + "｜".join(diag))
    for row in rows[1:]:
        print(row)

    if failed:
        print("[accept_check] 整体 FAIL——先修退化项再谈收益（单指标绿灯不代表「更像」）")
        return 1
    print("[accept_check] 整体 PASS：五条指标无一退化")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
