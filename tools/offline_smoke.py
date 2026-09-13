"""offline smoke：一条命令回答「这个仓库现在是健康的吗」。

本仓库没有运行时状态，smoke 聚焦三件仍然有价值的事：

  1. **装配完整性** —— 四层都在、顺序对、字数在预算内、每个角色每个场景都能装配；
  2. **内容红线** —— 不许出现元叙述（语料/实测/中位/频次）、`<think>`、占位符、
     截断标记、prompt 回声；这是「蒸馏出来的特征」最容易带进 prompt 的脏东西；
  3. **配套设施自检** —— 夹具、派生统计的形状、机械门禁与单测是否全绿。

**不调 LLM**（`--with-llm` 才调一次/角色），所以它是零成本、可进 CI 的那一层。
另外它自带**零写校验**：跑完比对仓库文件指纹，除了 `report/` 自己的产物之外，
任何被改动的文件都会 FAIL——prompt 装配是只读的，这条不变量值得机械守住。

用法：

    py -X utf8 tools/offline_smoke.py                # 全套（含单测与门禁）
    py -X utf8 tools/offline_smoke.py --fast         # 跳过单测与门禁（~1 秒）
    py -X utf8 tools/offline_smoke.py --with-llm     # 额外每个角色真调一次模型
    py -X utf8 tools/offline_smoke.py --mock-now 2026-09-12T03:00:00+09:00

产物：`report/offline_smoke.md`（含每条检查的明细与耗时）。
退出码：0 = 全绿（SKIP 不算失败），1 = 有 FAIL。
"""
from __future__ import annotations

# ── idiolect 路径引导：仓库根 + 各 tools 子目录上 sys.path ──
import sys as _sys
from pathlib import Path as _Path
_ROOT = _Path(__file__).resolve().parents[1]
for _p in (_ROOT, _ROOT / "tools",
           *(_ROOT / "tools" / _d for _d in ("corpus", "distill", "probe", "score", "gates"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))
from _paths import CORPUS_DIR, DATA, REPORT, ROOT  # noqa: E402,F401

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(ROOT))

import mock_clock as MOCK  # noqa: E402

CHARS = ["爱音", "灯", "立希", "素世", "乐奈"]
CHARKEY = {"爱音": "anon", "灯": "tomori", "立希": "taki", "素世": "soyo", "乐奈": "rana"}
LAYERS = ("canon", "voice", "style_target", "turn_logic")

# 层预算（字符数）。超了不是错，是「该重新蒸馏了」的信号 —— 所以给 FAIL 而不是警告：
# prompt 预算是硬约束，超预算是要动 prompt 的人必须看见的事。
BUDGET = {"canon": 18000, "voice": 7500, "style_target": 800, "turn_logic": 1200, "total": 26000}

# 内容红线：出现在**角色可见文本**里就是泄漏（实测踩过的坑）。
# 词表与 `voice_meta_gate.META_HARD` 保持一致——门禁和冒烟不该有两套标准。
FORBIDDEN = {
    "元叙述": ("语料", "实测", "专指", "金标准", "lift", "蒸馏", "统计", "占比",
               "出现次数", "基线", "中位", "persona card", "manifest", "cn train", "子模块"),
    "推理标签": ("<think>", "</think>", "thinking>"),
    "prompt 回声": ("<part ", "</part>", "<scene", "<system>"),
    "占位符": ("TODO", "FIXME", "待补", "XXX", "____"),
    "截断标记": ("已截断", "[[__MEMCTX_TAIL_SLOT__]]", "……（略"),
}

GATES = ["voice_meta_gate.py", "_gen_scene_check.py", "_tl_deep_check.py", "audit_role_packages.py",
         "oob_check.py", "evidence_check.py"]


class Result:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def add(self, name: str, ok: bool | None, detail: str = "", sec: float = 0.0) -> None:
        status = "SKIP" if ok is None else ("PASS" if ok else "FAIL")
        self.rows.append({"name": name, "status": status, "detail": detail, "sec": round(sec, 2)})
        icon = {"PASS": "PASS", "FAIL": "FAIL", "SKIP": "SKIP"}[status]
        print(f"[{icon}] {name:<28} {detail}", flush=True)

    @property
    def failed(self) -> list[dict]:
        return [r for r in self.rows if r["status"] == "FAIL"]


