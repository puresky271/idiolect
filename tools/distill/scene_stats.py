"""按场景分层统计语料，产出每场景的「字数预期 / 符号 / 物品-话题词表」。

方法论限制（重要）：
  语料只有角色台词、没有用户侧上下文，所以**场景归属靠原型检索近似**，
  不是精确标注。因此本产出用于「逐场景的风格预期参考」，
  场景的**语义判据**仍以 scenes.py 的用户侧定义为准（probe 用它来装配夹具）。

产出：
  report/scene_stats.json     每场景：n / 长度分布 / 标点 / 自称 / 词表 / 代表句
  report/scene_style_table.md 可读表（含 字数预期 与 物品话题词表）
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
from collections import Counter
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import scenes as SC  # noqa: E402
import style_features as S  # noqa: E402

REPORT = REPORT
MODEL = "BAAI/bge-small-zh-v1.5"
CHARS = {"tomori": "灯", "anon": "爱音", "rana": "乐奈", "soyo": "素世", "taki": "立希"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=60, help="每场景采样的近邻条数")
    ap.add_argument("--min-n", type=int, default=20)
    args = ap.parse_args()

    from validate_scenes import PROTOTYPES

    texts: list[str] = []
    chars: list[str] = []
    for line in (CORPUS_DIR / "cn.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("split") != "train":
            continue
        texts.append(r["text"])
        chars.append(r["character"])
    keep = [i for i, t in enumerate(texts) if len(t) >= 4 and not S.turn_features(t, "cn").silent]
    texts = [texts[i] for i in keep]
    chars = [chars[i] for i in keep]

    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(MODEL, device="cpu")
    keys = list(PROTOTYPES)
    print(f"[scene] encoding {len(texts)} 语料 + {len(keys)} 原型 ...", flush=True)
    cv = model.encode(texts, normalize_embeddings=True, convert_to_numpy=True, batch_size=64,
                      show_progress_bar=False)
    pv = model.encode([PROTOTYPES[k] for k in keys], normalize_embeddings=True,
                      convert_to_numpy=True, batch_size=32, show_progress_bar=False)
    sim = pv @ cv.T

    all_scenes = {s.key: s for s in SC.all_scenes()}
    out: dict[str, dict] = {}
    for i, key in enumerate(keys):
        idx = list(np.argsort(-sim[i])[: args.k])
        lines = [texts[j] for j in idx]
        if len(lines) < args.min_n:
            continue
        prof = S.profile_from_texts(lines, "cn")
        if not prof.get("n"):
            continue
        # 物品/话题词表：该场景近邻里显著偏多的实词
        others = [texts[j] for j in range(len(texts)) if j not in set(idx)]
        sig = S.logodds_signature(lines, others, "cn", top=14)
        sc = all_scenes[key]
        out[key] = {
            "cn": sc.cn,
            "char_side": sc.char_side,
            "watch": list(sc.watch),
            "n_sampled": len(lines),
            "length": prof["length"],
            "sent_per_turn": round(prof["n_sent"]["mean"], 2),
            "clause_per_turn": round(prof["n_clause"]["mean"], 2),
            "punct_rate": prof["punct_rate"],
            "first_person_rate": prof["first_person_rate"],
            "filler_rate": prof["filler_rate"],
            "char_dist": {CHARS[c]: n for c, n in Counter(chars[j] for j in idx).most_common()},
            "vocab": [{"word": w, "logodds": round(lo, 2), "count": c} for w, lo, c in sig],
            "exemplars": lines[:6],
        }

    (REPORT / "scene_stats.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = ["# 逐场景语料统计（字数预期 / 符号 / 物品话题词表）\n",
             f"- 来源：金标准 cn 语料按原型检索取近邻（每场景 top-{args.k}），模型 `{MODEL}`",
             "- **限制**：场景归属是检索近似，不是精确标注；语义判据以 scenes.py 的用户侧定义为准\n",
             "| 场景 | 中位字长 | p90 | 句数 | 省略号 | 感叹号 | 问号 | 自称 | 高频物/话题词 |",
             "|---|---|---|---|---|---|---|---|---|"]
    for key, v in out.items():
        L = v["length"]
        vocab = "、".join(x["word"] for x in v["vocab"][:8])
        lines.append(
            f"| `{key}` {v['cn']} | {L['p50']:.0f} | {L['p90']:.0f} | {v['sent_per_turn']:.2f} | "
            f"{v['punct_rate']['…'] * 100:.0f}% | {v['punct_rate']['！'] * 100:.0f}% | "
            f"{v['punct_rate']['？'] * 100:.0f}% | {v['first_person_rate'] * 100:.0f}% | {vocab} |"
        )
    lines.append("\n## 逐场景范例\n")
    for key, v in out.items():
        lines.append(f"\n### `{key}` {v['cn']}")
        lines.append(f"- 角色侧期望：{v['char_side']}")
        lines.append(f"- 评测重点：{', '.join(v['watch'])}")
        for e in v["exemplars"]:
            lines.append(f"  - {e}")
    (REPORT / "scene_style_table.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:6 + len(out)]))
    print(f"\n-> report/scene_stats.json, scene_style_table.md（{len(out)} 场景）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
