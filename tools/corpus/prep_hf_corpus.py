"""把 HF BanG_Dream_Events 数据集整理成 MyGO 五人金标准语料。

数据源: KomeijiForce/BanG_Dream_Events (cn/jp/en, 列: event_id/chapter/speaker/windowDisplayName/text)
  - speaker 列是占位符，真正的说话人在 windowDisplayName
  - 多人为「爱音・立希」这种全角间隔号拼接，只保留纯单人行（避免归属污染）

产出: bench/raw/hf/{lang}.jsonl
  每行 {"character_id","character","text","source","event_id","chapter","lang"}
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
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
RAW = HERE.parent / "raw"          # 与 v41 主目录共用已下载的 parquet
OUT = HERE / "raw" / "hf"
OUT.mkdir(parents=True, exist_ok=True)

# windowDisplayName -> 规范角色键（跨语言统一到 roman）
NAME_MAP = {
    "jp": {"燈": "tomori", "愛音": "anon", "楽奈": "rana", "そよ": "soyo", "立希": "taki"},
    "cn": {"灯": "tomori", "爱音": "anon", "乐奈": "rana", "爽世": "soyo", "立希": "taki"},
    "en": {"Tomori": "tomori", "Anon": "anon", "Rana": "rana", "Soyo": "soyo", "Taki": "taki"},
}
CID = {"tomori": "36", "anon": "37", "rana": "38", "soyo": "39", "taki": "40"}
MULTI_SEP = ("・", "·", "・")


def main() -> int:
    summary = {}
    for lang in ("jp", "cn", "en"):
        src = RAW / f"{lang}.parquet"
        if not src.exists():
            print(f"[{lang}] missing {src.name}, skip")
            continue
        df = pd.read_parquet(src)
        name_map = NAME_MAP[lang]
        rows = []
        multi = 0
        for rec in df.itertuples(index=False):
            name = str(getattr(rec, "windowDisplayName") or "").strip()
            text = str(getattr(rec, "text") or "").strip()
            if not text:
                continue
            if any(sep in name for sep in MULTI_SEP):
                multi += 1
                continue
            char = name_map.get(name)
            if not char:
                continue
            rows.append(
                {
                    "character_id": CID[char],
                    "character": char,
                    "text": text,
                    "source": "hf_eventstory",
                    "event_id": int(getattr(rec, "event_id")),
                    "chapter": int(getattr(rec, "chapter")),
                    "lang": lang,
                }
            )
        out = OUT / f"{lang}.jsonl"
        with out.open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        per = {}
        for r in rows:
            per[r["character"]] = per.get(r["character"], 0) + 1
        summary[lang] = {"kept": len(rows), "multi_speaker_skipped": multi, "per_character": per}
        print(f"[{lang}] kept={len(rows)} multi_skipped={multi} -> {out.name}")
        print("       ", per)
    (OUT / "_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
