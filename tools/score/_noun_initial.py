"""乐奈「名词起手率」缺口：当前生产臂 vs 原作基线（非 prompt 手段的起点）。

背景（`REPORT_rana_sentence.md`）：乐奈原作起手 56% 是**名词/体言直出**（五人最高），
主谓起手只有 11%（其余四人 30~40%）。两次 prompt 侧 A/B 都是负结论（+2.04pp，z=0.30 n.s.），
所以这一项改用**非 prompt 手段**——但先要把缺口量准（在哪一类起手上差）。

用法：
  py -X utf8 _noun_initial.py gen_off2 gen_on9        # 通用场景臂
  py -X utf8 _noun_initial.py deep_on8 --chars 乐奈
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
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.stdout.reconfigure(encoding="utf-8")

CHARS = ["灯", "爱音", "素世", "立希", "乐奈"]
KEY = {"灯": "tomori", "爱音": "anon", "素世": "soyo", "立希": "taki", "乐奈": "rana"}

FILLER = re.compile(r"^(嗯|啊|唔|哦|诶|唉|咦|哎|あ|ん|え)")
SUBJECT = re.compile(r"^[我你他她它这那谁哪]")
PUNCT = re.compile(r"^[？?！!…·]")


def opening_shape(t: str) -> str:
    """与 `rana_sentence.py` 完全同口径（保证与历史结论可比）。"""
    s = t.strip()
    if not s:
        return "空"
    if PUNCT.match(s):
        return "标点起手"
    if FILLER.match(s):
        return "语气词起手"
    if re.search(r"(吗|呢|吧|么)[？?]?$", s) or s.endswith(("？", "?")):
        return "疑问起手"
    if SUBJECT.match(s):
        return "主谓起手"
    return "名词/体言直出"


def corpus(char: str) -> list[str]:
    out = []
    for line in (CORPUS_DIR / "cn.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            if r["character"] == KEY[char] and r.get("split") == "train":
                out.append(r["text"])
    return out


def dist(texts: list[str]) -> dict[str, float]:
    c = Counter(opening_shape(t) for t in texts if t.strip())
    n = sum(c.values()) or 1
    return {k: v / n for k, v in c.items()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("labels", nargs="+")
    ap.add_argument("--chars", default="")
    args = ap.parse_args()
    chars = [c for c in args.chars.split(",") if c] or CHARS

    base = {c: dist(corpus(c)) for c in chars}
    kinds = ["名词/体言直出", "主谓起手", "语气词起手", "疑问起手", "标点起手"]

    print("## 原作基线（cn train）\n")
    print(f"{'角色':<5}" + "".join(f"{k:>12}" for k in kinds))
    for c in chars:
        print(f"{c:<5}" + "".join(f"{base[c].get(k, 0):>11.0%} " for k in kinds))

    for label in args.labels:
        p = REPORT / f"probe_{label}.jsonl"
        if not p.exists():
            print(f"\n[{label}] 缺文件")
            continue
        rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
        per: dict[str, list[str]] = defaultdict(list)
        for r in rows:
            if r.get("reply"):
                per[r["char"]].append(r["reply"])
        print(f"\n## 臂 `{label}`\n")
        print(f"{'角色':<5}" + "".join(f"{k:>12}" for k in kinds) + f"{'Δ名词':>10}")
        for c in chars:
            if not per.get(c):
                continue
            d = dist(per[c])
            gap = d.get("名词/体言直出", 0) - base[c].get("名词/体言直出", 0)
            print(f"{c:<5}" + "".join(f"{d.get(k, 0):>11.0%} " for k in kinds) + f"{gap:>+9.1%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