def fingerprint(root: Path) -> dict[str, str]:
    """仓库文件指纹（排除 report/、缓存、.git），用于零写校验。"""
    out: dict[str, str] = {}
    skip = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", "report", ".venv", "raw"}
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        if any(part in skip for part in rel.parts):
            continue
        if p.suffix in {".pyc", ".pyo"}:
            continue
        try:
            out[str(rel)] = hashlib.md5(p.read_bytes()).hexdigest()
        except OSError:
            continue
    return out


def check_assembly(res: Result) -> dict[str, dict]:
    """四层是否都在、顺序对不对、预算超没超。"""
    from idiolect.assemble import LAYER_ORDER, build_system_prompt, layer_sizes

    t0 = time.time()
    res.add("装配.层顺序", LAYER_ORDER == LAYERS, f"LAYER_ORDER={LAYER_ORDER}")

    sizes: dict[str, dict] = {}
    over: list[str] = []
    order_bad: list[str] = []
    for char in CHARS:
        msg = "明天几点上课"
        system = build_system_prompt(char, msg, session_id=f"smoke:{char}", now=MOCK.mock_now())
        sizes[char] = layer_sizes(char, msg, session_id=f"smoke:{char}", now=MOCK.mock_now())
        pos = [system.find(x) for x in ("一句话定位", "[语气清单]")]
        if not all(p >= 0 for p in pos[:1]) or (pos[1] >= 0 and pos[1] < pos[0]):
            order_bad.append(char)
        for key, limit in BUDGET.items():
            if key == "total":
                if len(system) > limit:
                    over.append(f"{char}.total={len(system)}")
            elif sizes[char].get(key, 0) > limit:
                over.append(f"{char}.{key}={sizes[char][key]}")
    res.add("装配.四层齐全", all(sizes[c]["canon"] and sizes[c]["voice"] for c in CHARS),
            " ".join(f"{c}:c{sizes[c]['canon']}/v{sizes[c]['voice']}/t{sizes[c]['style_target']}"
                     f"/l{sizes[c]['turn_logic']}" for c in CHARS), time.time() - t0)
    res.add("装配.层顺序(canon 在前)", not order_bad, f"异常={order_bad or '无'}")
    res.add("装配.层预算", not over, f"超预算={over or '无'}（上限 {BUDGET}）")
    return sizes


def check_scenes(res: Result) -> None:
    """13 通用场景 × 5 角色都要能装配出长度目标；turn_logic 触发矩阵要正确。"""
    from dump_turn_logic_gate import CASES, MARKER_TITLE, leak_check
    import re

    t0 = time.time()
    import idiolect.registry as RP
    import idiolect.scene_engine as engine
    from idiolect.scene_classifier import classify
    from idiolect.style_target import build_style_target_block

    scenes = sorted({s for s in (classify(t, c) for c in CHARS for t, _w, _o in CASES.get(c, [])) if s})
    missing = []
    for char in CHARS:
        for scene in scenes:
            if not build_style_target_block(char, scene):
                missing.append(f"{char}/{scene}")
    cells = sum(1 for c in CHARS for _ in scenes if build_style_target_block(c, _))
    res.add("场景.长度目标覆盖", not missing,
            f"探到 {len(scenes)} 场景 × 5 角色 → {cells} 格；缺 {missing or '无'}", time.time() - t0)

    bad_fire, bad_owner = [], []
    for char, cases in CASES.items():
        for text, want_fire, owner in cases:
            engine.reset_session()
            block = RP.render_turn_special_block(
                char, text, session_id=f"smoke:{char}:{text[:8]}",
                is_developer=False, mode="chat", now_jst=MOCK.mock_now()) or ""
            if bool(block) != want_fire:
                bad_fire.append(f"{char}/{text[:14]}")
            elif owner in MARKER_TITLE and not re.search(MARKER_TITLE[owner], block):
                bad_owner.append(f"{char}/{owner}")
    res.add("turn_logic.触发矩阵", not bad_fire, f"{sum(len(v) for v in CASES.values())} 例；"
                                                 f"异常={bad_fire or '无'}")
    res.add("turn_logic.归属标记", not bad_owner, f"异常={bad_owner or '无'}")

    leak = leak_check()
    res.add("turn_logic.角色串味", not (leak["soyo_in_rana"] or leak["rana_in_soyo"]), str(leak))


