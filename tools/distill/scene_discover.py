"""场景发现：对金标准语料做 embedding 聚类，产出候选场景体系。

为什么用聚类而不是直接让 LLM 分类：
  直接分类 = 把我预设的类别强加上去；聚类能发现**语料里真实存在**的语用场景，
  再用 LLM 给簇命名并判定内聚度。两者结合才既有据可依又不遗漏。

流程：
  1. 每角色分层抽样 N 条（去重、排除过短/沉默行）
  2. BAAI/bge-small-zh-v1.5（本地已缓存）编码
  3. KMeans 扫 k，用 silhouette 选最优
  4. 每簇取距质心最近的若干条当代表话语
  5. LLM 给每簇命名 + 判内聚度（是否真是一个场景）

产出：
  report/scene_clusters.json   每簇：size / 角色分布 / 代表话语
  report/scene_candidates.md   可读报告
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

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
REPORT = REPORT
CACHE = HERE / "raw" / "scene_embed_cache.npz"
CHARS = {"tomori": "灯", "anon": "爱音", "rana": "乐奈", "soyo": "素世", "taki": "立希"}
MODEL = "BAAI/bge-small-zh-v1.5"


def load_corpus(per_char: int, seed: int = 17) -> tuple[list[str], list[str]]:
    """分层抽样：每角色取 per_char 条（优先中等长度，避开无法承载场景的极短句）。"""
    import random

    import style_features as S

    by_char: dict[str, list[str]] = defaultdict(list)
    for line in (CORPUS_DIR / "cn.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("split") != "train":
            continue
        t = r["text"]
        if len(t) < 4 or S.turn_features(t, "cn").silent:
            continue
        by_char[r["character"]].append(t)

    rng = random.Random(seed)
    texts: list[str] = []
    chars: list[str] = []
    for key, pool in by_char.items():
        uniq = list(dict.fromkeys(pool))
        rng.shuffle(uniq)
        # 长度分层：一半取 6~18 字的短口语，一半取 19~40 字的长句，兼顾两类语用
        short = [t for t in uniq if 6 <= len(t) <= 18]
        long_ = [t for t in uniq if 19 <= len(t) <= 40]
        take = short[: per_char // 2] + long_[: per_char - per_char // 2]
        texts.extend(take)
        chars.extend([key] * len(take))
    return texts, chars


def embed(texts: list[str]) -> np.ndarray:
    if CACHE.exists():
        d = np.load(CACHE, allow_pickle=True)
        if list(d["texts"]) == texts:
            print(f"[scene] embedding cache hit ({len(texts)} 条)")
            return d["vec"]
    print(f"[scene] encoding {len(texts)} 条 with {MODEL} ...", flush=True)
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(MODEL, device="cpu")
    vec = model.encode(texts, normalize_embeddings=True, convert_to_numpy=True, batch_size=32,
                       show_progress_bar=False)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(CACHE, texts=np.array(texts, dtype=object), vec=vec)
    print(f"[scene] encoded -> {CACHE.name}")
    return vec


def pick_k(vec: np.ndarray, ks: list[int]) -> tuple[int, dict[int, float]]:
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score

    scores: dict[int, float] = {}
    for k in ks:
        km = KMeans(n_clusters=k, n_init=10, random_state=17).fit(vec)
        s = silhouette_score(vec, km.labels_, sample_size=min(600, len(vec)), random_state=17)
        scores[k] = round(float(s), 4)
        print(f"  k={k:<3} silhouette={s:.4f}")
    best = max(scores, key=scores.get)
    return best, scores


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-char", type=int, default=180)
    ap.add_argument("--k", default="", help="固定 k；缺省用 silhouette 扫 8..24")
    ap.add_argument("--reps", type=int, default=8, help="每簇代表话语条数")
    args = ap.parse_args()

    texts, chars = load_corpus(args.per_char)
    print(f"[scene] 样本 {len(texts)} 条｜角色分布 {dict(Counter(chars))}")
    vec = embed(texts)

    if args.k:
        k = int(args.k)
        scores = {}
        from sklearn.cluster import KMeans
        km = KMeans(n_clusters=k, n_init=10, random_state=17).fit(vec)
    else:
        k, scores = pick_k(vec, [10, 12, 14, 16, 18, 20, 22, 24])
        from sklearn.cluster import KMeans
        km = KMeans(n_clusters=k, n_init=10, random_state=17).fit(vec)
    print(f"[scene] chosen k={k}  (silhouette {scores})")

    labels = km.labels_
    centroids = km.cluster_centers_
    out: list[dict] = []
    for ci in range(k):
        idx = np.where(labels == ci)[0]
        if len(idx) == 0:
            continue
        d = np.linalg.norm(vec[idx] - centroids[ci], axis=1)
        order = idx[np.argsort(d)]
        reps = [texts[i] for i in order[: args.reps]]
        char_dist = Counter(chars[i] for i in idx)
        # 内聚度：簇内到质心的平均余弦距离（越小越内聚）
        cohesion = float(np.mean(d))
        out.append({
            "cluster": ci, "size": int(len(idx)),
            "cohesion": round(cohesion, 4),
            "char_dist": {CHARS[c]: n for c, n in char_dist.most_common()},
            "representatives": reps,
        })
    out.sort(key=lambda x: -x["size"])

    (REPORT / "scene_clusters.json").write_text(
        json.dumps({"k": k, "silhouette": scores, "n_samples": len(texts), "clusters": out},
                   ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [f"# 语料场景发现（embedding 聚类）\n",
             f"- 模型 `{MODEL}`｜样本 {len(texts)} 条（每角色 {args.per_char}）｜k={k}",
             f"- silhouette 扫描：{scores}\n"]
    for c in out:
        lines.append(f"\n## 簇 {c['cluster']}（{c['size']} 条，内聚 {c['cohesion']}）")
        lines.append(f"角色分布：{c['char_dist']}")
        lines.append("")
        for r in c["representatives"]:
            lines.append(f"- {r}")
    (REPORT / "scene_candidates.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[scene] -> report/scene_candidates.md（{len(out)} 簇）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
