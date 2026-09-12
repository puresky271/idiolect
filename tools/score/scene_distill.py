"""逐场景蒸馏评分：probe 输出 vs **该角色该场景**的原作基线。

这是「蒸馏」的对齐实现（用户 2026-09-11 指出的方法论根本）：
  参照物 = 原作里同一角色在**同一场景**下真说了什么
  （`scene_char_baseline.json`，130 个 (char,scene) 组合）
  而不是我自造的违规模式、也不是该角色的全局分布。

评分维度（都直接对齐原作基线）：
  · len_ratio     输出中位字长 / 原作同场景中位字长
  · len_p90_ratio 输出 p90 / 原作同场景 p90
  · sent_ratio    输出句数 / 原作同场景句数
  · anchor_ratio  输出锚点密度 / 原作同场景锚点密度（**只作诊断列，不进复合分**）
  · distill       复合分 = 1 − 加权偏离（长度 2 / p90 1 / 句数 1.5），1.0 = 与原作同场景一致
  · excess        **相对分**：本场景的总偏离 − 该角色在本次 run 所有场景的平均总偏离。
                  正值 = 这个场景比她自己平时更跑偏 → 排优先级就看这个。

⚠️ 2026-09-12 把 anchor 移出复合分：`anchor_density` 是 hits/chars 的比值，
  在**短句为主**的场景 cell 里分母极小，实测基线在 0.19~3.48 之间乱跳
  （素世 play_along 0.254 vs 素世全局 1.27），而模型输出稳定在 4.0~4.4
  → 几乎每个场景的 anchor 偏离都顶到 dev 上限，变成**恒定惩罚**，
  13 个场景里有 7 个被它压成 0.000、失去区分度。
  anchor 本身仍有信息（模型每百字锚点 4.04~4.38 vs 原作 1.83 ≈ 2.3 倍），
  但那是**全局结论**，不是场景间的区分量 —— 所以降级为诊断列。

产出 report/scene_distill.md / .json / scene_distill_<label>.json
"""
from __future__ import annotations

# ── idiolect 路径引导（可移植）：仓库根 + 各 tools 子目录上 sys.path ──
import sys as _sys
from pathlib import Path as _Path
_ROOT = _Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "tools",
           *(_ROOT / "tools" / _d for _d in ("corpus", "distill", "probe", "score", "gates"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))
from _paths import CORPUS_DIR, DATA, REPORT, ROOT  # noqa: E402,F401

import argparse
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import style_features as S  # noqa: E402

REPORT = REPORT
CHARS = ["爱音", "素世", "灯", "立希", "乐奈"]


def load_baseline() -> dict:
    return json.loads((DATA / "scene_char_baseline.json").read_text(encoding="utf-8"))




def global_baseline(char: str) -> dict | None:
    """scene 为空的夹具（生活化 / 个人钩子）用**角色全局基线**评分。

    26 场景体系里没有「日常闲聊」「canon 钩子」这类 key；但这两组夹具仍有观测价值，
    所以退回 `turn_agents.prompt_cards.STYLE_TARGETS` 的角色全局中位/p90/句数。
    anchor_density 用全语料实测均值 1.8 占位（诊断列，不进复合分）。
    """
    try:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from idiolect.style_target import STYLE_TARGETS  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return None
    t = STYLE_TARGETS.get(char)
    if not t:
        return None
    return {
        "n": 0,
        "scene": "(全局)",
        "length": {"p50": float(t["median_chars"]), "p90": float(t["p90_chars"])},
        "n_sent": {"mean": float(t["sent_per_turn"])},
        "anchor_density": 1.8,
    }


def ratio(a: float, b: float) -> float | None:
    if not b:
        return None
    return a / b


