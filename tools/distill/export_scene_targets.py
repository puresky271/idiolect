"""把 (角色 × 场景) 基线导出为**运行时可直接 import 的数据模块**。

读 `data/scene_char_baseline.json`（随仓库发布的派生统计），压成
`idiolect/scene_length_targets.py`（只留渲染需要的字段），使
`idiolect.style_target.build_style_target_block` 能按当轮场景取长度目标。

导出字段：median / p90 / sent / n（n < MIN_N 的 cell 丢弃——样本不足不给目标）

用法：py -X utf8 tools/distill/export_scene_targets.py
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
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = DATA / "scene_char_baseline.json"
# 生成物是**包内模块**：运行时由 idiolect.style_target 直接 import。
# 2026-09-13 修：此前指向仓库根，重跑会把文件写到根目录，包内那份不会更新。
DST = ROOT / "idiolect" / "scene_length_targets.py"
MIN_N = 20                             # 比 baseline 的 12 更严：要拿去做生产目标，样本得够


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="导出 (角色 × 场景) 长度目标到 idiolect/scene_length_targets.py")
    ap.add_argument("--dry-run", action="store_true", help="只统计不写文件")
    ap.add_argument("--out", default="", help=f"输出路径（默认 {DST}）")
    args = ap.parse_args()
    dst = Path(args.out) if args.out else DST

    if not SRC.exists():
        raise SystemExit(f"[stop] 缺 {SRC}——它随仓库发布；没有它就无法导出场景目标。")
    src = json.loads(SRC.read_text(encoding="utf-8"))
    import sys as _sys
    _sys.path.insert(0, str(HERE))
    try:
        import scenes as SC
        cn_map = {s.key: s.cn for s in SC.SCENES}
    except Exception:  # noqa: BLE001
        cn_map = {}
    # `scenes.py` 的 SCENES 只列了 13 个通用场景；13 个角色专属场景的 key→中文名补在这里
    cn_map.update({
        "anon_beauty": "美妆/穿搭", "anon_sns": "社交媒体",
        "tomori_nature": "自然物/收藏", "tomori_lyrics": "歌词/写作",
        "taki_music_pro": "编曲/练鼓", "taki_soft_spot": "软肋", "taki_shift": "打工/接客",
        "soyo_observe": "观察/点破", "soyo_tea": "红茶/待客", "soyo_past": "过去/CRYCHIC",
        "rana_guitar": "吉他/演出", "rana_food": "抹茶/食物", "rana_cat": "猫/观察",
    })

    out: dict[str, dict[str, dict]] = {}
    dropped = 0
    for key, v in src.items():
        if int(v.get("n") or 0) < MIN_N:
            dropped += 1
            continue
        char, scene = v["char"], v["scene"]
        out.setdefault(char, {})[scene] = {
            "median": round(float(v["length"]["p50"]), 1),
            "p90": round(float(v["length"]["p90"]), 1),
            "sent": round(float(v["n_sent"]["mean"]), 2),
            "n": int(v["n"]),
            "cn": cn_map.get(scene, scene),
        }

    lines = [
        '"""按「角色 × 场景」的原作长度/句数目标（**由脚本生成，勿手改**）。',
        "",
        "来源：`data/scene_char_baseline.json`",
        "      （先按角色过滤语料、再按场景原型检索 top-40 得到的分布）",
        "生成：`py -X utf8 tools/distill/export_scene_targets.py`",
        f"过滤：样本 n < {MIN_N} 的组合不导出（共丢弃 {dropped} 个）",
        f"规模：{sum(len(v) for v in out.values())} 个 (角色 × 场景) 目标",
        "",
        "消费方：`idiolect/style_target.py::build_style_target_block(char, scene)`",
        "         —— 命中场景时用本表替换**长度/句数**两行，其余（句末标点率/自称/硬检查）仍用全局值。",
        '"""',
        "from __future__ import annotations",
        "",
        # 注意：`= ` 与 JSON 体必须在**同一逻辑行**（JSON 体开头是 `{`，
        # 若被换行隔开，`x =` 后面直接断行会导致 SyntaxError —— 2026-09-12 踩过）
        "SCENE_LENGTH_TARGETS: dict[str, dict[str, dict]] = "
        + json.dumps(out, ensure_ascii=False, indent=4, sort_keys=True),
        "",
        "",
        "def get_scene_target(char: str, scene: str) -> dict | None:",
        '    """取 (角色 × 场景) 目标；无则 None（调用方回退全局值）。"""',
        '    return SCENE_LENGTH_TARGETS.get(str(char or "").strip(), {}).get(str(scene or "").strip())',
        "",
    ]
    cells = sum(len(v) for v in out.values())
    if not cells:
        # 空表会覆盖掉运行时模块里的 130 个目标 → 拒绝写（--dry-run 也不写）
        raise SystemExit(
            f"[stop] 导出结果为 0 个目标（源 {SRC} 里没有 n ≥ {MIN_N} 的组合）——拒绝覆盖 {dst}。")
    if args.dry_run:
        print(f"[dry-run] 将导出 {cells} 个目标到 {dst}（未写文件）")
        return 0
    dst.write_text("\n".join(lines), encoding="utf-8")
    print(f"导出 {cells} 个目标 → {dst}")
    print(f"  丢弃 n<{MIN_N} 的 {dropped} 个｜角色数 {len(out)}")
    for c, m in sorted(out.items()):
        meds = ", ".join(f"{s}:{d['median']:.0f}" for s, d in sorted(m.items()))
        print(f"  {c}: {len(m)} 场景  {meds[:96]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
