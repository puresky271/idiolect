"""探针闭环驱动：固定夹具 → 跑生成 → 三层评分 → 报告。

关键设计（决定实验是否可信）：
  1. **夹具逐字节固定**：对每个角色取一份真实 messages dump，只替换最后一条 user 内容。
     整段 system prompt（含当天记忆/日程/世界状态）在整轮实验中保持完全一致，
     所以 before/after 的差异只可能来自我们改的 prompt 分片。
  2. **参数固定**：temperature=0.75、max_tokens=120（两臂一致，排除采样参数干扰）。
  3. **分布级评分**：fidelity 需要多条样本才有意义，所以每场景 N 次；
     聚合到「角色 × 臂」再算分布，而不是逐条算。
  4. **中性对照场景**：用于识别「靠变冷淡刷分」——若中性场景的 fidelity 也一起掉，
     说明补丁在压长度而不是在塑角色。

产物：
  report/probe_<label>.jsonl   逐条原始回复
  report/probe_<label>.md      臂间对比报告
用法：
  py -X utf8 probe_runner.py --label baseline --runs 6                # 只跑 current 臂
  py -X utf8 probe_runner.py --label v42 --runs 6 --arm-name patched  # 自定义臂名
  py -X utf8 probe_runner.py --label dry --dry-run                    # 不调 LLM，只验证装配
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
import sys
import time
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))

# 必须在 import openai client **之前**应用：生产靠它把 thinking 控制注入每个调用点。
# 漏掉它会让 max_tokens=120 全被 reasoning 烧掉、content 为空（finish_reason=length）,
# 探针会退化成在测截断伪影而不是风格。
import llm_nothink_patch  # noqa: E402,F401

import rules as R  # noqa: E402
import style_features as S  # noqa: E402
import prompt_patch as PP  # noqa: E402
import reply_clean as RC  # noqa: E402
import mock_clock as MOCK  # noqa: E402
from probe_scenarios import SCENARIOS  # noqa: E402

FIXTURES = ROOT / "fixtures"          # 本仓库自带的占位夹具（优先）
SMOKE_OUT = ROOT / "_offline_smoke_out"  # 兼容：外部真实运行时 dump 也可以放这里
CHARS = ["爱音", "灯", "立希", "素世", "乐奈"]
CHARKEY = {"爱音": "anon", "灯": "tomori", "立希": "taki", "素世": "soyo", "乐奈": "rana"}


def newest_messages(char: str) -> Path:
    """先找 fixtures/（本仓库自带），再找 _offline_smoke_out/（外部 dump）。"""
    for base, pattern in ((FIXTURES, f"messages_{char}.json"),
                          (FIXTURES, f"messages_{char}_*.json"),
                          (SMOKE_OUT, f"messages_{char}_*.json")):
        cands = sorted(base.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
        if cands:
            return cands[0]
    raise SystemExit(
        f"没有 {char} 的夹具。跑 `py -X utf8 tools/probe/make_fixtures.py` 生成占位夹具，"
        f"或把你的运行时 dump 放进 {FIXTURES}/。")


def find_last_user_idx(msgs: list[dict]) -> int:
    for i in range(len(msgs) - 1, -1, -1):
        if msgs[i].get("role") == "user":
            return i
    raise SystemExit("fixture 里没有 user 消息")


def load_fixture(char: str) -> list[dict]:
    return json.loads(newest_messages(char).read_text(encoding="utf-8"))


def llm_extra_body(thinking: str) -> dict:
    """thinking 轴：'off' 显式关（可复现、便宜）；'on' 走 llm_nothink_patch 默认（生产现状）。

    注意 llm_nothink_patch 会把 max_tokens 加上 DEEPSEEK_REASONING_BUDGET(默认1500)，
    且 reasoning 消耗实测在 84~1620 之间波动——**大预算下仍会出现 content 为空的样本**，
    这类样本必须计为无效而不是「模型拒答」。
    """
    if thinking == "off":
        return {"thinking": {"type": "disabled"}}
    if thinking == "on":
        return {"thinking": {"type": "enabled"}}
    return {}


def sanitize_no_proxy() -> None:
    """httpx 0.28 会把 NO_PROXY 条目按 host:port 解析，IPv6 方括号记法 `[::1]` 会
    被切成非法端口 ':1]'，导致 OpenAI() 构造阶段直接抛 InvalidURL。
    这里只剔除方括号 IPv6 记法（loopback 本来就不需要代理），保留其余规则。
    """
    for var in ("NO_PROXY", "no_proxy"):
        raw = os.environ.get(var)
        if not raw:
            continue
        kept = [p.strip() for p in raw.split(",") if p.strip() and not (p.strip().startswith("[") and "]" in p)]
        os.environ[var] = ",".join(kept)


def make_client():
    sanitize_no_proxy()
    try:
        import secrets_loader

        secrets_loader.sync_env_from_secrets()
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] secrets_loader: {exc}", flush=True)
    from openai import OpenAI

    key = os.environ.get("LLM_API_KEY") or ""
    base = os.environ.get("LLM_BASE_URL") or ""
    if not key:
        raise SystemExit("LLM_API_KEY 为空——检查 .streamlit/secrets.toml")
    return OpenAI(api_key=key, base_url=base)


def derive_anchor_ref(char: str) -> float | None:
    """anchor_ref 的**唯一来源**：随仓库发布的场景基线，该角色各场景格按 n 加权均值。

    为什么定死这一个来源（2026-09-13 评审 N3）：anchor_ref 曾经有过两个真相来源——
    画像字段（全 train 行实测，含沉默回合）与场景基线派生值——乐奈两者差 28%，
    同一份产物走不同路径 composite 差 3.2 分，是 accept_check 默认容差的 3 倍，
    足以让同一臂被判通过或退回。场景基线与场景评分（scene_distill）同源、
    随仓库发布、有无语料都是同一个文件，所以定为唯一口径；画像不再导出自己的
    anchor_density 字段。返回 None = 连场景基线也没有（composite_score 走 1.0 兜底）。
    """
    p = DATA / "scene_char_baseline.json"
    if not p.exists():
        return None
    base = json.loads(p.read_text(encoding="utf-8"))
    cells = [c for k, c in base.items()
             if k.startswith(f"{char}|") and c.get("n") and c.get("anchor_density") is not None]
    if not cells:
        return None
    return sum(c["n"] * c["anchor_density"] for c in cells) / sum(c["n"] for c in cells)


def score_arm(char: str, replies: list[str], gold: dict) -> dict:
    """对一个「角色 × 臂」的全部回复做三层评分。

    头号指标是 composite（风格保真 0.65 + 内容锚点 0.35，见 style_features.composite_score）：
    单看 fidelity 会奖励「短」——实测纯助手腔 fidelity 84.9 高于真像角色的 82.0
    （2026-09-13 外部评审用本仓库函数复算确认），所以上报口径以 composite 领衔，
    fidelity 保留为对照列。
    """
    prof = S.profile_from_texts(replies, "cn")
    out: dict = {"n_bubbles": prof.get("n", 0), "n_replies": len(replies)}
    if not prof.get("n") or not gold.get("n"):
        return out
    fid = S.style_fidelity(gold, prof)
    # anchor_ref 唯一定死场景基线派生值（见 derive_anchor_ref 的 docstring）——
    # 有语料/无语料两条路径产出同一个参照，同一份产物不会走出两个 composite
    comp = S.composite_score(gold, prof, replies, anchor_ref=derive_anchor_ref(char))
    out["composite"] = comp["composite"]
    out["anchor_density"] = comp["anchor_density"]
    out["anchor_ref"] = comp["anchor_ref"]
    out["anchor_score"] = comp["anchor_score"]
    out["fidelity"] = fid["fidelity"]
    out["rmse"] = fid["rmse"]
    out["worst_dims"] = sorted(
        (
            {"dim": k, **v}
            for k, v in fid["drift"].items()
            if v.get("z") is not None or abs(v.get("delta") or 0) > 0.05
        ),
        key=lambda d: -abs(d["z"] if d["z"] is not None else (d.get("delta") or 0) / 0.5),
    )[:5]

    # 硬规则
    tot = vhit = anyhit = 0
    by_rule: dict[str, int] = defaultdict(int)
    for t in replies:
        for bubble in [b for b in t.split("\n") if b.strip()] or [t]:
            f = S.turn_features(bubble, "cn")
            if f.silent:
                continue
            tot += 1
            hits = R.check_text(char, bubble, sentence_count=f.n_sent, length=f.length)
            if hits:
                anyhit += 1
            if any(h.level == "V" for h in hits):
                vhit += 1
            for h in hits:
                by_rule[h.rule] += 1
    out["hard_n"] = tot
    out["hard_any_rate"] = round(anyhit / tot, 4) if tot else 0.0
    out["hard_v_rate"] = round(vhit / tot, 4) if tot else 0.0
    out["hard_by_rule"] = {k: round(v / tot, 4) for k, v in sorted(by_rule.items(), key=lambda x: -x[1])[:6]} if tot else {}

    # 具体处境锚点率（防「变冷淡刷分」的正向指标）
    import re

    concrete = re.compile(r"(教室|学校|排练|RiNG|吉他|贝斯|鼓|抹茶|布丁|红茶|咖啡|便利店|饭团|雨|窗|桌子|手机|手机|课|车站|电车|猫|笔记本|便当|面包|鞋|伞)")
    conc = sum(1 for t in replies if concrete.search(t))
    out["concrete_anchor_rate"] = round(conc / len(replies), 4) if replies else 0.0
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--runs", type=int, default=6, help="每场景生成次数（分布级评分需要 >=6）")
    ap.add_argument("--arm-name", default="current", help="本次要跑的臂名（写入结果）")
    ap.add_argument("--dry-run", action="store_true", help="不调 LLM，只验证夹具装配")
    ap.add_argument("--chars", default="", help="只跑指定角色（逗号分隔）")
    ap.add_argument("--temperature", type=float, default=0.75)
    ap.add_argument("--max-tokens", type=int, default=420, help="生产主聊天路径量级（非 idle 的 120）")
    ap.add_argument("--thinking", choices=["on", "off", "default"], default="off",
                    help="探针默认关思考：可复现、免截断伪影；'on' 用于对照生产现状")
    ap.add_argument("--patch", default="none", help="prompt 补丁名（见 prompt_patch.py：none / targets / targets_cap / targets_cap_anchor）")
    ap.add_argument("--registry", action="store_true",
                    help="用 probe_registry（v1 手工 + v2 语料反推，覆盖 26 场景）而不是 probe_scenarios")
    ap.add_argument("--drop-risk", action="store_true", help="与 --registry 同用时剔除 canon 敏感夹具")
    ap.add_argument("--scenes", default="", help="只跑这些场景 key（逗号分隔；与 --registry 同用）")
    ap.add_argument("--cats", default="", help="只跑这些类别（逗号分隔，如 生活化,个人钩子；与 --registry 同用）")
    ap.add_argument("--assemble", action="store_true",
                    help="system 段用 idiolect.assemble 按当轮 user 现场装配"
                         "（canon + voice + 场景化长度目标 + turn_logic 四层全上）。"
                         "自带占位夹具时需要它；外部真实 dump 不需要。")
    ap.add_argument("--turn-logic", action="store_true",
                    help="把**生产 turn_logic**（场景模块 block）按夹具的 user_text 注入 system prompt。"
                         "没有它，probe 永远测不到 turn_logic 的效果——这是本框架此前的盲区。")
    args = ap.parse_args()

    only = [c for c in args.chars.split(",") if c]
    out_jsonl = REPORT / f"probe_{args.label}.jsonl"
    out_md = REPORT / f"probe_{args.label}.md"
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)

    gold: dict[str, dict] = {}
    gold_src = ""
    corpus_cn = CORPUS_DIR / "cn.jsonl"
    if corpus_cn.exists():
        # 有语料：现场按同一套特征代码算 gold 画像（与历史批次数字逐位可比）
        for char, key in CHARKEY.items():
            texts = []
            for line in corpus_cn.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    r = json.loads(line)
                    if r["character"] == key and r.get("split") == "train":
                        texts.append(r["text"])
            gold[char] = S.profile_from_texts(texts, "cn")
        gold_src = f"语料现场计算（{corpus_cn}）"
    else:
        # 无语料：用随仓库发布的派生画像（同样的聚合量，不是原作文本）。
        # 本仓库不分发原作台词，所以这是**默认**路径；数字口径与上面一致。
        prof_path = DATA / "style_profiles.json"
        if not prof_path.exists():
            print(f"[probe] 既没有语料（{corpus_cn}）也没有 {prof_path}——"
                  f"先跑 tools/distill/export_profiles.py，或用 IDIOLECT_CORPUS_DIR 指向语料目录",
                  flush=True)
            return 2
        raw = json.loads(prof_path.read_text(encoding="utf-8"))
        for char, key in CHARKEY.items():
            gold[char] = raw.get(key, {"n": 0})
        gold_src = f"派生统计 {prof_path.name}（无原作文本）"
    # anchor_ref 不走 gold 画像（有过两个真相来源的教训，见 derive_anchor_ref）：
    # 两条路径统一从场景基线派生，启动时就把来源印出来
    refs = {c: derive_anchor_ref(c) for c in CHARKEY}
    missing = [c for c, r in refs.items() if r is None]
    print(f"[probe] gold 画像来源 = {gold_src}｜anchor_ref 来源 = 场景基线派生（唯一口径）"
          + (f"｜⚠ 派生失败走兜底：{'、'.join(missing)}" if missing else ""), flush=True)

    client = None if args.dry_run else make_client()
    model = os.environ.get("LLM_MODEL", "deepseek-flash")
    extra_body = llm_extra_body(args.thinking)
    targets = PP.load_targets("cn")
    print(f"[probe] label={args.label} arm={args.arm_name} runs={args.runs} model={model} "
          f"thinking={args.thinking} max_tokens={args.max_tokens} patch={args.patch} dry={args.dry_run}", flush=True)
    print(f"[probe] patch = {PP.describe(args.patch)}", flush=True)
    print(f"[probe] 时钟 = {MOCK.describe()}", flush=True)
    if not MOCK.is_mocked():
        print("[probe] ⚠ 真实时钟：本批数字不可与 mock 白天时间的批次比较", flush=True)
    print(f"[probe] turn_logic 注入 = {args.turn_logic}", flush=True)

    records: list[dict] = []
    per_char_replies: dict[str, list[str]] = defaultdict(list)

    if args.registry:
        import probe_registry as PR

        reg = PR.registry(drop_risk=args.drop_risk)
        want_scenes = {s for s in (args.scenes or "").split(",") if s}
        if want_scenes:
            reg = [x for x in reg if x.get("scene") in want_scenes]
        want_cats = {c for c in (args.cats or "").split(",") if c}
        if want_cats:
            reg = [x for x in reg if x.get("cat") in want_cats]
        plan: dict[str, list[dict]] = defaultdict(list)
        for it in reg:
            plan[it["char"]].append({"id": it["id"], "cat": it["cat"], "text": it["user_text"],
                                     "scene": it["scene"], "source": it["source"], "risk": it["risk"]})
        print(f"[probe] registry: {len(reg)} 条夹具，覆盖 {len({x['scene'] for x in reg})} 场景", flush=True)
    else:
        plan = {c: [{"id": s["id"], "cat": s["cat"], "text": s["text"], "scene": "", "source": "v1", "risk": False}
                    for s in scs] for c, scs in SCENARIOS.items()}

    for char, scenarios in plan.items():
        if only and char not in only:
            continue
        fixture = load_fixture(char)
        ui = find_last_user_idx(fixture)
        base_sys = fixture[0]["content"]
        # targets_scene 的补丁**逐场景**重算（见下方循环），这里不预计算——
        # 预计算时没有场景信息，会撞上「无基线即报错」的守卫（2026-09-12）。
        if args.patch == "targets_scene":
            patched_sys = base_sys
        else:
            patched_sys = PP.apply_patch(base_sys, CHARKEY[char], args.patch, targets)
        print(f"[probe] {char}: fixture={newest_messages(char).name} user_idx={ui} "
              f"scenarios={len(scenarios)} sys "
              f"{'assemble(四层)' if args.assemble else f'{len(base_sys)}->{len(patched_sys)}'} chars", flush=True)
        for sc in scenarios:
            msgs = json.loads(json.dumps(fixture))
            # ── system 段的三个来源，优先级从高到低 ──
            #   1. --assemble ：按本轮的 user 现场装配四层（占位夹具走这条）
            #   2. --patch targets_scene ：逐场景重算长度目标补丁（差分实验）
            #   3. 夹具自带的 system（外部真实 dump）
            # 2026-09-13 修：此前 1 和 3 是并列的两个 if/else，装配结果被
            # `msgs[0]["content"] = patched_sys` 原地覆盖，--assemble 静默变成空操作
            # （占位夹具的 system 为空 → 模型收到空 system，回复退化成通用助手腔）。
            if args.assemble:
                from idiolect.assemble import build_system_prompt
                sys_text = build_system_prompt(
                    char, sc["text"], session_id=f"probe:{args.label}:{char}:{sc['id']}",
                    now=MOCK.mock_now())
            elif args.patch == "targets_scene":
                # targets_scene 需要「本轮场景」才知道注入哪套基线 → 逐场景重新算
                sys_text = PP.apply_patch(
                    base_sys, CHARKEY[char], args.patch, targets,
                    scene=sc.get("scene", ""), scene_cn=sc.get("cat", ""))
            else:
                sys_text = patched_sys
            # 补丁可以**叠加**在装配结果之上：插入点 = style_target 层开始
            # （persona card 末尾）。装配结果必有该层；夹具/外部 dump 里没有层边界时
            # prompt_patch 会直接报错退出，而不是悄悄换个落点（2026-09-13 评审 C1：
            # 旧锚点曾落在一句交叉引用内部，把句子腰斩）。
            if args.assemble and args.patch != "none":
                sys_text = PP.apply_patch(
                    sys_text, CHARKEY[char], args.patch, targets,
                    scene=sc.get("scene", ""), scene_cn=sc.get("cat", ""))
            msgs[0]["content"] = sys_text
            msgs[ui]["content"] = sc["text"]
            # 空 system 会让模型退回通用助手腔（模板化安慰/客服腔），此时测到的是
            # 「没有角色 prompt 的模型」，不是被评测的 prompt 分片。宁可当场炸掉。
            if len(msgs[0]["content"]) < 1000:
                raise SystemExit(
                    f"[probe] system 段只有 {len(msgs[0]['content'])} 字符 —— 装配没生效。"
                    f"检查 --assemble / --patch / 夹具自带 system；不要在这种状态下取数。")
            # ── 生产 turn_logic 注入 ──────────────────────────────
            # 逐场景算一次即可（同场景 N 次 run 的 block 内容相同）；
            # session_id 按 (label,char,scenario) 唯一，避免跨场景共享去重状态。
            tl_text = ""
            if args.turn_logic:
                try:
                    import idiolect.registry as RP
                    tl_text = RP.render_turn_special_block(
                        char, sc["text"],
                        session_id=f"probe:{args.label}:{char}:{sc['id']}",
                        is_developer=False, mode="chat", now_jst=MOCK.mock_now(),
                    ) or ""
                except Exception as exc:  # noqa: BLE001
                    print(f"[probe] turn_logic 注入失败 {char}/{sc['id']}: {exc}", flush=True)
                    tl_text = ""
                if tl_text:
                    msgs[0]["content"] = msgs[0]["content"] + "\n\n" + tl_text
            for k in range(args.runs):
                if args.dry_run:
                    text, err, sec = "", "", 0.0
                else:
                    t0 = time.time()
                    try:
                        resp = client.chat.completions.create(
                            model=model, messages=msgs, temperature=args.temperature,
                            max_tokens=args.max_tokens, extra_body=extra_body,
                        )
                        text = (resp.choices[0].message.content or "").strip()
                        err = "" if text else "EMPTY_CONTENT"
                    except Exception as exc:  # noqa: BLE001
                        text, err = "", f"{type(exc).__name__}: {exc}"
                    sec = round(time.time() - t0, 1)
                cleaned, cinfo = RC.clean_reply(text)
                rec = {
                    "char": char, "scenario": sc["id"], "cat": sc["cat"], "arm": args.arm_name,
                    "scene": sc.get("scene", ""), "source": sc.get("source", ""), "risk": sc.get("risk", False),
                    "k": k, "reply": cleaned, "reply_raw": text, "clean": cinfo,
                    "error": err, "sec": sec,
                    "prompt_chars": len(msgs[0]["content"]),
                    "turn_logic_chars": len(tl_text),
                }
                records.append(rec)
                if cleaned and not err:
                    per_char_replies[char].append(cleaned)
                if not args.dry_run:
                    print(f"[probe]   {sc['id']} #{k}: {text[:64]!r}{(' ERR ' + err) if err else ''}", flush=True)

    # 落盘逐条
    with out_jsonl.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    # 聚合评分
    summary = {char: score_arm(char, replies, gold[char]) for char, replies in per_char_replies.items()}
    (REPORT / f"probe_{args.label}_summary.json").write_text(
        json.dumps({"label": args.label, "arm": args.arm_name, "runs": args.runs,
                    "patch": args.patch, "thinking": args.thinking, "max_tokens": args.max_tokens,
                    "summary": summary},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    lines = [f"# 探针结果 · {args.label}（臂 = {args.arm_name}）\n"]
    errs = sum(1 for r in records if r["error"])
    lines.append(f"- 夹具：每角色真实 messages dump，仅替换末条 user；生产同参 temperature={args.temperature} max_tokens={args.max_tokens}")
    lines.append(f"- 生成：{len(records)} 条（error {errs}）｜ 每场景 {args.runs} 次\n")
    lines.append(f"| 角色 | 气泡 | composite | fidelity | 锚点(出/参) | 硬规则V | 硬规则任一 | 具体锚点率 | 泄漏率 | 最漂维度 |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    leak_by_char: dict[str, list[int]] = defaultdict(list)
    for r in records:
        if r["reply"] or r["error"] == "EMPTY_CONTENT":
            leak_by_char[r["char"]].append(1 if r["clean"]["leak"] else 0)
    for char, s in summary.items():
        if not s.get("n_bubbles"):
            lines.append(f"| {char} | 0 | — | — | — | — | — | — | — | — |")
            continue
        worst = "、".join(d["dim"] for d in s.get("worst_dims", [])[:3])
        lk = leak_by_char.get(char, [])
        lk_rate = sum(lk) / len(lk) * 100 if lk else 0.0
        lines.append(
            f"| {char} | {s['n_bubbles']} | **{s['composite']}** | {s['fidelity']} | "
            f"{s['anchor_density']}/{s['anchor_ref']} | {s['hard_v_rate'] * 100:.1f}% | "
            f"{s['hard_any_rate'] * 100:.1f}% | {s['concrete_anchor_rate'] * 100:.0f}% | "
            f"{lk_rate:.0f}% | {worst} |"
        )
    if summary:
        comps = [s["composite"] for s in summary.values() if "composite" in s]
        fids = [s["fidelity"] for s in summary.values() if "fidelity" in s]
        vs = [s["hard_v_rate"] for s in summary.values() if "hard_v_rate" in s]
        concs = [s["concrete_anchor_rate"] for s in summary.values() if "concrete_anchor_rate" in s]
        if comps:
            lines.append(
                f"\n**总体**：composite 均值 {sum(comps) / len(comps):.1f}（头号指标，风格 0.65 + 锚点 0.35）｜"
                f"fidelity 均值 {sum(fids) / len(fids):.1f}｜"
                f"硬规则 V 级均值 {sum(vs) / len(vs) * 100:.1f}%｜"
                f"具体锚点率均值 {sum(concs) / len(concs) * 100:.0f}%"
            )
        allk = [x for v in leak_by_char.values() for x in v]
        if allk:
            lines.append(f"泄漏率（think标签/心想/说话人回显/中文动作旁白）均值 {sum(allk) / len(allk) * 100:.0f}%")
    # 场景级明细（按类别看长度）
    lines.append("\n## 场景级明细（中位字长 / 句数）\n")
    lines.append("| 角色 | 场景 | 类别 | 中位字长 | 均句数 | 样本 |")
    lines.append("|---|---|---|---|---|---|")
    by_sc: dict[tuple[str, str], list[str]] = defaultdict(list)
    for r in records:
        if r["reply"] and not r["error"]:
            by_sc[(r["char"], r["scenario"])].append(r["reply"])
    # 场景元数据：v1 来自 probe_scenarios，v2 来自注册表；两者都要能查到
    sc_meta: dict[str, dict] = {s["id"]: s for scs in SCENARIOS.values() for s in scs}
    for r in records:
        sc_meta.setdefault(r["scenario"], {"cat": r.get("cat") or r.get("scene") or "", "watch": []})
    for (char, sid), replies in by_sc.items():
        fs = [S.turn_features(t, "cn") for t in replies]
        fs = [f for f in fs if not f.silent]
        if not fs:
            continue
        med = sorted(f.length for f in fs)[len(fs) // 2]
        sent = sum(f.n_sent for f in fs) / len(fs)
        lines.append(f"| {char} | {sid} | {sc_meta[sid].get('cat', '')} | {med} | {sent:.2f} | {len(fs)} |")

    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\n[probe] -> {out_jsonl.name}, {out_md.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
