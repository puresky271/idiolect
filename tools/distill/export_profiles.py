"""导出 `data/style_profiles.json`：每个角色的完整风格画像（**派生统计，不含原文**）。

为什么需要它：探针的 fidelity 评分要把「模型的产出」和「原作的分布」对齐，而分布
需要 mean/sd/分位数——`style_targets.json` 只有中位与 p90，够写 prompt，不够算分。
原项目里这个 gold 画像是**每次探针现场从语料算**的，于是没有语料就跑不了探针；
本仓库把画像作为派生统计发出去，让「clone → 探针 → 出分」这条链闭合。

画像 = `style_features.profile_from_texts(train 台词)`，逐字段都是聚合量
（n / 均值 / 标准差 / 分位数 / 出现率 / 高频语气词），**没有任何一句原作台词**。
语料仍不入库：要重算就用 `IDIOLECT_CORPUS_DIR` 指向你自己的语料目录。

用法：
    py -X utf8 tools/distill/export_profiles.py            # 写 data/style_profiles.json
    py -X utf8 tools/distill/export_profiles.py --check    # 只校验已有文件与语料是否一致
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

import style_features as S  # noqa: E402

CHARKEY = {"爱音": "anon", "灯": "tomori", "立希": "taki", "素世": "soyo", "乐奈": "rana"}


def load_train(lang: str = "cn") -> dict[str, list[str]]:
    from _paths import corpus_file, require_corpus

    require_corpus(lang)  # 空语料一律当场退出（否则会写出空画像）
    out: dict[str, list[str]] = {k: [] for k in CHARKEY.values()}
    for line in corpus_file(lang).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("split") == "train" and r.get("character") in out:
            out[r["character"]].append(r["text"])
    return out


def build(lang: str = "cn") -> dict:
    texts = load_train(lang)
    out: dict = {"lang": lang, "note": "派生统计（聚合量），不含任何原作台词；由 tools/distill/export_profiles.py 生成"}
    for char, key in CHARKEY.items():
        out[key] = S.profile_from_texts(texts[key], lang)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", default="cn")
    ap.add_argument("--check", action="store_true", help="只比对已有文件与语料重算结果")
    args = ap.parse_args()

    dst = DATA / "style_profiles.json"
    fresh = build(args.lang)
    if args.check:
        if not dst.exists():
            print(f"[FAIL] 缺 {dst}")
            return 1
        old = json.loads(dst.read_text(encoding="utf-8"))
        diff = []
        for key in CHARKEY.values():
            a, b = old.get(key, {}), fresh.get(key, {})
            for field in ("n", "length", "n_sent", "punct_rate", "first_person_rate"):
                if json.dumps(a.get(field), sort_keys=True) != json.dumps(b.get(field), sort_keys=True):
                    diff.append(f"{key}.{field} 旧={str(a.get(field))[:60]} 新={str(b.get(field))[:60]}")
        if diff:
            print("[FAIL] 画像与语料不一致（语料换代了？重跑 export_profiles.py）：")
            for d in diff[:12]:
                print("   ", d)
            return 1
        print(f"[ ok ] {dst.name} 与语料一致（{len(CHARKEY)} 角色）")
        return 0

    DATA.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(fresh, ensure_ascii=False, indent=1), encoding="utf-8")
    size = dst.stat().st_size
    print(f"-> {dst}（{size / 1024:.1f} KB）")
    for char, key in CHARKEY.items():
        p = fresh[key]
        print(f"  {char:<4} n={p['n']:<5} 中位={p['length']['p50']:<6.1f} "
              f"p90={p['length']['p90']:<6.1f} 句数={p['n_sent']['mean']:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
