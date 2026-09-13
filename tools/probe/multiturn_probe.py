"""多轮风格漂移探针：n 轮自对话，逐轮记录锚点密度与长度，检验「越聊越不像」。

为什么存在（2026-09-13，Ditto 方法论移植）：WikiRoleEval 全程多轮；本仓库的探针
是「真实 dump + 替换末条 user」的**单轮**下一句测试——多轮累积漂移（越聊越长、
口癖稀释、逐渐助手化、聊深了开始出戏）是 prompt 工程的真实风险，此前没有测量。
probe_runner 的 composite 测的是静态分布拟合，测不到「第 1 轮和第 8 轮的差」。

设计：
  · 每角色一段固定的 user 剧本（`TURN_SCRIPT`，全部角色共用、逐字节固定），
    逐轮用 `build_messages(history=...)` 现场装配四层（turn_logic 按当轮 user
    分类；session 全程同一 id——per-session 去重语义与生产一致）。
  · **模型的回复进入它自己的上下文**——这正是要测的 self-reinforcement 路径。
  · 逐轮指标：锚点 hits/chars、中位字长、句数、OOB 审计（复用 oob_check——
    漂移的极端形态就是聊着聊着出戏）。
  · 漂移判定：前半段 vs 后半段的**合并计数泊松检验**（复用 accept_check 的
    实现，不重写第二份统计口径）。样本不足时照实打印「无结论」，不硬判——
    这是 docs/00 §4.4 的纪律。

用法：
  py -X utf8 tools/probe/multiturn_probe.py --label mt1                # 真跑（需 LLM_API_KEY）
  py -X utf8 tools/probe/multiturn_probe.py --label mt1 --dry-run      # 不调 LLM，验证装配
  py -X utf8 tools/probe/multiturn_probe.py --label mt1 --gate         # 漂移 FAIL 或 OOB 高危即 rc 1
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

import argparse
import json
import os
import time
from collections import defaultdict

from _paths import REPORT  # noqa: E402

import mock_clock as MOCK  # noqa: E402
import reply_clean as RC  # noqa: E402
import style_features as S  # noqa: E402
from accept_check import critical_drop, poisson_decrease_pvalue  # noqa: E402
from oob_check import audit_oob  # noqa: E402
from probe_runner import llm_extra_body, make_client  # noqa: E402

CHARS = ["爱音", "灯", "立希", "素世", "乐奈"]

# 固定剧本：日常闲聊八轮，不带 canon 敏感内容；逐字节固定才能跨批次比较。
# 第 7 轮的猫对乐奈是兴趣锚点、对别人是普通话题——故意保留，让剧本对全员通用。
TURN_SCRIPT = [
    "在吗？今天过得怎么样",
    "中午吃了什么",
    "周末有什么安排吗",
    "最近有在听什么歌吗",
    "今天有点累，不想动",
    "学校那边最近忙吗",
    "最近有看到那只猫吗",
    "好啦不早了，晚安",
]


def drift_verdict(hits: list[int], chars: list[int], alpha: float = 0.05) -> dict:
    """前半段 vs 后半段的锚点合并泊松检验。

    verdict：FAIL = 后半段显著塌方；PASS = 未检出显著下降；
    NO_DATA = 轮数/计数不足以做任何统计。`inconclusive` 标记「通过了但当前
    样本量连可检测下限都算不出来」——门禁照常放行，报告里必须带上这句。
    """
    n = len(hits)
    if n < 2 or sum(hits) == 0 or sum(chars) == 0:
        return {"verdict": "NO_DATA", "p": None, "inconclusive": True,
                "early": None, "late": None, "mde": None}
    mid = n // 2
    hb, xb = sum(hits[:mid]), sum(chars[:mid])
    ha, xa = sum(hits[mid:]), sum(chars[mid:])
    p = poisson_decrease_pvalue(hb, xb, ha, xa)
    mde = critical_drop(hb, xb, xa, alpha)
    return {"verdict": "FAIL" if p < alpha else "PASS",
            "p": p, "inconclusive": mde is None and p >= alpha,
            "early": [hb, xb], "late": [ha, xa], "mde": mde}


def run_char(char: str, label: str, *, runs_client, model: str, extra_body: dict,
             temperature: float, max_tokens: int, dry_run: bool) -> list[dict]:
    """跑一个角色的 n 轮自对话，返回逐轮记录。LLM 出错即中断该角色（对话已断）。"""
    from idiolect.assemble import build_messages

    history: list[dict] = []
    rows: list[dict] = []
    for t, user_text in enumerate(TURN_SCRIPT, start=1):
        msgs = build_messages(char, user_text, history=history,
                              session_id=f"multiturn:{label}:{char}", now=MOCK.mock_now())
        if len(msgs[0]["content"]) < 1000:
            raise SystemExit(f"[mt] system 段只有 {len(msgs[0]['content'])} 字符——装配没生效。")
        if dry_run:
            text, err, sec = "", "DRY_RUN", 0.0
        else:
            t0 = time.time()
            try:
                resp = runs_client.chat.completions.create(
                    model=model, messages=msgs, temperature=temperature,
                    max_tokens=max_tokens, extra_body=extra_body)
                text = (resp.choices[0].message.content or "").strip()
                err = "" if text else "EMPTY_CONTENT"
            except Exception as exc:  # noqa: BLE001
                text, err = "", f"{type(exc).__name__}: {exc}"
            sec = round(time.time() - t0, 1)
        cleaned, cinfo = RC.clean_reply(text)
        feat = S.turn_features(cleaned, "cn") if (cleaned and not err) else None
        hits, nchars = S.anchor_hits_chars([cleaned]) if (cleaned and not err) else (0, 0)
        # 全程 unarmed：TURN_SCRIPT 没有 NSFW 轮次；若未来加入越界轮次须传 risk_dims
        audit = audit_oob(cleaned, char) if (cleaned and not err) else None
        rows.append({
            "char": char, "turn": t, "scenario": f"turn{t}", "cat": "multiturn",
            "arm": "multiturn", "user": user_text,
            "reply": cleaned, "reply_raw": text, "clean": cinfo, "error": err, "sec": sec,
            "prompt_chars": len(msgs[0]["content"]),
            "length": feat.length if feat else 0,
            "n_sent": feat.n_sent if feat else 0,
            "anchor_hits": hits, "anchor_chars": nchars,
            "oob": ({"features": audit.features_hit, "high": audit.high_hit} if audit else {}),
        })
        if not dry_run and err:
            print(f"[mt]   turn{t}: ERR {err}——中断 {char} 的对话", flush=True)
            break
        history.append({"role": "user", "content": user_text})
        if cleaned:
            history.append({"role": "assistant", "content": cleaned})
        if not dry_run:
            oob_tag = f" ⚠{'、'.join(audit.features_hit)}" if audit and audit.features_hit else ""
            print(f"[mt]   turn{t}: len={feat.length if feat else 0} "
                  f"hits={hits} {text[:48]!r}{oob_tag}", flush=True)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--chars", default="", help="只跑指定角色（逗号分隔）")
    ap.add_argument("--dry-run", action="store_true", help="不调 LLM，只验证逐轮装配")
    ap.add_argument("--temperature", type=float, default=0.75)
    ap.add_argument("--max-tokens", type=int, default=420)
    ap.add_argument("--thinking", choices=["on", "off", "default"], default="off")
    ap.add_argument("--alpha", type=float, default=0.05, help="漂移泊松检验的单侧显著性水平")
    ap.add_argument("--gate", action="store_true", help="漂移 FAIL 或 OOB 高危命中即 rc 1")
    args = ap.parse_args()

    only = {c for c in args.chars.split(",") if c}
    out_jsonl = REPORT / f"multiturn_{args.label}.jsonl"
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)

    client = None if args.dry_run else make_client()
    model = os.environ.get("LLM_MODEL", "deepseek-flash")
    extra_body = llm_extra_body(args.thinking)
    print(f"[mt] label={args.label} turns={len(TURN_SCRIPT)} model={model} "
          f"thinking={args.thinking} dry={args.dry_run}", flush=True)
    print(f"[mt] 时钟 = {MOCK.describe()}", flush=True)

    all_rows: list[dict] = []
    for char in CHARS:
        if only and char not in only:
            continue
        print(f"[mt] {char} 开始自对话", flush=True)
        all_rows.extend(run_char(char, args.label, runs_client=client, model=model,
                                 extra_body=extra_body, temperature=args.temperature,
                                 max_tokens=args.max_tokens, dry_run=args.dry_run))

    with out_jsonl.open("w", encoding="utf-8") as fh:
        for r in all_rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    # 聚合：逐角色漂移判定 + OOB 高危计数
    by_char: dict[str, list[dict]] = defaultdict(list)
    for r in all_rows:
        if not r["error"] or r["error"] == "DRY_RUN":
            by_char[r["char"]].append(r)
    summary: dict[str, dict] = {}
    oob_high_total = 0
    for char, rows in by_char.items():
        hits = [r["anchor_hits"] for r in rows]
        nchars = [r["anchor_chars"] for r in rows]
        dv = drift_verdict(hits, nchars, alpha=args.alpha)
        oob_high = sum(1 for r in rows if r["oob"].get("high"))
        oob_high_total += oob_high
        lens = [r["length"] for r in rows if r["anchor_chars"]]
        summary[char] = {
            "turns": len(rows),
            "per_turn": [{"turn": r["turn"], "length": r["length"], "n_sent": r["n_sent"],
                          "anchor_hits": r["anchor_hits"], "anchor_chars": r["anchor_chars"],
                          "oob_features": r["oob"].get("features", [])} for r in rows],
            "drift": dv, "oob_high": oob_high,
            "len_first_half": (sum(lens[:len(lens) // 2]) / max(1, len(lens) // 2)) if lens else 0,
            "len_second_half": (sum(lens[len(lens) // 2:]) / max(1, len(lens) - len(lens) // 2)) if lens else 0,
        }
    (REPORT / f"multiturn_{args.label}_summary.json").write_text(
        json.dumps({"label": args.label, "kind": "multiturn",
                    "turns": len(TURN_SCRIPT), "summary": summary},
                   ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n[mt] -> {out_jsonl.name}")
    for char, s in summary.items():
        dv = s["drift"]
        if dv["verdict"] == "NO_DATA":
            drift_txt = "锚点计数为 0（无结论）"
        else:
            rate_e = dv["early"][0] / dv["early"][1] * 100 if dv["early"][1] else 0
            rate_l = dv["late"][0] / dv["late"][1] * 100 if dv["late"][1] else 0
            mde = (f"，可检测下限 ≈ 降 {dv['mde']:.0%}" if dv["mde"] is not None
                   else "，样本量过小（无结论）")
            drift_txt = (f"锚点 {rate_e:.2f} → {rate_l:.2f} /百字（p={dv['p']:.3f}{mde}）")
        print(f"  {char}：{drift_txt}｜字长 {s['len_first_half']:.0f} → {s['len_second_half']:.0f}"
              f"｜OOB 高危 {s['oob_high']}")

    if args.gate:
        failed = [c for c, s in summary.items() if s["drift"]["verdict"] == "FAIL"]
        if failed:
            print(f"[mt] FAIL：漂移显著塌方 {'、'.join(failed)}")
            return 1
        if oob_high_total:
            print(f"[mt] FAIL：多轮中出现 OOB 高危命中 {oob_high_total} 条")
            return 1
        inconclusive = [c for c, s in summary.items() if s["drift"]["inconclusive"]]
        note = f"（注意：{'、'.join(inconclusive)} 的样本量不足以检测漂移）" if inconclusive else ""
        print(f"[mt] PASS：无显著漂移、无 OOB 高危{note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
