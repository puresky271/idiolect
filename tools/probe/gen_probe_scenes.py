"""探针夹具生成：从语料范例反推「用户侧台词」，补满 26 个场景。

为什么反推而不是手写：
  手写夹具是我凭印象编的；从**该场景的真实角色台词**反推用户那句话，
  夹具就锚在语料上，且天然带上该场景的真实话题与语域。

流程（每个 场景×角色 组合）：
  1. 取该场景近邻里属于该角色的真实台词（`report/scene_stats.json`）
  2. 让 LLM 反推出「什么样的用户消息会引出这些回答」——产出 2 条候选
  3. 落盘成 probe 场景条目（含出处与理由，便于人工审查）

产出：report/probe_scenes_v2.json（先审查再并入 probe_runner）
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

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[2]))

import llm_nothink_patch  # noqa: E402,F401
import probe_runner as P  # noqa: E402
import scenes as SC  # noqa: E402

REPORT = REPORT
CHARS = {"爱音": "anon", "素世": "soyo", "灯": "tomori", "立希": "taki", "乐奈": "rana"}
# 哪些角色需要为该场景建夹具（角色专属场景按归属；通用缺口全体铺）
GENERIC_GAP = ["request", "play_along"]

PROMPT = """你在为角色扮演聊天机器人设计**测试夹具**。

角色：{char}
场景类型：**{scene_cn}**
这个场景的判据（对方这一轮在做什么）：{user_side}
角色在这个场景下应该表现成：{char_side}

下面是系统从该角色**官方台词库**里检索到的、属于这个场景的真实台词
（这些就是该角色的实际回答，作为风格与话题的锚点）：

{gold}

请**反推**：什么样的「用户消息」会引出这类回答？
要求：
- 写成用户（对方）会真的打出来的口语，不要书面语、不要问卷腔
- 长度接近真实聊天（8~30 字），可以带具体细节（时间/地点/物件）
- 必须是**能自然引出上面那些回答**的触发语
- 不要提到「测试」「夹具」「场景」等元词汇
- 不要模仿角色的口吻，这是**对方**说的话

输出 JSON（只输出 JSON）：
{{"candidates": [
  {{"user_text": "...", "why": "为什么这句能引出该场景（≤30 字）"}},
  {{"user_text": "...", "why": "..."}}
]}}
"""


def scenes_with_gold() -> dict[str, dict]:
    return json.loads((REPORT / "scene_stats.json").read_text(encoding="utf-8"))


def build_jobs() -> list[tuple[str, str]]:
    """-> [(scene_key, char_cn)]，只覆盖缺口场景。"""
    stats = scenes_with_gold()
    covered = json.loads((REPORT / "scene_coverage.json").read_text(encoding="utf-8"))
    gaps = set(covered["gaps"])
    jobs: list[tuple[str, str]] = []
    for ch_cn, ch_key in CHARS.items():
        for key in SC.CHAR_SCENES.get(ch_key, []):
            if key.key in gaps:
                jobs.append((key.key, ch_cn))
    for key in GENERIC_GAP:
        if key in gaps:
            for ch_cn in CHARS:
                jobs.append((key, ch_cn))
    return jobs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-tokens", type=int, default=600)
    ap.add_argument("--only", default="", help="只跑指定 scene key（逗号分隔）")
    args = ap.parse_args()

    stats = scenes_with_gold()
    all_sc = {s.key: s for s in SC.all_scenes()}
    jobs = build_jobs()
    if args.only:
        want = {x.strip() for x in args.only.split(",")}
        jobs = [j for j in jobs if j[0] in want]
    print(f"[probe-gen] {len(jobs)} 个 场景×角色 组合待生成")

    client = P.make_client()
    model = os.environ.get("LLM_MODEL", "deepseek-flash")
    out: dict[str, list[dict]] = defaultdict(list)
    fails = 0
    for i, (key, ch_cn) in enumerate(jobs, 1):
        sc = all_sc[key]
        ch_key = CHARS[ch_cn]
        st = stats.get(key, {})
        # 取该角色的真实台词（scene_stats 的 exemplars 没标角色，用近邻里角色分布做参考）
        gold = st.get("exemplars", [])[:5]
        if not gold:
            print(f"  [{i}] {key}/{ch_cn}: 无语料范例，跳过")
            fails += 1
            continue
        prompt = PROMPT.format(char=ch_cn, scene_cn=f"{sc.cn}（{key}）", user_side=sc.user_side,
                               char_side=sc.char_side, gold="\n".join(f"- {g}" for g in gold))
        try:
            resp = client.chat.completions.create(
                model=model, messages=[{"role": "user", "content": prompt}],
                temperature=0.4, max_tokens=args.max_tokens,
                extra_body={"thinking": {"type": "disabled"}},
            )
            raw = resp.choices[0].message.content or ""
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            data = json.loads(m.group(0)) if m else {}
            cands = data.get("candidates") or []
            for j, c in enumerate(cands[:2]):
                ut = str(c.get("user_text", "")).strip()
                if not ut:
                    continue
                out[key].append({
                    "id": f"{key}_{ch_key}_{j}",
                    "scene": key, "scene_cn": sc.cn, "char": ch_cn, "char_key": ch_key,
                    "user_text": ut, "why": str(c.get("why", ""))[:40],
                    "gold_exemplars": gold[:3],
                })
            print(f"  [{i}/{len(jobs)}] {key}/{ch_cn}: {len(cands[:2])} 条")
        except Exception as exc:  # noqa: BLE001
            fails += 1
            print(f"  [{i}/{len(jobs)}] {key}/{ch_cn}: ERR {type(exc).__name__}: {exc}")

    (REPORT / "probe_scenes_v2.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    total = sum(len(v) for v in out.values())
    print(f"\n[probe-gen] 生成 {total} 条夹具，覆盖 {len(out)} 场景，失败 {fails}")
    print(f"-> report/probe_scenes_v2.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
