"""合并 HF + Bestdori → 五人金标准语料（去重 + 来源标注 + 训练/留出切分）。

去重策略：
  同语言内按 (character, text) 唯一化。重复行不是噪声，而是「同一句被多个场景复用」，
  但若不去重，量化分布会被反复出现的台词带偏。
  跨来源（bestdori / hf）保留**首次出现的来源标签**，并记录该文本被哪些来源覆盖。

留出集切分：
  按文本 hash 稳定切 20% 作为 holdout，防止后续探针调参对 gold 过拟合
  （调参只能看 train 部分的分布，验收用 holdout）。

产出 bench/raw/gold/{lang}.jsonl + gold_stats.json
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

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = CORPUS_DIR
OUT.mkdir(parents=True, exist_ok=True)
CHARS = ["tomori", "anon", "rana", "soyo", "taki"]
MYGO_ID = {"36": "tomori", "37": "anon", "38": "rana", "39": "soyo", "40": "taki"}
HOLDOUT_RATIO = 0.2


def is_holdout(text: str) -> bool:
    h = int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)
    return (h % 100) < HOLDOUT_RATIO * 100


def main() -> int:
    stats: dict = {}
    for lang in ("jp", "cn"):
        merged: dict[tuple[str, str], dict] = {}
        # bestdori 优先（覆盖更广、含 area/talkset）
        for src in ("bestdori", "hf"):
            if src == "bestdori":
                p = HERE / "raw" / "bestdori" / f"{lang}.jsonl"
                rows = []
                if p.exists():
                    for line in p.read_text(encoding="utf-8").splitlines():
                        if line.strip():
                            r = json.loads(line)
                            ch = MYGO_ID.get(str(r["character_id"]))
                            if ch:
                                rows.append({"character": ch, "text": r["text"], "source": "bestdori",
                                             "dir": r.get("dir", ""), "speaker": r.get("speaker", "")})
            else:
                p = HERE / "raw" / "hf" / f"{lang}.jsonl"
                rows = []
                if p.exists():
                    for line in p.read_text(encoding="utf-8").splitlines():
                        if line.strip():
                            r = json.loads(line)
                            rows.append({"character": r["character"], "text": r["text"], "source": "hf",
                                         "dir": f"event{r['event_id']}", "speaker": ""})
            for r in rows:
                key = (r["character"], r["text"])
                if key in merged:
                    merged[key]["also"].add(src)
                else:
                    merged[key] = {**r, "also": {src}}

        out = OUT / f"{lang}.jsonl"
        per_char = Counter()
        per_split = Counter()
        with out.open("w", encoding="utf-8") as f:
            for (ch, text), r in merged.items():
                split = "holdout" if is_holdout(text) else "train"
                rec = {
                    "character": ch,
                    "text": text,
                    "source": r["source"],
                    "also": sorted(r["also"]),
                    "dir": r["dir"],
                    "lang": lang,
                    "split": split,
                }
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                per_char[ch] += 1
                per_split[split] += 1

        stats[lang] = {
            "unique_total": len(merged),
            "per_character": dict(per_char),
            "per_split": dict(per_split),
            "coverage_both_sources": sum(1 for r in merged.values() if len(r["also"]) > 1),
        }
        print(f"[{lang}] unique={len(merged)}  per_char={dict(per_char)}  split={dict(per_split)}")
        print(f"       两来源都有: {stats[lang]['coverage_both_sources']}")

    (OUT / "gold_stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
