"""示例复述审计：**直接检测回复里有没有照抄注入块中的示例句**。

为什么需要它（用户 2026-09-12 反复担心的点）：
  「同格 distinct 比例」只是**间接代理**——它能发现 6 条雷同，但说不出「抄的是哪一句」，
  也发现不了「抄了示例的一句、但句子本身有变化」这种半抄袭。
  这里改成直接量：把注入块里**示例行**的引号内容抽出来，逐条回复比对。

抽取规则（关键）：
  · 只看示例行：含「形态示例 / 正例 / 参考 / 示例」的行；
    场景模块的「口癖」提示行**排除**——口癖本来就是要她说的（「行了」「嗯。」）。
  · 丢掉占位符（含（）、/、· 的 token）与 2 字以下 token。
  · 命中判定：`literal in reply`（逐字包含）；
    另报 `LCS`（与任一 literal 的最长公共子串，≥4 才算「近似复述」），
    用来抓「抄了半句再改几个字」。

用法：
  py -X utf8 _copy_audit.py --cat 深模块 --labels deep_off,deep_on,deep_on2,deep_on3,deep_on4,deep_on5
  py -X utf8 _copy_audit.py --cat 通用场景 --labels gen_off,gen_on,gen_on2,gen_on3,gen_on4
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
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[2]))

import idiolect.registry as RP  # noqa: E402
import probe_scenarios as PS  # noqa: E402

REPORT = REPORT
CHARKEY = {"爱音": "anon", "素世": "soyo", "灯": "tomori", "立希": "taki", "乐奈": "rana"}

_CANON_CACHE: dict[str, str] = {}


def canon_text(char: str) -> str:
    """该角色的 canon 长档案 + voice manifest —— 用来判断一个引用是不是「本来就在 prompt 里」。

    为什么必须区分：`rana` 的「有趣的女孩子」是 canon 原话、`taki` 的「行了」是她的口癖，
    这些本来就在 identity block / voice manifest 里，模型复用它们**不是**我的例句被照抄。
    只有「仅存在于我写的 turn_logic 正文里」的片段才算复述问题。
    """
    if char not in _CANON_CACHE:
        try:
            _CANON_CACHE[char] = (RP.get_canon_profile(char) or "") + "\n" + (RP.get_voice_manifest(char) or "")
        except Exception:  # noqa: BLE001
            _CANON_CACHE[char] = ""
    return _CANON_CACHE[char]

_QUOTED = re.compile(r"「([^」]+)」")
_EXAMPLE_LINE = re.compile(r"形态示例|正例|参考|示例")
_TIC_LINE = re.compile(r"口癖")
_PLACEHOLDER = re.compile(r"[（）()／/·—]|^[A-Za-z]+$")


def iter_fixtures(cat: str):
    """把 probe_scenarios 里的夹具线性化（按类别过滤）。"""
    for char, scs in PS.SCENARIOS.items():
        for sc in scs:
            if cat and sc.get("cat") != cat:
                continue
            yield char, sc


def example_literals(block: str) -> list[str]:
    """抽出注入块里**所有可能被照抄的引号内容**。

    口径（2026-09-12 收紧过一次）：早期只看「形态示例 / 正例」行，漏掉了 bullet 里的引用；
    现在扫**所有行**，只排除两处：
      · 引擎自动追加的「口癖」提示行——口癖本来就该她说；
      · 标注「原话」的行——canon 原话属于角色档案，不是我写的例句
        （但这类仍单独统计，见 `audit` 的 `n_canon`，因为它们同样会被逐字复用）。
    占位符（含 （）、/）不算例句。
    """
    out: list[str] = []
    for line in block.splitlines():
        if _TIC_LINE.search(line):
            continue
        for tok in _QUOTED.findall(line):
            tok = tok.strip()
            if len(tok) < 2 or _PLACEHOLDER.search(tok):
                continue
            out.append(tok)
    return out


def lcs(a: str, b: str) -> int:
    """最长公共子串长度（字符串都不长，DP 够用）。"""
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    best = 0
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        ai = a[i - 1]
        for j in range(1, len(b) + 1):
            if ai == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                best = max(best, cur[j])
        prev = cur
    return best


def audit(label: str, cat: str) -> dict:
    p = REPORT / f"probe_{label}.jsonl"
    if not p.exists():
        return {}
    rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    replies: dict[tuple[str, str], list[str]] = defaultdict(list)
    for r in rows:
        if r.get("reply"):
            replies[(r["char"], r["scenario"])].append(r["reply"])

    block_cache: dict[tuple[str, str], str] = {}
    cell_stats: dict[tuple[str, str], dict] = {}
    hit_counter: dict[str, int] = defaultdict(int)

    # 无注入臂（label 含 off）**不渲染** block → 复述率应≈0；
    # 它给的是「巧合重叠」下限（回复碰巧用了语料里也有的说法）。
    inject = "off" not in label

    for (char, scid), reps in replies.items():
        key = (char, scid)
        if key not in block_cache:
            text = next((sc["text"] for c, sc in iter_fixtures(cat)
                         if c == char and sc["id"] == scid), None)
            if text is None:
                continue
            block_cache[key] = RP.render_turn_special_block(
                char, text, session_id=f"probe:{label}:{char}:{scid}",
                is_developer=False, mode="chat") or "" if inject else ""
        lits = [x for x in example_literals(block_cache[key]) if x not in canon_text(char)]
        n_hit = n_near = 0
        worst = 0
        for rep in reps:
            best_exact, best_lit = 0, ""
            for lit in lits:
                if lit in rep and len(lit) > best_exact:
                    best_exact, best_lit = len(lit), lit
            if best_exact >= 3:
                n_hit += 1
                hit_counter[best_lit] += 1
            near = max((lcs(rep, lit) for lit in lits), default=0)
            worst = max(worst, near)
            if best_exact < 3 and near >= 4:
                n_near += 1
        cell_stats[key] = {"n": len(reps), "n_hit": n_hit, "n_near": n_near,
                           "max_lcs": worst, "n_lit": len(lits),
                           "max_lit": max((len(x) for x in lits), default=0)}
    return {"cells": cell_stats, "hits": dict(hit_counter)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cat", required=True)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--detail", action="store_true", help="逐格打印")
    args = ap.parse_args()

    labels = [x for x in args.labels.split(",") if x]
    print(f"# 示例复述审计 · {args.cat}（命中 = 回复里**逐字包含**注入块的引号内容 ≥3 字）\n")
    print(f"{'臂':<12}{'格数':>5}{'回复数':>7}{'逐字复述':>9}{'复述率':>9}{'近似复述':>9}"
          f"{'最长引用':>9}{'最长公共子串':>12}")
    for lab in labels:
        res = audit(lab, args.cat)
        st = res.get("cells") or {}
        if not st:
            print(f"{lab:<12}（无数据）")
            continue
        n = sum(v["n"] for v in st.values())
        hit = sum(v["n_hit"] for v in st.values())
        near = sum(v["n_near"] for v in st.values())
        mlcs = max((v["max_lcs"] for v in st.values()), default=0)
        mlit = max((v["max_lit"] for v in st.values()), default=0)
        print(f"{lab:<12}{len(st):>5}{n:>7}{hit:>9}{hit / n if n else 0:>9.0%}"
              f"{near:>9}{mlit:>9}{mlcs:>12}")
        if args.detail:
            for (char, scid), v in sorted(st.items(), key=lambda kv: -kv[1]["n_hit"]):
                if v["n_hit"]:
                    print(f"    {char} {scid:<24} 复述 {v['n_hit']}/{v['n']}  最长公共子串 {v['max_lcs']}")
            top = sorted(res["hits"].items(), key=lambda kv: -kv[1])[:8]
            if top:
                print("    被复述的示例句：")
                for lit, cnt in top:
                    print(f"      ×{cnt}  「{lit}」")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