def dev(a: float, b: float) -> float:
    """偏离度（对数对称，上限 2.0）。

    ⚠️ 两个边界必须显式处理，否则会给"完全一致"的维度判满额偏离：
      · 两者都为 0 → 一致，偏离 0（初版漏了这个，anchor 维度把多数场景无端扣分）
      · 一方为 0 一方非 0 → 真偏离，给 1.0
    """
    if not a and not b:
        return 0.0
    if not a or not b:
        return 1.0
    return min(abs(math.log2(a / b)), 2.0)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", required=True, help="probe 轮次（逗号分隔）")
    args = ap.parse_args()

    base = load_baseline()
    lines = ["# 逐场景蒸馏评分：输出 vs 原作同场景基线\n",
             "> 参照物 = **同一角色在同一场景**下的原作台词分布（130 个组合）",
             "> 各列为「输出 / 原作」原值；蒸馏分 1.0 = 与原作同场景分布一致\n"]

    for label in [x for x in args.labels.split(",") if x]:
        p = REPORT / f"probe_{label}.jsonl"
        if not p.exists():
            continue
        rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
        per: dict[tuple[str, str], list[str]] = defaultdict(list)
        for r in rows:
            # scene 为空的夹具（生活化 / 个人钩子）也要收 —— 它们走 global_baseline 回退
            if r.get("reply") and r.get("scene") is not None:
                per[(r["char"], r.get("scene") or "")].append(r["reply"])

        scored = []
        for (char, scene), replies in sorted(per.items()):
            key = f"{char}|{scene}"
            b = base.get(key)
            if not b and not scene:
                b = global_baseline(char)
            if not b or not replies:
                continue
            prof = S.profile_from_texts(replies, "cn")
            if not prof.get("n"):
                continue
            out_med = prof["length"]["p50"]
            out_p90 = prof["length"]["p90"]
            out_sent = prof["n_sent"]["mean"]
            out_anchor = S.anchor_density(replies)
            r_len = ratio(out_med, b["length"]["p50"])
            r_p90 = ratio(out_p90, b["length"]["p90"])
            r_sent = ratio(out_sent, b["n_sent"]["mean"])
            r_anchor = ratio(out_anchor, b["anchor_density"])
            d_len = dev(out_med, b["length"]["p50"])
            d_p90 = dev(out_p90, b["length"]["p90"])
            d_sent = dev(out_sent, b["n_sent"]["mean"])
            d_anchor = dev(out_anchor, b["anchor_density"])
            # 复合分：只用稳定三维（长度 2 / p90 1 / 句数 1.5，权重和 4.5）
            d = (2.0 * d_len + 1.0 * d_p90 + 1.5 * d_sent) / 4.5
            distill = round(max(0.0, 1.0 - d), 3)
            scored.append({
                "char": char, "scene": scene or "(全局)", "n": prof["n"],
                "out_med": out_med, "base_med": b["length"]["p50"],
                "r_len": round(r_len, 2) if r_len else None,
                "out_p90": out_p90, "base_p90": b["length"]["p90"],
                "r_p90": round(r_p90, 2) if r_p90 else None,
                "out_sent": round(out_sent, 2), "base_sent": round(b["n_sent"]["mean"], 2),
                "r_sent": round(r_sent, 2) if r_sent else None,
                "out_anchor": round(out_anchor, 2), "base_anchor": b["anchor_density"],
                "r_anchor": round(r_anchor, 2) if r_anchor else None,
                "dev_len": round(d_len, 3), "dev_p90": round(d_p90, 3),
                "dev_sent": round(d_sent, 3), "dev_anchor": round(d_anchor, 3),
                "dev_total": round(d, 3),
                "distill": distill,
            })

        # 相对分：减去「该角色在本次 run 的平均偏离」→ 挑出她自己最跑偏的场景
        by_char_dev: dict[str, list[float]] = defaultdict(list)
        for s in scored:
            by_char_dev[s["char"]].append(s["dev_total"])
        char_mean = {c: statistics.fmean(v) for c, v in by_char_dev.items()}
        for s in scored:
            s["char_mean_dev"] = round(char_mean[s["char"]], 3)
            s["excess"] = round(s["dev_total"] - char_mean[s["char"]], 3)
        scored.sort(key=lambda x: -x["excess"])
        lines.append(f"\n## `{label}`\n")
        lines.append("按 **excess**（本场景总偏离 − 该角色平均总偏离）降序 —— 越靠前＝越该优先治。\n")
        lines.append("| 角色 | 场景 | n | excess | 蒸馏分 | 中位(出/原) | p90(出/原) | 句数(出/原) | 锚点(出/原)* |")
        lines.append("|---|---|---|---|---|---|---|---|---|")
        for s in scored:
            def pair(o, bb, r):
                return f"{o} / {bb} ({r}×)" if r is not None else f"{o} / {bb}"
            lines.append(
                f"| {s['char']} | `{s['scene']}` | {s['n']} | {s['excess']:+.3f} | **{s['distill']}** | "
                f"{pair(s['out_med'], s['base_med'], s['r_len'])} | "
                f"{pair(s['out_p90'], s['base_p90'], s['r_p90'])} | "
                f"{pair(s['out_sent'], s['base_sent'], s['r_sent'])} | "
                f"{pair(s['out_anchor'], s['base_anchor'], s['r_anchor'])} |")
        if scored:
            mean_d = statistics.fmean(s["distill"] for s in scored)
            over = sum(1 for s in scored if (s["r_len"] or 0) > 1.2)
            under = sum(1 for s in scored if (s["r_len"] or 9) < 0.8)
            lines.append("\n\\* 锚点列**不进复合分**（分母不稳，见模块 docstring），只作诊断。")
            lines.append(f"\n**均值 {mean_d:.3f}**（{len(scored)} 个场景）")
            lines.append(f"\n长度方向：比原作长 >1.2× 的 {over} 个｜比原作短 <0.8× 的 {under} 个")
            all_anchor = statistics.fmean(s["out_anchor"] for s in scored)
            base_anchor = statistics.fmean(s["base_anchor"] for s in scored)
            if base_anchor:
                lines.append(f"\n锚点密度（诊断）：输出 {all_anchor:.2f} / 原作 {base_anchor:.2f} "
                             f"= **{all_anchor / base_anchor:.1f}×**")
            byc: dict[str, list[float]] = defaultdict(list)
            for s in scored:
                byc[s["char"]].append(s["distill"])
            lines.append("\n按角色：" + "｜".join(
                f"{c} {statistics.fmean(v):.3f}" for c, v in sorted(byc.items(), key=lambda kv: -statistics.fmean(kv[1]))))

        (REPORT / f"scene_distill_{label}.json").write_text(
            json.dumps(scored, ensure_ascii=False, indent=2), encoding="utf-8")

    (REPORT / "scene_distill.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
