"""导出角色全局数值目标（每人一份），供 prompt 补丁与报告引用。

产出 `report/style_targets.json`（发布副本在 `data/style_targets.json`）。

⚠️ 口径差异（刻意保留）：本脚本**不过滤 split**，train 与 holdout 都算进来，
所以 n 比 `export_profiles.py` 的 train-only 画像大（cn.anon 1579 vs 1244）。
理由：这份数字是写进 prompt 的「这个人一般怎么说」，样本多一份更稳；而评测的
参照系必须 train-only，否则等于拿留出行当答案。生产 `idiolect/style_target.py`
的 `STYLE_TARGETS` 照这份抄写，改口径会让 prompt 里的数字与历史批次不可比。
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
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import style_features as S  # noqa: E402

CHARS = {"tomori": "灯", "anon": "爱音", "rana": "乐奈", "soyo": "爽世", "taki": "立希"}


def main() -> int:
    out: dict = {}
    for lang in ("cn", "jp"):
        per: dict[str, list[str]] = defaultdict(list)
        p = CORPUS_DIR / f"{lang}.jsonl"
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            per[r["character"]].append(r["text"])
        out[lang] = {}
        for key, texts in per.items():
            prof = S.profile_from_texts(texts, lang)
            out[lang][key] = {"name": CHARS.get(key, key), "n": prof.get("n", 0),
                              **S.style_targets(prof, lang)}
    dst = REPORT / "style_targets.json"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"{'角色':<7}{'中位':>6}{'p90':>6}{'句/回合':>9}{'省略号':>8}{'感叹号':>8}{'问号':>7}{'句号':>7}{'一人称':>8}")
    print("-" * 66)
    for key, t in out["cn"].items():
        print(f"{t['name']:<7}{t['median_chars']:>6.0f}{t['p90_chars']:>6.0f}{t['sent_per_turn']:>9.2f}"
              f"{t['ellipsis_rate'] * 100:>7.0f}%{t['exclaim_rate'] * 100:>7.0f}%{t['question_rate'] * 100:>6.0f}%"
              f"{t['period_rate'] * 100:>6.0f}%{t['first_person_rate'] * 100:>7.0f}%")
    print(f"\n-> {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
