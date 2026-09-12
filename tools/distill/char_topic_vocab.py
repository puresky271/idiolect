"""角色「物品 / 话题词表」蒸馏（curated seed + 语料核对）。

为什么不用 jieba 词性过滤：在这个语域上 jieba 判得很差，实测——
  「抹茶」→ 抹/v + 茶/n（被切开）｜「点心」→ v ｜「演出」→ v ｜「曲」→ q ｜「冰淇淋」→ nr
所以词性过滤会把最该收的词全滤掉，同时留下噪声。`char_vocab.json` 的自由 n-gram 则是另一头：
碎片（`ト`/`レ`/`小酷`/`毛猫`）。

本模块走与口癖蒸馏相同的路子：**人工候选表 → 语料实测 → 专指度排序**。
候选来源：五份 `canon.py` 明写的物品/话题 + 已落盘 turn_logic 场景模块内的「可用细节」
+ 语料抽样里反复出现的具体物。零支持或支持过弱的候选**不落盘**（并在报告里列出来）。

产出 report/char_topic_vocab.json / .md
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

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPORT = REPORT
CHARS = {"tomori": "灯", "anon": "爱音", "rana": "乐奈", "soyo": "素世", "taki": "立希"}

# 人工候选（只放**具体物 / 具体话题**；不放语气词、不放人名）
CANDIDATES: dict[str, list[str]] = {
    "tomori": [
        "石头", "创可贴", "笔记本", "歌词", "诗", "星星", "企鹅", "西瓜虫", "独角仙",
        "樱花", "雨", "天空", "云", "颜色", "声音", "味道", "水族馆", "天文", "昆虫",
        "贴纸", "纸星星", "海", "花", "生日", "主唱", "歌", "水滴", "温度", "光",
        "雨", "企鹅", "创可贴",
    ],
    "anon": [
        "照片", "视频", "自拍", "账号", "直播", "化妆品", "口红", "腮红", "美甲",
        "裙子", "时尚", "镜子", "伦敦", "留学", "英语", "甜品", "蛋糕", "面包",
        "手机", "社交", "衣服", "发型", "饰品", "咖啡馆", "甜点", "吉他",
        "练习", "演出", "咖啡", "乐队",
    ],
    "rana": [
        "抹茶", "抹茶芭菲", "芭菲", "冰淇淋", "点心", "荞麦面", "猫", "猫咪",
        "吉他", "弦", "演出", "演奏", "声音", "舞台", "树", "长椅", "毛线球",
        "猫粮", "海报", "外婆", "荞麦", "零食", "琴",
    ],
    "soyo": [
        "红茶", "咖啡", "伯爵", "杯子", "点心", "贝斯", "低音提琴", "乐理", "礼仪",
        "公寓", "花园", "池", "灯笼", "家务", "料理", "妈妈", "裙子", "甜点", "香气",
        "演奏", "学校", "学姐", "茶",
    ],
    "taki": [
        "鼓", "鼓手", "作曲", "熊猫", "排练", "拉面", "面包", "咖啡", "电脑", "谱",
        "姐姐", "花咲川", "羽丘", "打工", "鼓棒", "节奏", "编曲", "熊猫",
        "练习", "演出", "录音", "乐队", "打工",
    ],
}


def main() -> int:
    corpus: dict[str, list[str]] = {k: [] for k in CHARS}
    require_corpus("cn")
    for line in (CORPUS_DIR / "cn.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("split") == "train" and r["character"] in corpus:
            corpus[r["character"]].append(r["text"])
    jp: dict[str, list[str]] = {k: [] for k in CHARS}
    for line in (CORPUS_DIR / "jp.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("split") == "train" and r["character"] in jp:
            jp[r["character"]].append(r["text"])

    out: dict[str, dict] = {}
    lines = ["# 角色物品/话题词表（语料核对版）\n",
             "> 候选来自 canon / turn_logic / 语料抽样；每条都给出实测次数与专指度。",
             "> `专指度` = 本人每万字频次 / 最高他人每万字频次。**零支持的不落盘**。\n"]

    for ck, cname in CHARS.items():
        texts = corpus[ck]
        n_self = sum(len(t) for t in texts) or 1
        rows, dropped = [], []
        for w in dict.fromkeys(CANDIDATES[ck]):      # 去重且保序
            cnt = sum(t.count(w) for t in texts)
            if cnt < 3:
                dropped.append({"word": w, "count": cnt})
                continue
            others_max, who = 0.0, ""
            for ok in CHARS:
                if ok == ck:
                    continue
                ro = sum(t.count(w) for t in corpus[ok]) / (sum(len(t) for t in corpus[ok]) or 1)
                if ro > others_max:
                    others_max, who = ro, ok
            rate = cnt / n_self
            rows.append({
                "word": w, "count": cnt, "per_10k": round(rate * 10000, 1),
                "line_share": round(sum(1 for t in texts if w in t) / len(texts), 4),
                "spec": round(rate / others_max, 2) if others_max else 999.0,
                "top_other": CHARS[who] if who else "",
                "jp_count": sum(t.count(w) for t in jp[ck]),
            })
        rows.sort(key=lambda x: (-x["spec"], -x["count"]))
        out[cname] = {"char": cname, "n": len(texts), "words": rows, "dropped": dropped}
        lines.append(f"\n## {cname}（n={len(texts)}）\n")
        lines.append("**落盘词表（专指度 ≥2 优先）**：")
        lines.append("　" + "、".join(
            f"`{r['word']}`({r['count']}, ×{r['spec']})" for r in rows if r["spec"] >= 2))
        lines.append("\n**共用但真实出现**：")
        lines.append("　" + "、".join(
            f"`{r['word']}`({r['count']})" for r in rows if r["spec"] < 2))
        if dropped:
            lines.append("\n**零/弱支持（不落盘）**：")
            lines.append("　" + "、".join(f"`{d['word']}`({d['count']})" for d in dropped))

    (REPORT / "char_topic_vocab.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    (REPORT / "char_topic_vocab.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print("\n-> report/char_topic_vocab.md / .json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
