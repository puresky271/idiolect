"""语料质量审计：去重、归属风险、来源覆盖、两语言对照。

不做这步，量化结论会被重复行/多人同句行污染。
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

import json
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHARS = ["tomori", "anon", "rana", "soyo", "taki"]
MYGO_ID = {"36": "tomori", "37": "anon", "38": "rana", "39": "soyo", "40": "taki"}
# 多说话人标记（全角间隔号）——归属不可靠，单独统计
MULTI_SEP = "・"


def load_rows(lang: str) -> list[dict]:
    rows: list[dict] = []
    bd = HERE / "raw" / "bestdori" / f"{lang}.jsonl"
    if bd.exists():
        for line in bd.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                ch = MYGO_ID.get(str(r["character_id"]))
                if ch:
                    rows.append({**r, "character": ch, "source": "bestdori"})
    hf = HERE / "raw" / "hf" / f"{lang}.jsonl"
    if hf.exists():
        for line in hf.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append({**json.loads(line), "source": "hf"})
    return rows


def main() -> int:
    lines: list[str] = []
    for lang in ("jp", "cn"):
        rows = load_rows(lang)
        if not rows:
            continue
        by_char: dict[str, list[dict]] = defaultdict(list)
        for r in rows:
            by_char[r["character"]].append(r)

        lines.append(f"\n{'=' * 74}\n## {lang.upper()}  原始 {len(rows)} 行\n{'=' * 74}")
        lines.append(f"{'角色':<8}{'原始':>7}{'唯一':>7}{'重复%':>8}{'多人行':>8}{'bestdori':>10}{'hf':>7}{'中位字长':>9}")
        lines.append("-" * 66)

        total_uniq = 0
        for ch in CHARS:
            rs = by_char.get(ch, [])
            texts = [r["text"] for r in rs]
            uniq = list(dict.fromkeys(texts))
            multi = sum(1 for t in texts if MULTI_SEP in t)
            src = Counter(r["source"] for r in rs)
            lens = sorted(len(t) for t in uniq)
            med = lens[len(lens) // 2] if lens else 0
            dup = (1 - len(uniq) / len(texts)) * 100 if texts else 0
            total_uniq += len(uniq)
            lines.append(
                f"{ch:<8}{len(texts):>7}{len(uniq):>7}{dup:>7.0f}%{multi:>8}{src.get('bestdori', 0):>10}"
                f"{src.get('hf', 0):>7}{med:>9}"
            )
        lines.append(f"{'合计':<8}{len(rows):>7}{total_uniq:>7}")

        # 跨来源重复：bestdori 与 hf 的重合度
        bd_txt = {r["text"] for r in rows if r["source"] == "bestdori"}
        hf_txt = {r["text"] for r in rows if r["source"] == "hf"}
        if bd_txt and hf_txt:
            inter = bd_txt & hf_txt
            lines.append(
                f"\n来源重合：bestdori {len(bd_txt)} / hf {len(hf_txt)} → 交集 {len(inter)}"
                f"（hf 有 {len(inter) / max(len(hf_txt), 1) * 100:.0f}% 已被 bestdori 覆盖）"
            )
        # 最长 / 最短样例
        longest = max(rows, key=lambda r: len(r["text"]))
        lines.append(f"\n最长行（{longest['character']}, {len(longest['text'])} 字）: {longest['text'][:120]}")
        lines.append("")

    text = "\n".join(lines)
    out = REPORT / "corpus_audit.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
