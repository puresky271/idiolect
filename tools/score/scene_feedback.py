"""逐场景「真实 LLM 回复 vs 原作台词」对照反馈。

这是用户 2026-09-12 要求的闭环：**不是只看分数**，而是把
「模型这一轮真说了什么」和「原作里同一角色在同一场景真说了什么」并排放在一起看。

与 `scene_distill.py` 的分工：
  · `scene_distill` 给分布级评分（中位/p90/句数的比值 + excess 相对分）
  · 本脚本给**可读的对照**：原作句 / 模型句并排 + 每角色的判语

参照物两种，都列出（`affection` 两种口径差别很大，正好用来说明为什么）：
  · `检索` = `scene_char_baseline.json` 的原型近邻 top-40 里的前若干条
  · `锚定` = 该场景的**反应词典子集**（`affection_reference.py`），更贴题

用法：
  py -X utf8 scene_feedback.py --scene affection --labels aff_before,aff_after --n 8
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
from _paths import CORPUS_DIR, DATA, REPORT, ROOT  # noqa: E402,F401

import argparse
import json
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
REPORT = REPORT

CHARS = {"tomori": "灯", "anon": "爱音", "rana": "乐奈", "soyo": "素世", "taki": "立希"}

# 场景 → 反应词典（锚定参照物用；目前只做了 affection）
ANCHOR_RX = {
    "affection": re.compile(r"(突然|怎么了|干嘛|干什么|说什么|为什么要|搞什么|别突然|你这话)"),
    "affection_short": re.compile(r"^(诶|欸|哈|啊|呃|唔|咦)[？?！!—~～…]"),
}

# 话题 → 原作台词取词正则（2026-09-12 新增，供 turn_logic 深模块用）。
# 为什么需要：深模块的话题（家 / 吹奏乐社 / 外婆 / 午睡 / 有趣 / 猫）在 26 场景体系里
# 大多没有对应 key，`scene_char_baseline.json` 给不出「原作同场景台词」。
# 这里直接按**话题词**从金标准语料取同一角色的原句——同样是「原作真说过的」。
TOPIC_RX = {
    "soyo_deep_home": re.compile(r"(妈妈|家里|在家|回家|家务|做饭|洗衣|公寓)"),
    "soyo_deep_wind": re.compile(r"(吹奏|低音大提琴|低音提琴|管弦|贝斯|乐谱|琴弦)"),
    "rana_deep_space": re.compile(r"(外婆|奶奶|SPACE|ライブハウス|归宿|容身|LIVEHOUSE)", re.IGNORECASE),
    "rana_deep_nap": re.compile(r"(睡|困|午睡|打盹)"),
    "rana_deep_int": re.compile(r"(有趣|好玩|无聊|没意思)"),
    "rana_deep_cat": re.compile(r"猫"),
}


def topic_lines(char_cn: str, topic_key: str, limit: int = 10) -> list[str]:
    """按话题正则从金标准语料取同一角色的原句（深模块的「原作同话题」参照物）。"""
    rx = TOPIC_RX.get(topic_key)
    if not rx:
        return []
    rows = [json.loads(l) for l in (CORPUS_DIR / "cn.jsonl").read_text(
        encoding="utf-8").splitlines() if l.strip()]
    key = {v: k for k, v in CHARS.items()}[char_cn]
    out = []
    for r in rows:
        if r["character"] != key or r.get("split") != "train":
            continue
        t = r["text"]
        if len(t) > 60 or not rx.search(t):
            continue
        out.append(t)
    return out[:limit]


def anchored_lines(char_cn: str, scene: str, limit: int = 10) -> list[str]:
    rx = ANCHOR_RX.get(scene)
    if not rx:
        return []
    short = ANCHOR_RX.get(scene + "_short")
    rows = [json.loads(l) for l in (CORPUS_DIR / "cn.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    key = {v: k for k, v in CHARS.items()}[char_cn]
    out = []
    for r in rows:
        if r["character"] != key or r.get("split") != "train":
            continue
        t = r["text"]
        if len(t) > 40:
            continue
        if rx.search(t) or (short and short.search(t)):
            out.append(t)
    return out[:limit]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene", default="", help="场景 key（与 probe 结果里的 scene 字段匹配）")
    ap.add_argument("--ids", default="", help="按 scenario id 前缀过滤（深模块话题用）")
    ap.add_argument("--labels", required=True, help="probe 轮次（逗号分隔），按给出顺序对照")
    ap.add_argument("--n", type=int, default=8, help="每角色展示多少条")
    args = ap.parse_args()

    base = json.loads((DATA / "scene_char_baseline.json").read_text(encoding="utf-8"))
    labels = [x for x in args.labels.split(",") if x]

    def want(r: dict) -> bool:
        if args.ids:
            return str(r.get("scenario", "")).startswith(args.ids)
        return r.get("scene") == args.scene

    runs: dict[str, dict[str, list[str]]] = {}
    for label in labels:
        p = REPORT / f"probe_{label}.jsonl"
        if not p.exists():
            continue
        per: dict[str, list[str]] = defaultdict(list)
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if want(r) and r.get("reply") and not r.get("error"):
                per[r["char"]].append(r["reply"])
        runs[label] = dict(per)

    title = args.ids or args.scene
    out = [f"# 逐场景对照反馈 · `{title}`\n",
           "> 左＝原作里**同一角色在同一话题/场景**真说过的；右＝模型本轮真说的。",
           "> 参照物口径不同会给不同结论，所以能给的都列。\n"]

    for cname in CHARS.values():
        b = base.get(f"{cname}|{args.scene}") if args.scene else None
        an = anchored_lines(cname, args.scene, args.n) if args.scene else []
        tl = topic_lines(cname, args.ids, args.n)
        out.append(f"\n---\n\n## {cname}\n")
        if b:
            L = b["length"]
            out.append(f"**原作参照（场景基线）**：检索口径 n={b['n']}，中位 {L['p50']:.0f} / p90 {L['p90']:.0f}"
                       f"；锚定口径 n={len(an) if an else '—'}"
                       + (f"，中位 {statistics.median([len(t) for t in an]):.0f}" if an else ""))
            out.append("")
        if tl:
            med_t = statistics.median([len(t) for t in tl])
            out.append(f"**原作参照（话题取词）**：n={len(tl)}，中位 {med_t:.0f} 字")
            out.append("")
            out.append("原作（话题）：" + "　".join(f"「{t}」" for t in tl[: args.n]))
            out.append("")
        if an:
            out.append("原作（锚定）：" + "　".join(f"「{t}」" for t in an[: args.n]))
            out.append("")
        if b and b.get("exemplars"):
            out.append("原作（检索 top）：" + "　".join(f"「{t}」" for t in b["exemplars"][:5]))
            out.append("")
        L = b["length"] if b else None
        for label in labels:
            reps = runs.get(label, {}).get(cname, [])
            if not reps:
                out.append(f"**{label}**：无样本")
                continue
            lens = sorted(len(x) for x in reps)
            med = statistics.median(lens)
            ref = L["p50"] if L else (statistics.median([len(t) for t in tl]) if tl else None)
            ref_name = "场景基线" if L else "话题取词"
            verdict = ""
            if ref:
                ratio = med / ref
                verdict = ("✅ 接近" if 0.7 <= ratio <= 1.4 else
                           f"⚠️ 偏长 {ratio:.1f}×" if ratio > 1.4 else f"⚠️ 偏短 {ratio:.2f}×")
            out.append(f"**{label}**（n={len(reps)}，中位 {med:.0f} 字，vs {ref_name} 比 "
                       f"{med / ref:.2f}× {verdict}）" if ref else f"**{label}**（n={len(reps)}，中位 {med:.0f} 字）")
            out.append("")
            for t in reps[: args.n]:
                out.append(f"- [{len(t):3}] 「{t}」")
            out.append("")

    fname = f"scene_feedback_{title}.md" if title else "scene_feedback_global.md"
    (REPORT / fname).write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))
    print(f"\n-> report/{fname}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
