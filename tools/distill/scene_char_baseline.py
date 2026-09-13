"""构建「角色 × 场景」级 gold 基线 —— 「蒸馏」参照物的正确形态。

为什么要这一层（用户 2026-09-11 指出的方法论根本）：
  基准的参照物应该是**原作里同一角色在同一场景下真说了什么**，
  而不是我自造的违规模式或全局角色分布。

与 `scene_stats.py` 的区别（这是关键修正）：
  · `scene_stats` 是**跨角色**的 per-scene 统计（原型检索全语料、再按场景聚合）
    → 会把别的角色的话算进该场景基线
  · 本模块**先按角色过滤、再按场景原型检索**，得到 (char, scene) 的真基线
    → 也就是「灯在『情绪崩溃』场景真说了什么」这一层的分布

产出 report/scene_char_baseline.json（train，默认）/ report/scene_char_baseline_holdout.json（--split holdout）
  {(char, scene): {profile, exemplars, n}}

split 的设计意图（build_gold.py）：按文本 hash 稳定切 20% 作 holdout，
**调参只能看 train 的分布，验收用 holdout**。2026-09-13 之前本脚本只读 train，
holdout 零消费点（外部评审指出）；现在 `--split holdout` 建出验收基线，
配合 `scene_distill.py --baseline` 完成样本外验收。
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
from _paths import CORPUS_DIR, DATA, REPORT, ROOT, require_corpus  # noqa: E402,F401

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import scenes as SC  # noqa: E402
import style_features as S  # noqa: E402

REPORT = REPORT
MODEL = "BAAI/bge-small-zh-v1.5"
CHARS = {"tomori": "灯", "anon": "爱音", "rana": "乐奈", "soyo": "素世", "taki": "立希"}


def load_corpus(split: str = "train") -> dict[str, list[str]]:
    """按角色分组读语料，只收指定 split 的行。

    train = 蒸馏参照（调参能看的部分）；holdout = 验收参照（最终验收才用）。
    """
    by_char: dict[str, list[str]] = defaultdict(list)
    require_corpus("cn")
    for line in (CORPUS_DIR / "cn.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("split") != split:
            continue
        t = r["text"]
        if len(t) >= 4 and not S.turn_features(t, "cn").silent:
            by_char[r["character"]].append(t)
    return by_char


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=40, help="每 (char,scene) 取多少条最近邻")
    ap.add_argument("--min-n", type=int, default=12, help="少于此数则该组合不产出（标为证据不足）")
    ap.add_argument("--split", choices=["train", "holdout"], default="train",
                    help="用哪部分语料建基线：train=蒸馏参照（默认，与历史一致）；"
                         "holdout=验收参照（调参不得看它，只用于最终验收轮）")
    ap.add_argument("--no-exemplars", action="store_true",
                    help="剥掉例句字段（发布用：本仓库不分发原作文本）")
    ap.add_argument("--out", default="", help=f"输出路径（默认 {REPORT / 'scene_char_baseline.json'}；"
                                              f"holdout 时为 …_holdout.json）")
    args = ap.parse_args()

    from validate_scenes import PROTOTYPES

    by_char = load_corpus(args.split)
    total = sum(len(v) for v in by_char.values())
    if not total:
        raise SystemExit(
            f"[stop] split={args.split} 的可用语料是 0 行——基线会是空壳，"
            f"直接退出不写产物（语料：{CORPUS_DIR / 'cn.jsonl'}）。")
    print(f"[baseline] split={args.split} 可用语料 {total} 行", flush=True)

    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(MODEL, device="cpu")
    keys = list(PROTOTYPES)
    print(f"[baseline] 编码 {len(keys)} 个场景原型 …", flush=True)
    pv = model.encode([PROTOTYPES[k] for k in keys], normalize_embeddings=True,
                      convert_to_numpy=True, batch_size=32, show_progress_bar=False)

    out: dict[str, dict] = {}
    thin: list[str] = []
    for ck, cname in CHARS.items():
        texts = by_char.get(ck, [])
        if not texts:
            continue
        cv = model.encode(texts, normalize_embeddings=True, convert_to_numpy=True,
                          batch_size=64, show_progress_bar=False)
        sim = pv @ cv.T                       # (n_scene, n_char_corpus)
        for i, scene in enumerate(keys):
            idx = list(np.argsort(-sim[i])[: args.k])
            lines = [texts[j] for j in idx]
            if len(lines) < args.min_n:
                thin.append(f"{cname}/{scene}({len(lines)})")
                continue
            prof = S.profile_from_texts(lines, "cn")
            if not prof.get("n"):
                continue
            out[f"{cname}|{scene}"] = {
                "char": cname, "scene": scene, "n": len(lines),
                "length": prof["length"], "n_sent": prof["n_sent"], "n_clause": prof["n_clause"],
                "punct_rate": prof["punct_rate"], "first_person_rate": prof["first_person_rate"],
                "filler_rate": prof["filler_rate"],
                "anchor_density": round(S.anchor_density(lines), 3),
                "exemplars": lines[:8],
            }
            if args.no_exemplars:
                out[f"{cname}|{scene}"].pop("exemplars", None)
        print(f"  {cname}: {len(texts)} 条语料 → 产出 {sum(1 for k in out if k.startswith(cname + '|'))} 个场景基线")

    default_name = "scene_char_baseline.json" if args.split == "train" else "scene_char_baseline_holdout.json"
    dst = Path(args.out) if args.out else (REPORT / default_name)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n共 {len(out)} 个 (角色 × 场景) 基线")
    if thin:
        print(f"样本不足未产出 {len(thin)} 个：{thin[:12]}{' …' if len(thin) > 12 else ''}")
    print(f"-> {dst}")

    # 打印几个样例供核对
    print("\n=== 样例（乐奈/素世的专属场景）===")
    for key in ("乐奈|rana_guitar", "乐奈|rana_cat", "素世|soyo_observe", "素世|soyo_tea",
                "灯|tomori_lyrics", "立希|taki_music_pro"):
        v = out.get(key)
        if not v:
            print(f"  {key}: （未产出）")
            continue
        L = v["length"]
        print(f"  {key}: n={v['n']} 中位={L['p50']:.0f} p90={L['p90']:.0f} "
              f"句数={v['n_sent']['mean']:.2f} 锚点={v['anchor_density']}")
        for e in (v.get("exemplars") or [])[:2]:
            print(f"      {e[:52]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
