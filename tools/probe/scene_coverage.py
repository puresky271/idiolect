"""覆盖率盘点：现有 probe 场景 vs 26 个语用场景，找出缺口。

用法：py -X utf8 scene_coverage.py
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

import json
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import scenes as SC  # noqa: E402
import taxonomy as TX  # noqa: E402

REPORT = REPORT
CHARS = ["爱音", "素世", "灯", "立希", "乐奈"]
CHARKEY = {"爱音": "anon", "素世": "soyo", "灯": "tomori", "立希": "taki", "乐奈": "rana"}

# 现有探针场景 → 语用场景 的映射（人工判定，写在代码里便于审查）
EXISTING_MAP = {
    "anon_p1_crisis": "crisis", "anon_p2_crying": "comfort", "anon_p3_repeat": "crisis",
    "anon_p4_mundane": "banter", "anon_p5_mundane2": "schedule", "anon_p6_meta_bait": "meta_language",
    "anon_p7_love": "affection", "anon_p8_love2": "affection",
    "tomori_p1_crying": "comfort", "tomori_p2_hundred": "affection", "tomori_p3_repeat": "affection",
    "tomori_p7_love": "affection",
    "tomori_p4_mundane": "banter", "tomori_p5_mundane2": "schedule", "tomori_p6_meta_bait": "meta_language",
    "taki_p1_love": "affection", "taki_p2_test": "probe_stance", "taki_p3_repeat": "probe_stance",
    "taki_p7_love2": "affection",
    "taki_p8_rana": "rana_cat",
    "taki_p4_mundane": "schedule", "taki_p5_mundane2": "third_party", "taki_p6_meta_bait": "meta_language",
    "soyo_p1_notgood": "low_mood", "soyo_p2_wish": "wellwish", "soyo_p3_repeat": "low_mood",
    "soyo_p4_mundane": "schedule", "soyo_p5_mundane2": "fact_qa", "soyo_p6_meta_bait": "meta_language",
    "soyo_p7_love": "affection", "soyo_p8_love2": "affection",
    "rana_p1_annoying": "low_mood", "rana_p2_halfword": "third_party", "rana_p3_repeat": "low_mood",
    "rana_p4_mundane": "fact_qa", "rana_p5_mundane2": "schedule", "rana_p6_meta_bait": "meta_language",
    "rana_p7_love": "affection", "rana_p8_love2": "affection",
}


def main() -> int:
    import probe_scenarios as PS

    have: dict[str, list[str]] = defaultdict(list)
    for char, scs in PS.SCENARIOS.items():
        for sc in scs:
            mapped = EXISTING_MAP.get(sc["id"])
            if mapped:
                have[mapped].append(f"{char}:{sc['id']}")

    all_sc = {s.key: s for s in SC.all_scenes()}
    print(f"语用场景 {len(all_sc)} 个｜现有探针覆盖 {len(have)} 个\n")
    print(f"{'状态':<6}{'场景':<20}{'中文':<18}{'已有夹具'}")
    print("-" * 92)
    gaps = []
    for key, s in all_sc.items():
        got = have.get(key, [])
        mark = "✓" if got else "✗"
        if not got:
            gaps.append(key)
        print(f"{mark:<6}{key:<20}{s.cn:<18}{len(got)} 个" + (f"  {'、'.join(got[:2])}" if got else ""))

    print(f"\n缺口 {len(gaps)}/{len(all_sc)}：{gaps}")
    (REPORT / "scene_coverage.json").write_text(
        json.dumps({"covered": {k: v for k, v in have.items()}, "gaps": gaps},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
