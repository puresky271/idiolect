"""场景体系验证：这些场景在语料里真的互相可分吗？（原型法）

方法：
  1. 每个场景写一句「原型」（该场景下角色会怎么说的典型句）
  2. 把原型与整份金标准语料一起编码
  3. 对每个场景取最近 K 条真实台词
  4. 检查两件事：
     a) 两个场景的最近邻集合**不该高度重合**（重合率高 = 场景冗余，该合并）
     b) 每个场景的近邻里**该有像样的样本量**（没有 = 该场景在语料里不存在，该删）
  这是对聚类失败的补救：不要求全局有簇结构，只要求**场景之间可分**。

产出 report/scene_separation.md + report/scene_exemplars.json
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

REPORT = REPORT
CACHE = HERE / "raw" / "scene_embed_cache.npz"
MODEL = "BAAI/bge-small-zh-v1.5"
CHARS = {"tomori": "灯", "anon": "爱音", "rana": "乐奈", "soyo": "素世", "taki": "立希"}

# 每个场景的原型句：不是评分模板，只用来在语料里定位该场景
PROTOTYPES: dict[str, str] = {
    "crisis": "别说不在了这种话，你现在到底出什么事了",
    "comfort": "你先别哭，我这边在教室，外面在下雨",
    "low_mood": "你上次也这么说。缓过来了没有，别硬撑着",
    "affection": "突然说这个干嘛，我这边还在上课",
    "wellwish": "你这句话里没有你自己，你自己那份呢",
    "probe_stance": "我没那个意思，是你自己绕回来问的",
    "schedule": "三点十分下课，之后直接去排练",
    "fact_qa": "不知道。这个我没听说过",
    "request": "你先把这个弄清楚，别的以后再说",
    "banter": "便利店饭团确实有点干，得配点喝的",
    "meta_language": "哪一句。你说的是我刚才说的哪句话",
    "third_party": "那家伙今天又没来，说她也没用",
    "play_along": "嗯。我也是这么想的",
    "anon_beauty": "那个牌子的粉底我用过，色号要选冷调的",
    "anon_sns": "那张照片我修了半小时，发出去点赞还不错",
    "tomori_nature": "那个是蟬蜕。夏天的时候树上会有很多",
    "tomori_lyrics": "写不出来。写了一行又划掉了",
    "taki_music_pro": "这段鼓点要改，第二小节跟贝斯撞了",
    "taki_soft_spot": "熊猫……那个我当然知道，不用你说",
    "taki_shift": "客人走了要收杯子，凛凛子さん说过好几遍",
    "soyo_observe": "你刚才说缓一阵子就好，今天又来操心别人",
    "soyo_tea": "红茶。大吉岭的香气比较清，下午配点心刚好",
    "soyo_past": "过去的事我记得。不过先做今天的事吧",
    "rana_guitar": "弦松了。换一根就好",
    "rana_food": "抹茶芭菲。放学后去买",
    "rana_cat": "猫在屋檐下面。雨停了它就走",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=25, help="每场景取最近 K 条真实台词")
    ap.add_argument("--overlap-warn", type=float, default=0.6, help="重合率超过则判为冗余场景")
    args = ap.parse_args()

    # 语料
    texts: list[str] = []
    chars: list[str] = []
    require_corpus("cn")
    for line in (CORPUS_DIR / "cn.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("split") != "train":
            continue
        texts.append(r["text"])
        chars.append(r["character"])
    print(f"[scene] 语料 {len(texts)} 条")

    import style_features as S
    keep = [i for i, t in enumerate(texts) if len(t) >= 4 and not S.turn_features(t, "cn").silent]
    texts = [texts[i] for i in keep]
    chars = [chars[i] for i in keep]

    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(MODEL, device="cpu")
    keys = [s.key for s in SC.all_scenes()]
    protos = [PROTOTYPES[k] for k in keys]
    print(f"[scene] encoding {len(texts)} 语料 + {len(protos)} 原型 ...", flush=True)
    cv = model.encode(texts, normalize_embeddings=True, convert_to_numpy=True, batch_size=64,
                      show_progress_bar=False)
    pv = model.encode(protos, normalize_embeddings=True, convert_to_numpy=True, batch_size=32,
                      show_progress_bar=False)

    sim = pv @ cv.T  # (n_scene, n_corpus)
    top: dict[str, list[int]] = {k: list(np.argsort(-sim[i])[: args.k]) for i, k in enumerate(keys)}

    # 场景两两重合率（Jaccard）
    overlap: list[tuple[str, str, float]] = []
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            sa, sb = set(top[a]), set(top[b])
            j = len(sa & sb) / len(sa | sb)
            if j > 0:
                overlap.append((a, b, round(j, 3)))
    overlap.sort(key=lambda x: -x[2])

    # 交叉分配检查：对每个场景近邻，看「最像哪个原型」
    best_proto = np.argmax(sim, axis=0)  # 每条语料最像哪个场景
    purity: dict[str, float] = {}
    for i, k in enumerate(keys):
        idx = top[k]
        hit = sum(1 for j in idx if best_proto[j] == i)
        purity[k] = round(hit / len(idx), 3)

    redundant = [(a, b, j) for a, b, j in overlap if j > args.overlap_warn]
    weak = [k for k, p in purity.items() if p < 0.3 and k in PROTOTYPES]

    lines = ["# 场景体系验证（原型法）\n",
             f"- 模型 `{MODEL}`｜语料 {len(texts)} 条｜每场景近邻 k={args.k}",
             "- 方法：给每个场景写一句原型，取语料最近邻；检查**场景间重合率**与**近邻纯度**。",
             "- 判据：重合率 > %.2f 视为冗余（应合并）；纯度 < 0.30 视为语料中不成立（应删/改）。\n"
             % args.overlap_warn]

    lines.append("## 场景纯度（近邻里「最像本场景」的比例）\n")
    lines.append("| 场景 | 中文 | 纯度 | 近邻样例 |")
    lines.append("|---|---|---|---|")
    for k in keys:
        sc = SC.SCENE_BY_KEY.get(k) or next(s for s in SC.all_scenes() if s.key == k)
        ex = "／".join(texts[j][:14] for j in top[k][:3])
        lines.append(f"| `{k}` | {sc.cn} | {purity[k]:.2f} | {ex} |")

    lines.append("\n## 场景两两重合率（Top-%.0f Jaccard，仅列 >0）\n" % args.k)
    lines.append("| 场景 A | 场景 B | 重合率 | 判定 |")
    lines.append("|---|---|---|---|")
    for a, b, j in overlap[:40]:
        verdict = "冗余，建议合并" if j > args.overlap_warn else ("偏高，观察" if j > 0.4 else "可分")
        lines.append(f"| `{a}` | `{b}` | {j} | {verdict} |")

    lines.append(f"\n## 结论\n")
    lines.append(f"- 冗余场景对（>{args.overlap_warn}）：{len(redundant)}")
    for a, b, j in redundant:
        lines.append(f"  - `{a}` ↔ `{b}`（{j}）")
    lines.append(f"- 纯度不足场景（<0.30）：{len(weak)} → {weak if weak else '无'}")

    (REPORT / "scene_separation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (REPORT / "scene_exemplars.json").write_text(
        json.dumps({k: {"char_dist": dict((CHARS[c], sum(1 for j in v if chars[j] == c))
                                          for c in set(chars[j] for j in v)),
                        "exemplars": [texts[j] for j in v[:10]]}
                    for k, v in top.items()}, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n".join(lines[-12:]))
    print("\n-> report/scene_separation.md, scene_exemplars.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
