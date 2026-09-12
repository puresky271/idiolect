"""探针场景注册表 v2：把语料反推的夹具并入统一场景集。

设计：
  · 保留 v1 的 30 个手工场景（与历史各臂可比）
  · 并入 v2 的 46 个语料反推夹具（补齐 15 个缺口场景）
  · 每条都带 scene key（来自 scenes.py），使评分可按语用场景聚合
  · canon 敏感项（如 soyo_past 用「祥子要重组乐队」）标记 risk，便于审查/剔除

用法：
  py -X utf8 probe_registry.py --list            # 列出全部
  py -X utf8 probe_registry.py --scene-stats     # 场景覆盖统计
  py -X utf8 probe_registry.py --drop-risk       # 打印剔除 risk 项后的集合
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
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import scenes as SC  # noqa: E402
from scene_coverage import EXISTING_MAP  # noqa: E402

REPORT = REPORT
V2_PATH = REPORT / "probe_scenes_v2.json"

# canon 敏感夹具：并入前需人工确认（先标记、默认保留但在报告中标注）
RISK_IDS = {
    "soyo_past_soyo_0", "soyo_past_soyo_1",  # 提到祥子/重组乐队，canon 敏感
    "taki_shift_taki_0",                      # 打工结束「去喝一杯」——未成年饮酒风险
}


def load_v1() -> list[dict]:
    import probe_scenarios as PS

    out = []
    for char, scs in PS.SCENARIOS.items():
        for sc in scs:
            out.append({
                "id": sc["id"], "source": "v1", "char": char, "cat": sc["cat"],
                # 夹具可自带 `scene`（例如深模块的猫话题挂 rana_cat）；
                # 没有才回落到 EXISTING_MAP —— 让「该按场景评分的」拿到原作同场景基线。
                "scene": sc.get("scene") or EXISTING_MAP.get(sc["id"], ""),
                "user_text": sc["text"],
                "risk": False, "why": "",
            })
    return out


def load_v2() -> list[dict]:
    if not V2_PATH.exists():
        return []
    d = json.loads(V2_PATH.read_text(encoding="utf-8"))
    out = []
    for scene, items in d.items():
        for it in items:
            out.append({
                "id": it["id"], "source": "v2", "char": it["char"], "cat": it.get("scene_cn", ""),
                "scene": scene, "user_text": it["user_text"],
                "risk": it["id"] in RISK_IDS, "why": it.get("why", ""),
            })
    return out


def registry(drop_risk: bool = False) -> list[dict]:
    items = load_v1() + load_v2()
    if drop_risk:
        items = [x for x in items if not x["risk"]]
    return items


def by_char(items: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        out[it["char"]].append(it)
    return dict(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--scene-stats", action="store_true")
    ap.add_argument("--drop-risk", action="store_true")
    args = ap.parse_args()

    items = registry()
    print(f"注册表：{len(items)} 条（v1 {sum(1 for x in items if x['source'] == 'v1')}｜"
          f"v2 {sum(1 for x in items if x['source'] == 'v2')}）")
    print(f"风险标记：{sum(1 for x in items if x['risk'])} 条")
    print(f"角色分布：{dict(Counter(x['char'] for x in items))}")

    scene_cnt = Counter(x["scene"] for x in items if x["scene"])
    all_sc = {s.key: s for s in SC.all_scenes()}
    missing = [k for k in all_sc if k not in scene_cnt]
    print(f"\n场景覆盖：{len(scene_cnt)}/{len(all_sc)}｜未覆盖：{missing if missing else '无'}")
    print(f"\n{'场景':<20}{'中文':<18}{'条数':>5}  角色")
    print("-" * 78)
    for key, s in all_sc.items():
        n = scene_cnt.get(key, 0)
        chars = sorted({x["char"] for x in items if x["scene"] == key})
        print(f"{key:<20}{s.cn:<18}{n:>5}  {'、'.join(chars)}")

    if args.list:
        print("\n--- 明细 ---")
        for it in items:
            flag = " ⚠risk" if it["risk"] else ""
            print(f"[{it['source']}] {it['id']:<28} {it['char']:<4} scene={it['scene']:<18} {it['user_text'][:34]!r}{flag}")

    (REPORT / "probe_registry.json").write_text(
        json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
