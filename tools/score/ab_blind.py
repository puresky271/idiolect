"""A/B 盲评：两臂回复按夹具配对、随机左右，给人或 LLM 做「哪个更像角色」的判决。

为什么存在（2026-09-13 外部方法论评审）：锚点密度这种词表命中太粗，
内容维度需要正交信号——至少做 A/B 双盲（人读），更好是 LLM-as-judge 双盲。
机械指标（composite/distill）与盲评结论互相独立，两个方向互相印证才算数。

三种模式：
  1. 出题（默认）：生成盲评 worksheet + 答案映射 key
       py -X utf8 tools/score/ab_blind.py --a gen_off2 --b gen_on10
     产物：report/ab_blind_<a>_vs_<b>.md（不含臂名）+ …_key.json（判卷用映射）
  2. 判卷：人工答完（{item_id: "left"|"right"|"tie"}）后统胜率
       py -X utf8 tools/score/ab_blind.py --tally 答卷.json --key …_key.json
  3. LLM 判卷：--llm 逐对随机呈现顺序（防位置偏置），judge 只看「哪段更像该角色」
       py -X utf8 tools/score/ab_blind.py --a … --b … --llm
     ⚠️ 局限：judge 与被判方若是同一模型，结论是循环论证的弱信号——
     只作正交参考，**不进机械门禁**（门禁走 accept_check.py 的四条独立指标）。

确定性：左右顺序由 idiolect._text_rng 按 (a, b, 角色, 夹具, k) 定种——
同输入永远同序，判卷映射才可复现（与后处理的定种纪律一致）。
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
import os  # noqa: E402
import sys  # noqa: E402

from idiolect._text_rng import seeded_rng  # noqa: E402


def load_cells(label: str) -> dict[tuple[str, str], list[dict]]:
    """读 probe_<label>.jsonl，按 (char, scenario) 分组，组内按 k 排序。"""
    p = REPORT / f"probe_{label}.jsonl"
    if not p.exists():
        raise SystemExit(f"[stop] 找不到 {p}——先跑 probe_runner --label {label}")
    cells: dict[tuple[str, str], list[dict]] = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("reply") and not r.get("error"):
            cells.setdefault((r.get("char", ""), r.get("scenario", "")), []).append(r)
    for reps in cells.values():
        reps.sort(key=lambda r: r.get("k", 0))
    return cells


def build_pairs(a: str, b: str) -> list[dict]:
    """两臂按夹具配对；每对用定种 RNG 决定左右（防呈现顺序泄漏臂信息）。"""
    ca, cb = load_cells(a), load_cells(b)
    pairs: list[dict] = []
    for key in sorted(set(ca) & set(cb)):
        char, scenario = key
        for i, (ra, rb) in enumerate(zip(ca[key], cb[key])):
            k = ra.get("k", i)
            a_left = seeded_rng(f"ab_blind|{a}|{b}|{char}|{scenario}|{k}").random() < 0.5
            pairs.append({
                "char": char, "scenario": scenario, "k": k,
                "left_arm": a if a_left else b, "right_arm": b if a_left else a,
                "left": ra["reply"] if a_left else rb["reply"],
                "right": rb["reply"] if a_left else ra["reply"],
            })
    only_a = len(set(ca) - set(cb))
    only_b = len(set(cb) - set(ca))
    if not pairs:
        raise SystemExit(f"[stop] {a} 与 {b} 没有共同 (角色, 夹具) 格可配对")
    if only_a or only_b:
        print(f"[ab_blind] 注意：仅 {a} 有的格 {only_a} 个、仅 {b} 有的格 {only_b} 个，已跳过",
              flush=True)
    return pairs


def write_worksheet(a: str, b: str, pairs: list[dict]) -> tuple[str, str]:
    """出题：worksheet 不含任何臂名；key 记录左右 ↔ 臂的映射。"""
    items: dict[str, dict] = {}
    lines = ["# 盲评 worksheet",
             "",
             f"- 共 {len(pairs)} 对。每对选「左 / 右 / 平」——标准只有一个：**哪段更像这个角色本人会说的话**。",
             "- 判完后存成 `{item_id: \"left\"|\"right\"|\"tie\"}` 的 JSON，"
             "用 `--tally 答卷.json --key <key文件>` 判卷。",
             ""]
    for i, p in enumerate(pairs, 1):
        item_id = f"i{i:04d}"
        items[item_id] = {"char": p["char"], "scenario": p["scenario"], "k": p["k"],
                          "left_arm": p["left_arm"], "right_arm": p["right_arm"]}
        lines += [f"## {item_id} ｜ 角色：{p['char']} ｜ 夹具：{p['scenario']}",
                  "",
                  f"- 左：{p['left']}",
                  f"- 右：{p['right']}",
                  ""]
    ws = REPORT / f"ab_blind_{a}_vs_{b}.md"
    key = REPORT / f"ab_blind_{a}_vs_{b}_key.json"
    ws.write_text("\n".join(lines) + "\n", encoding="utf-8")
    key.write_text(json.dumps({"a": a, "b": b, "items": items}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"[ab_blind] {len(pairs)} 对 -> {ws.name}（答题用）+ {key.name}（判卷 key，评前勿看）")
    return str(ws), str(key)


def tally(answers_path: str, key_path: str) -> int:
    """判卷：把 left/right/tie 按 key 翻回臂名，统胜率。"""
    answers = json.loads(open(answers_path, encoding="utf-8").read())
    key = json.loads(open(key_path, encoding="utf-8").read())
    items = key["items"]
    unknown = [i for i in answers if i not in items]
    if unknown:
        print(f"[ab_blind] 答卷里有 key 之外的 item：{unknown[:5]}", file=sys.stderr)
        return 2
    wins = {key["a"]: 0.0, key["b"]: 0.0}
    n = 0
    for item_id, choice in answers.items():
        m = items[item_id]
        if choice == "left":
            wins[m["left_arm"]] += 1.0
        elif choice == "right":
            wins[m["right_arm"]] += 1.0
        elif choice == "tie":
            wins[m["left_arm"]] += 0.5
            wins[m["right_arm"]] += 0.5
        else:
            print(f"[ab_blind] {item_id} 的答案 {choice!r} 非法（left/right/tie）", file=sys.stderr)
            return 2
        n += 1
    if not n:
        print("[ab_blind] 答卷是空的", file=sys.stderr)
        return 2
    print(f"[ab_blind] 判卷 {n} 题：")
    for arm, w in sorted(wins.items(), key=lambda kv: -kv[1]):
        print(f"  {arm} {w:.1f} 胜 / {n} 题（胜率 {w / n * 100:.0f}%）")
    out = _Path(answers_path).with_name(_Path(answers_path).stem + "_tally.json")
    out.write_text(json.dumps({"n": n, "wins": wins}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  -> {out.name}")
    return 0


JUDGE_PROMPT = """你是角色扮演评审。角色：{char}（《BanG Dream! It's MyGO!!!!!》）。
下面两段是对同一条消息的两种候选回复。判断标准只有一个：**哪段更像这个角色本人会说的话**
（语气、口癖、长度感、具体性；不要奖励客套与正确的废话）。

