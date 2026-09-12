"""核实候选触发词在目标角色语料中的实际出现次数。

目的：turn_logic 的触发词若在语料里根本不存在，模块永远不会触发（静默失效）。
本脚本把候选词逐个查证，只保留有实证的。
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

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

CANDIDATES = {
    "rana": {
        "guitar": ["吉他", "弦", "弹", "演出", "排练", "演奏", "调音", "拨片", "音", "曲"],
        "food": ["抹茶", "抹", "芭菲", "冰淇淋", "点心", "荞麦面", "甜", "吃", "喝", "点心"],
        "cat": ["猫", "屋檐", "院子", "池子", "雨", "窗", "野猫", "猫猫"],
    },
    "soyo": {
        "observe": ["又说", "昨天", "上次", "不是", "为什么", "你自己", "这次", "倒是"],
        "tea": ["红茶", "茶", "咖啡", "伯爵", "大吉岭", "泡", "点心", "奶茶"],
        "past": ["CRYCHIC", "记得", "春日影", "以前", "过去", "那时候", "祥子", "睦"],
    },
    "taki": {
        "music_pro": ["鼓", "编曲", "小节", "贝斯", "节拍", "和弦", "旋律", "练"],
    },
    "anon": {
        "beauty": ["腮红", "口红", "粉底", "色号", "发夹", "裙子", "香水", "柔顺剂", "牌"],
    },
}


def corpus(char_key: str) -> list[str]:
    out = []
    require_corpus("cn")
    for line in (CORPUS_DIR / "cn.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            if r["character"] == char_key:
                out.append(r["text"])
    return out


def main() -> int:
    for char_key, scenes in CANDIDATES.items():
        texts = corpus(char_key)
        print(f"\n=== {char_key}（语料 {len(texts)} 条）===")
        for scene, words in scenes.items():
            rows = []
            for w in dict.fromkeys(words):  # 去重保序
                n = sum(1 for t in texts if w in t)
                rows.append((w, n))
            kept = [f"{w}({n})" for w, n in rows if n > 0]
            dropped = [w for w, n in rows if n == 0]
            print(f"  [{scene}] 可用: {'、'.join(kept) if kept else '（无）'}")
            if dropped:
                print(f"           剔除（语料中不存在）: {'、'.join(dropped)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
