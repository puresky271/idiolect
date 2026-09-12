"""turn_logic 效果 A/B：同一夹具，两臂只差「命中场景时注入的 turn_logic 块」。

指标选择（按能测性）：
  · filler_short（≤4 字回合占比）—— 最可能被场景模块改善的指标：
    乐奈在吉他/猫场景若只答「嗯。」就是失败，模块应把它推进到给具体物
  · anchor_density（每百字锚点数）
  · composite（综合分，对金标准分布）

为什么不用 nominal_start / le6：见 report/power_calc.json，
那两个指标在可承受样本量下只能分辨 ≥10pp，而场景模块的预期效应更小。

用法：
  py -X utf8 scene_ab.py --runs 10
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
import os
import statistics
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[2]))

import llm_nothink_patch  # noqa: E402,F401
import idiolect.scene_engine as engine  # noqa: E402
import probe_runner as P  # noqa: E402
import style_features as S  # noqa: E402
from idiolect.registry import render_turn_special_block  # noqa: E402

REPORT = REPORT
# (角色, user_text, 是否应命中场景)
SCENES = [
    ("乐奈", "我的吉他弦断了", True),
    ("乐奈", "排练的时候一弦突然断了，好烦", True),
    ("乐奈", "外面有只猫", True),
    ("乐奈", "要不要去吃抹茶芭菲", True),
    ("乐奈", "今天天气不错", False),
    ("素世", "你还记得以前那支乐队吗", True),
    ("素世", "要不要喝杯咖啡", True),
    ("素世", "今天午饭吃什么", False),
]
CHARS = ["乐奈", "素世"]


def metric(reply: str) -> dict:
    t = reply.strip()
    if not t:
        return {}
    return {
        "le4": 1.0 if len(t) <= 4 else 0.0,
        "anchor": S.anchor_density([t]),
        "len": float(len(t)),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=10)
    ap.add_argument("--max-tokens", type=int, default=420)
    args = ap.parse_args()

    client = P.make_client()
    model = os.environ.get("LLM_MODEL", "deepseek-flash")

    fixtures: dict[str, tuple[list[dict], int, str]] = {}
    for ch in CHARS:
        fx = P.load_fixture(ch)
        fixtures[ch] = (fx, P.find_last_user_idx(fx), fx[0]["content"])

    rows: list[dict] = []
    for char, user_text, should_hit in SCENES:
        fx, ui, base_sys = fixtures[char]
        # after 臂：注入生产 turn_logic 块
        engine.reset_session()
        tl = render_turn_special_block(char, user_text, session_id=f"ab:{char}:{user_text[:8]}",
                                      is_developer=False)
        for arm in ("before", "after"):
            sysmsg = base_sys if arm == "before" else (base_sys + ("\n\n" + tl if tl else ""))
            for k in range(args.runs):
                msgs = json.loads(json.dumps(fx))
                msgs[0]["content"] = sysmsg
                msgs[ui]["content"] = user_text
                try:
                    r = client.chat.completions.create(
                        model=model, messages=msgs, temperature=0.75,
                        max_tokens=args.max_tokens,
                        extra_body={"thinking": {"type": "disabled"}},
                    )
                    raw = (r.choices[0].message.content or "").strip()
                except Exception as exc:  # noqa: BLE001
                    raw = ""
                    print(f"  ERR {type(exc).__name__}")
                cleaned, _ = P.RC.clean_reply(raw)
                cleaned = P.RC.normalize_nicknames(char, cleaned)
                rows.append({"char": char, "user_text": user_text, "arm": arm, "k": k,
                             "hit": should_hit, "tl_len": len(tl),
                             "reply": cleaned, "metric": metric(cleaned)})
        got = sum(1 for r in rows if r["char"] == char and r["user_text"] == user_text
                  and r["arm"] == "after")
        print(f"  [{char}] {user_text[:24]:<26} tl_len={len(tl):<5} runs={got}")

    # 统计
    print(f"\n=== turn_logic 效果（{args.runs} 次/臂/场景）===\n")
    print(f"{'指标':<14}{'before':>10}{'after':>10}{'差':>10}{'SE':>9}{'z':>7}{'显著?':>8}")
    print("-" * 70)
    summary = {}
    for key in ("le4", "anchor", "len"):
        A, B = [], []
        for r in rows:
            if not r["metric"]:
                continue
            (A if r["arm"] == "before" else B).append(r["metric"][key])
        if len(A) < 3 or len(B) < 3:
            continue
        ma, mb = statistics.fmean(A), statistics.fmean(B)
        sa, sb = statistics.stdev(A), statistics.stdev(B)
        se = math.sqrt(sa ** 2 / len(A) + sb ** 2 / len(B))
        z = (mb - ma) / se if se else 0.0
        sig = "是" if abs(z) > 1.96 else "否"
        print(f"{key:<14}{ma:>10.3f}{mb:>10.3f}{mb - ma:>+10.3f}{se:>9.3f}{z:>7.2f}{sig:>8}")
        summary[key] = {"before": round(ma, 4), "after": round(mb, 4), "diff": round(mb - ma, 4),
                        "se": round(se, 4), "z": round(z, 2), "significant": abs(z) > 1.96,
                        "n_before": len(A), "n_after": len(B)}

    # 分场景看（只看命中场景）
    print("\n=== 分场景（命中场景）le4 与 anchor ===")
    print(f"{'角色':<6}{'user_text':<26}{'le4 b→a':>12}{'anchor b→a':>14}{'len b→a':>12}")
    print("-" * 74)
    per = defaultdict(lambda: {"before": [], "after": []})
    for r in rows:
        if r["hit"] and r["metric"]:
            per[(r["char"], r["user_text"])][r["arm"]].append(r["metric"])
    for (char, ut), d in per.items():
        if not d["before"] or not d["after"]:
            continue
        f = lambda arm, k: statistics.fmean([x[k] for x in d[arm]])
        print(f"{char:<6}{ut[:24]:<26}{f('before','le4'):>6.2f}→{f('after','le4'):<5.2f}"
              f"{f('before','anchor'):>7.2f}→{f('after','anchor'):<6.2f}"
              f"{f('before','len'):>6.1f}→{f('after','len'):<5.1f}")

    (REPORT / "scene_turn_logic_ab.json").write_text(
        json.dumps({"runs": args.runs, "summary": summary,
                    "rows": [{k: v for k, v in r.items() if k != "reply"} for r in rows]},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    (REPORT / "scene_turn_logic_ab.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    print(f"\n-> report/scene_turn_logic_ab.json / .jsonl")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