左：{left}
右：{right}

只输出 JSON：{{"winner": "left"|"right"|"tie", "reason": "一句话"}}"""


def llm_judge(a: str, b: str, pairs: list[dict]) -> int:
    """LLM 判卷。左右顺序沿用出题时的定种随机（每对独立，防位置偏置）。"""
    import secrets_loader  # noqa: PLC0415

    secrets_loader.sync_env_from_secrets()
    from openai import OpenAI  # noqa: PLC0415

    key = os.environ.get("LLM_API_KEY") or ""
    if not key:
        raise SystemExit("[stop] LLM_API_KEY 为空——--llm 需要密钥（见 tools/secrets_loader.py）")
    client = OpenAI(api_key=key, base_url=os.environ.get("LLM_BASE_URL") or "")
    model = os.environ.get("LLM_MODEL", "deepseek-flash")

    results = []
    wins = {a: 0.0, b: 0.0}
    for i, p in enumerate(pairs, 1):
        prompt = JUDGE_PROMPT.format(char=p["char"], left=p["left"], right=p["right"])
        try:
            resp = client.chat.completions.create(
                model=model, messages=[{"role": "user", "content": prompt}],
                temperature=0.0, max_tokens=200)
            text = (resp.choices[0].message.content or "").strip()
            body = text[text.find("{"): text.rfind("}") + 1]
            verdict = json.loads(body)
            winner = verdict.get("winner", "tie")
        except Exception as exc:  # noqa: BLE001
            verdict = {"winner": "tie", "reason": f"judge 调用失败：{exc}"}
            winner = "tie"
        if winner == "left":
            wins[p["left_arm"]] += 1.0
        elif winner == "right":
            wins[p["right_arm"]] += 1.0
        else:
            wins[p["left_arm"]] += 0.5
            wins[p["right_arm"]] += 0.5
        results.append({"item": f"i{i:04d}", **{k: p[k] for k in ("char", "scenario", "k")},
                        "winner": winner, "reason": verdict.get("reason", "")})
        print(f"[ab_blind] i{i:04d} {p['char']}/{p['scenario']}: {winner}", flush=True)

    n = len(pairs)
    print(f"[ab_blind] LLM 判卷 {n} 题（judge={model}；正交参考，不进机械门禁）：")
    for arm, w in sorted(wins.items(), key=lambda kv: -kv[1]):
        print(f"  {arm} {w:.1f} 胜 / {n} 题（胜率 {w / n * 100:.0f}%）")
    out = REPORT / f"ab_blind_{a}_vs_{b}_llm.json"
    out.write_text(json.dumps({"judge": model, "n": n, "wins": wins, "results": results},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  -> {out.name}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", default="", help="臂 A 的 probe label")
    ap.add_argument("--b", default="", help="臂 B 的 probe label")
    ap.add_argument("--tally", default="", help="判卷模式：人工答卷 JSON（item_id → left/right/tie）")
    ap.add_argument("--key", default="", help="判卷模式：出题时生成的 …_key.json")
    ap.add_argument("--llm", action="store_true", help="用 LLM 判卷代替人工（正交参考，不进门禁）")
    args = ap.parse_args()

    if args.tally:
        if not args.key:
            print("[ab_blind] --tally 需要同时给 --key", file=sys.stderr)
            return 2
        return tally(args.tally, args.key)

    if not args.a or not args.b:
        print("[ab_blind] 出题/LLM 判卷需要 --a 与 --b", file=sys.stderr)
        return 2
    pairs = build_pairs(args.a, args.b)
    if args.llm:
        return llm_judge(args.a, args.b, pairs)
    write_worksheet(args.a, args.b, pairs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