def check_forbidden(res: Result, sizes: dict[str, dict]) -> None:
    """五角色 × 多场景装配出的 system 里不许有元叙述/标签/占位符。"""
    from idiolect.assemble import build_system_prompt

    msgs = ["在干嘛", "明天几点上课", "我一直在哭，快撑不住了", "今天天气不错，午饭吃什么",
            "你是不是有喜欢的人了", "爱音今天来练习了吗", "你刚才那句是什么意思，我没听懂"]
    hits: list[str] = []
    for char in CHARS:
        for msg in msgs:
            system = build_system_prompt(char, msg, session_id=f"smoke:{char}", now=MOCK.mock_now())
            for kind, words in FORBIDDEN.items():
                for w in words:
                    if w in system:
                        hits.append(f"{char}/{kind}:{w}")
    res.add("内容.红线扫描", not hits, f"{len(CHARS) * len(msgs)} 份 system；命中={sorted(set(hits)) or '无'}")


def check_fixtures(res: Result) -> None:
    bad: list[str] = []
    note: list[str] = []
    for char in CHARS:
        p = ROOT / "fixtures" / f"messages_{char}.json"
        if not p.exists():
            bad.append(f"{char}:缺文件")
            continue
        try:
            rows = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            bad.append(f"{char}:{type(exc).__name__}")
            continue
        if not rows or rows[0].get("role") != "system":
            bad.append(f"{char}:首条不是 system")
        if not any(r.get("role") == "user" for r in rows):
            bad.append(f"{char}:没有 user 轮")
        note.append(f"{char}:{len(rows)}条/system{len(rows[0].get('content', '')) if rows else 0}字")
    res.add("夹具.结构", not bad, f"{' '.join(note)}｜异常={bad or '无'}")
    if note and all("system0字" in n for n in note):
        res.add("夹具.占位提示", None, "5 份都是占位夹具（system 为空）→ 探针请加 --assemble")
    elif any("system0字" in n for n in note):
        res.add("夹具.占位提示", None, "部分夹具 system 为空 → 探针请加 --assemble")


def check_data(res: Result) -> None:
    """派生统计的形状：发布出去的 data/ 必须自洽。"""
    want = ["style_targets.json", "scene_char_baseline.json", "scene_stats.json",
            "tic_profile.json", "tic_by_scene.json"]
    missing = [n for n in want if not (DATA / n).exists()]
    if missing:
        res.add("数据.派生统计", False, f"缺 {missing}")
        return
    targets = json.loads((DATA / "style_targets.json").read_text(encoding="utf-8"))
    base = json.loads((DATA / "scene_char_baseline.json").read_text(encoding="utf-8"))
    stats = json.loads((DATA / "scene_stats.json").read_text(encoding="utf-8"))
    tics = json.loads((DATA / "tic_profile.json").read_text(encoding="utf-8"))

    # style_targets.json = {"cn": {char: {"name","n","median_chars","p90_chars",...,"<scene>": {...}}}}
    # 注意：本仓库发布的这份**只有全局字段**，没有嵌套的场景格（场景目标在
    # idiolect/scene_length_targets.py 里）。这里只数字段，不声称「场景格」。
    layer_cn = targets.get("cn", {}) if isinstance(targets, dict) else {}
    fields = sorted({k for v in layer_cn.values() if isinstance(v, dict) for k in v})
    chars_cov = [c for c in CHARKEY.values() if c in layer_cn]
    res.add("数据.长度目标覆盖", len(chars_cov) == 5 and len(fields) >= 10,
            f"cn: {len(chars_cov)} 角色 / 每角色 {len(fields)} 个全局字段"
            f"（场景级目标在 idiolect/scene_length_targets.py，由 场景.长度目标覆盖 检查）")

    # 场景级目标来自包内数据模块，单独查
    try:
        from idiolect.scene_length_targets import SCENE_LENGTH_TARGETS

        cells = sum(len(v) for v in SCENE_LENGTH_TARGETS.values())
        res.add("数据.场景目标(包内)", cells >= 100,
                f"{len(SCENE_LENGTH_TARGETS)} 角色 / {cells} 个 (角色 × 场景) 目标")
    except Exception as exc:  # noqa: BLE001
        res.add("数据.场景目标(包内)", False, f"导入失败：{type(exc).__name__}: {exc}")

    # scene_char_baseline.json = {"<char_cn>|<scene>": {"n","length","n_sent",...}}（例句已剥离）
    empty = [k for k, v in base.items() if not isinstance(v, dict) or not v.get("length")]
    res.add("数据.场景基线", not empty,
            f"{len(base)} 键（{len({k.split('|')[0] for k in base})} 角色 × "
            f"{len({k.split('|')[1] for k in base if '|' in k})} 场景）｜空={empty or '无'}")
    res.add("数据.场景统计", bool(stats), f"scene_stats={len(stats)} 场景｜tic_profile={len(tics)} 角色")
    leaked = [k for k, v in base.items() if isinstance(v, dict) and "exemplars" in v]
    res.add("数据.无原作文本", not leaked,
            f"带例句的键={leaked[:5] or '无'}（本仓库不分发原作文本，只发派生统计）")


