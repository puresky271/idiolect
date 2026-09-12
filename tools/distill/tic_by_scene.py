"""场景条件下的口癖分布 —— 把「蒸馏」推进到口癖层。

方法论与 `scene_char_baseline.py` 一致：
  先按角色过滤语料，再按场景原型做最近邻检索，得到「这个角色在这个场景里真说了什么」，
  然后在检索到的集合里统计口癖频次，与**该角色的全局频次**相比得到 lift。

lift > 1 表示「这个口癖在这个场景里比平时更常出现」——
这正是要把口癖写进 scene style block 的依据，而不是凭感觉分配。

例：立希的「哈？」全局 10.6/万字，若在 `taki_soft_spot` 里 lift < 1 而在 `crisis` 里 lift > 1，
     就应该把「哈？」写进 crisis 的 block、而不是 soft_spot。

产出 report/tic_by_scene.json / .md
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

# 只统计**已被语料确认**的口癖（来自 tic_profile 核对后的清单，不含零支持候选）
TICS: dict[str, list[str]] = {
    "tomori": ["……", "诶……", "嗯……", "呃", "啊……", "唔……", "小爽世", "小爱", "小立希", "小乐奈", "不知道", "嗯"],
    "anon": ["诶？", "诶——", "诶~", "诶诶", "啊——", "啊哈哈", "嘛", "哎呀", "咦", "啊", "诶", "哦", "对吧", "不过", "谢谢"],
    "rana": ["哼哼", "哼", "ふふん", "呼", "好吃", "有趣", "有趣的女人", "无聊", "抹茶", "芭菲", "吉他", "猫",
             "不够", "还不够", "我要", "我想吃", "嗯。", "我知道了", "Rikki"],
    "soyo": ["哦", "呢", "的哦", "的呢", "了吧", "呵呵", "这样啊", "这样", "如果", "只是", "小灯", "小爱音",
             "小立希", "小乐奈", "小睦", "嗯，", "嘛"],
    "taki": ["哈？", "啊？", "野猫", "那家伙", "这家伙", "不，", "行了", "吵", "烦", "唉……", "真是的",
             "别", "好了", "喂", "灯", "不过", "总之"],
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=120, help="每 (char,scene) 取多少条最近邻")
    ap.add_argument("--min-count", type=int, default=5, help="cell 内至少出现几次才报")
    ap.add_argument("--min-lift", type=float, default=1.4, help="lift 下限")
    args = ap.parse_args()

    from validate_scenes import PROTOTYPES

    by_char: dict[str, list[str]] = defaultdict(list)
    for line in (CORPUS_DIR / "cn.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("split") != "train":
            continue
        t = r["text"]
        if len(t) >= 4 and not S.turn_features(t, "cn").silent:
            by_char[r["character"]].append(t)

    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(MODEL, device="cpu")
    keys = list(PROTOTYPES)
    print(f"[tic_by_scene] 编码 {len(keys)} 个场景原型 …", flush=True)
    pv = model.encode([PROTOTYPES[k] for k in keys], normalize_embeddings=True,
                      convert_to_numpy=True, batch_size=32, show_progress_bar=False)

    out: dict[str, dict] = {}
    for ck, cname in CHARS.items():
        texts = by_char.get(ck, [])
        if not texts:
            continue
        vocab = [w for w in TICS[ck]]
        n_self = sum(len(t) for t in texts) or 1
        # 全局基线：每万字频次
        base = {w: sum(t.count(w) for t in texts) / n_self * 10000 for w in vocab}
        cv = model.encode(texts, normalize_embeddings=True, convert_to_numpy=True,
                          batch_size=64, show_progress_bar=False)
        sim = pv @ cv.T
        for i, scene in enumerate(keys):
            idx = list(np.argsort(-sim[i])[: args.k])
            lines = [texts[j] for j in idx]
            n_cell = sum(len(t) for t in lines) or 1
            rows = []
            for w in vocab:
                c = sum(t.count(w) for t in lines)
                if c < args.min_count:
                    continue
                rate = c / n_cell * 10000
                lift = rate / base[w] if base[w] else 999.0
                if lift < args.min_lift:
                    continue
                rows.append({"tic": w, "count": c, "per_10k": round(rate, 1),
                             "base_per_10k": round(base[w], 1), "lift": round(lift, 2)})
            if not rows:
                continue
            rows.sort(key=lambda x: (-x["lift"], -x["count"]))
            out[f"{cname}|{scene}"] = {"char": cname, "scene": scene, "k": len(lines), "tics": rows}
        print(f"  {cname}: {len(texts)} 条 → {sum(1 for k in out if k.startswith(cname + '|'))} 个场景有显著口癖")

    (REPORT / "tic_by_scene.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = ["# 场景条件下的口癖 lift（蒸馏到口癖层）\n",
             f"> 每 (角色 × 场景) 取 {args.k} 条最近邻语料，统计口癖每万字频次 / 该角色全局频次。",
             f"> 只报 cell 内出现 ≥{args.min_count} 次且 lift ≥{args.min_lift} 的口癖。",
             "> lift > 1 = 这个场景里她比平时更常说；这是把口癖写进 scene block 的依据。\n"]
    for key, v in out.items():
        lines.append(f"\n## {key}（k={v['k']}）\n")
        for r in v["tics"][:10]:
            lines.append(f"- `{r['tic']}` ×{r['count']}　lift {r['lift']}（本场景 {r['per_10k']} / 全局 {r['base_per_10k']} 每万字）")
    (REPORT / "tic_by_scene.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n-> report/tic_by_scene.md / .json（{len(out)} 个 cell）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