def check_gates(res: Result) -> None:
    for gate in GATES:
        p = ROOT / "tools" / "gates" / gate
        t0 = time.time()
        r = subprocess.run([sys.executable, "-X", "utf8", str(p)], cwd=ROOT,
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        tail = (r.stdout or "").strip().splitlines()
        res.add(f"门禁.{gate}", r.returncode == 0,
                (tail[-1] if tail else (r.stderr or "").strip()[-120:]), time.time() - t0)


def check_tests(res: Result) -> None:
    t0 = time.time()
    r = subprocess.run([sys.executable, "-X", "utf8", "-m", "pytest", "tests", "-q"], cwd=ROOT,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    tail = [ln for ln in (r.stdout or "").strip().splitlines() if ln.strip()]
    res.add("单测.tests/", r.returncode == 0, tail[-1] if tail else "无输出", time.time() - t0)


def check_llm(res: Result) -> None:
    """每个角色真调一次（mock 时间）——只在 --with-llm 下跑。"""
    try:
        from openai import OpenAI
    except Exception as exc:  # noqa: BLE001
        res.add("LLM.可用性", None, f"openai SDK 不可用：{exc}")
        return
    import llm_nothink_patch  # noqa: E402,F401
    from idiolect.assemble import build_messages

    key = os.environ.get("LLM_API_KEY", "").strip()
    if not key:
        res.add("LLM.可用性", None, "未设置 LLM_API_KEY（见 docs/ 的密钥说明）")
        return
    client = OpenAI(api_key=key, base_url=os.environ.get("LLM_BASE_URL") or None)
    model = os.environ.get("LLM_MODEL", "deepseek-flash")
    msgs = "在干嘛"
    bad, note = [], []
    for char in CHARS:
        t0 = time.time()
        messages = build_messages(char, msgs, session_id=f"smoke:{char}", now=MOCK.mock_now())
        try:
            resp = client.chat.completions.create(
                model=model, messages=messages, temperature=0.75, max_tokens=420,
                extra_body={"thinking": {"type": "disabled"}})
            text = (resp.choices[0].message.content or "").strip()
        except Exception as exc:  # noqa: BLE001
            bad.append(f"{char}:{type(exc).__name__}")
            continue
        if not text:
            bad.append(f"{char}:空回复")
        if "<think>" in text:
            bad.append(f"{char}:think 泄漏")
        note.append(f"{char}:{len(text)}字/{round(time.time() - t0, 1)}s")
        res.add(f"LLM.{char}", not bad or not bad[-1].startswith(char), f"{len(text)}字 {text[:36]!r}",
                time.time() - t0)
    if bad:
        res.add("LLM.异常汇总", False, str(bad))


# ── 文档.README 字数表 ──────────────────────────────────────────────────
# 三语 README 里有两张实测表：四层表（乐奈找猫场景）与 comfort 格表。
# 改了 prompt 层就必须重生成表格——2026-09-13 踩过：voice 末尾共享块改写后
# 表格没更新，voice 列全员差 -32 没人发现。这里用同一条装配路径（layer_sizes）
# 现场复算、逐格对账：对不上就是文档在说谎。
README_COMFORT_MSG = "我一直在哭，快撑不住了"   # README 表注明的 comfort 格输入
README_CAT_MSG = "你今天又想去哪找猫"           # 四层表注明的找猫输入

# comfort 表的角色名拼写（三语各异）→ CHARKEY 的罗马字 key
README_CHAR_NAMES = {
    "README.md": {"爱音": "anon", "灯": "tomori", "立希": "taki", "素世": "soyo", "乐奈": "rana"},
    "README.en.md": {"Anon": "anon", "Tomori": "tomori", "Taki": "taki", "Soyo": "soyo", "Rana": "rana"},
    "README.ja.md": {"愛音": "anon", "燈": "tomori", "立希": "taki", "そよ": "soyo", "楽奈": "rana"},
}


def check_readme_tables(res: Result) -> None:
    """三语 README 的字数表与 `layer_sizes` 现场实测逐格对账。

    口径必须与 README 注明的一致：comfort 格 = 输入「我一直在哭，快撑不住了」；
    四层表 = 乐奈 × 找猫。合计列 = 四层之和（表自身口径）。
    """
    from idiolect.assemble import layer_sizes

    t0 = time.time()
    # 表格是在**默认** mock 时刻下量出来的；--mock-now 是单次调试覆盖，
    # 不该让文档校验跟着漂，所以这里显式摘掉环境变量再量。
    saved_now = os.environ.pop(MOCK.ENV_VAR, None)
    try:
        # session 后缀带时间戳：turn_logic 去重表按 session 记账，
        # 同进程里重复调用也要每次拿到完整块。
        stamp = time.time_ns()
        comfort = {CHARKEY[c]: layer_sizes(c, README_COMFORT_MSG,
                                           session_id=f"smoke:readme:{CHARKEY[c]}:{stamp}",
                                           now=MOCK.mock_now())
                   for c in CHARS}
        cat = layer_sizes("乐奈", README_CAT_MSG,
                          session_id=f"smoke:readme:rana-cat:{stamp}", now=MOCK.mock_now())
    finally:
        if saved_now is not None:
            os.environ[MOCK.ENV_VAR] = saved_now

    bad: list[str] = []
    n_cells = 0
    for fname, names in README_CHAR_NAMES.items():
        text = (ROOT / fname).read_text(encoding="utf-8")
        lines = text.splitlines()
        # 四层表：行首是 `层名`（全文件唯一），行内最后一个数字是该层字数
        for layer in LAYERS:
            row = next((l for l in lines if l.startswith(f"| `{layer}`")), None)
            n_cells += 1
            if row is None:
                bad.append(f"{fname} 四层表缺 {layer} 行")
                continue
            nums = [int(x) for x in re.findall(r"\d+", row)]
            if not nums or nums[-1] != cat[layer]:
                bad.append(f"{fname} 四层表 {layer}={nums[-1] if nums else '—'} 实测={cat[layer]}")
        # comfort 格表：整行形如「| 名 | 四层各一格 | 合计 |」的纯整数
        for cn, key in names.items():
            pat = re.compile(rf"^\|\s*{re.escape(cn)}\s*\|(?:\s*\d+\s*\|){{5}}\s*$", re.M)
            m = pat.search(text)
            n_cells += 1
            if m is None:
                bad.append(f"{fname} comfort 表缺 {cn} 行")
                continue
            nums = [int(x) for x in re.findall(r"\d+", m.group(0))]
            want = [comfort[key][k] for k in LAYERS]
            if nums[:4] != want:
                bad.append(f"{fname} comfort 表 {cn}={nums[:4]} 实测={want}")
            elif nums[4] != sum(want):
                bad.append(f"{fname} comfort 表 {cn} 合计 {nums[4]} ≠ 四层和 {sum(want)}")
    res.add("文档.README 字数表", not bad,
            f"{n_cells} 格对账（三语 × 两表）；不一致={bad or '无'}", time.time() - t0)


def check_cli_safety(res: Result) -> None:
    """会写到**外部数据目录**的脚本必须带 argparse，否则 `--help` 也会真的动手。

    2026-09-13 的事故：对全仓库脚本跑 `--help` 做冒烟，`build_gold.py` 没有 argparse，
    于是 `--help` 被忽略、合并照跑；它的源文件按脚本自身目录解析（新仓库里不存在），
    结果把 `IDIOLECT_CORPUS_DIR` 指向的外部语料目录覆盖成 0 字节，退出码还是 0。
    现在三道：读侧 `require_corpus()`、写侧零结果守卫、这里补静态检查。

    判据（两条，宁窄不误报）：
      1. 把输出根目录直接赋成 `CORPUS_DIR` / `DATA` 的脚本 —— 这就是覆盖外部数据的那类；
      2. `tools/corpus/` 下所有带 `main()` 的脚本 —— 这个目录整体会碰语料。
    """
    import re

    assign_root = re.compile(r"(?m)^\s*(?:OUT|DST|DEST|out_dir|dst)\s*=\s*(?:CORPUS_DIR|DATA)\b")
    risky: list[str] = []
    for p in sorted((ROOT / "tools").rglob("*.py")):
        src = p.read_text(encoding="utf-8")
        has_args = "argparse" in src
        rel = str(p.relative_to(ROOT))
        if has_args:
            continue
        if assign_root.search(src):
            risky.append(f"{rel}（把输出根赋成 CORPUS_DIR/DATA）")
        elif rel.startswith("tools\\corpus\\") and "def main(" in src:
            risky.append(f"{rel}（tools/corpus 下带 main 却没有 argparse）")
    total = len(list((ROOT / "tools").rglob("*.py")))
    res.add("工具.CLI 安全", not risky, f"{total} 个脚本；风险项={risky or '无'}")


def main() -> int:
    ap = argparse.ArgumentParser(description="offline smoke：零写、零 LLM 的仓库健康检查")
    ap.add_argument("--fast", action="store_true", help="跳过门禁与单测")
    ap.add_argument("--with-llm", action="store_true", help="额外每角色真调一次模型")
    ap.add_argument("--mock-now", default="", help="覆盖 mock 时刻（ISO 8601）")
    args = ap.parse_args()

    if args.mock_now:
        os.environ[MOCK.ENV_VAR] = args.mock_now
    REPORT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    print(f"[smoke] 仓库 {ROOT}")
    print(f"[smoke] 时钟 = {MOCK.describe()}")
    print(f"[smoke] 语料目录 {CORPUS_DIR}（{'存在' if CORPUS_DIR.exists() else '不存在——涉及语料的检查会 SKIP'}）")
    print("-" * 96)

    before = fingerprint(ROOT)
    res = Result()
    sizes = check_assembly(res)
    check_scenes(res)
    check_forbidden(res, sizes)
    check_fixtures(res)
    check_data(res)
    check_cli_safety(res)
    check_readme_tables(res)
    if not args.fast:
        check_gates(res)
        check_tests(res)
    if args.with_llm:
        check_llm(res)
    after = fingerprint(ROOT)
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    res.add("零写校验", not changed, f"仓库文件变更={changed or '无'}（只允许写 report/）")

    print("-" * 96)
    n_fail = len(res.failed)
    md = [f"# offline smoke · {ROOT.name}", "",
          f"- 时钟：{MOCK.describe()}",
          f"- 耗时：{round(time.time() - t0, 1)}s｜检查 {len(res.rows)} 项｜FAIL {n_fail}",
          f"- 结论：{'PASS' if not n_fail else 'FAIL'}", "",
          "| 检查 | 结果 | 明细 |", "|---|---|---|"]
    md += [f"| {r['name']} | {r['status']} | {r['detail'].replace('|', '/')} |" for r in res.rows]
    (REPORT / "offline_smoke.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"[smoke] {'PASS' if not n_fail else f'FAIL x{n_fail}'}｜{round(time.time() - t0, 1)}s"
          f"｜-> report/offline_smoke.md")
    return 1 if n_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
