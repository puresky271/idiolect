"""评测链路修复的契约测试（2026-09-13，外部方法论评审驱动）。

背景：外部评审用仓库自己的评分函数证明——两个上报指标（fidelity / 场景贴合分）
**分不出「像」与「不像」**：一段完全出戏的通用助手腔 fidelity 84.9、distill 0.606，
高于真像角色的样本（82.0 / 0.286）。根因是目标函数只有长度维度，唯一带内容信号的
`composite_score`（风格 0.65 + 锚点 0.35）写好了却零调用；holdout 切了没人读；
且所有验收压在一个复合分上。

本文件钉的契约（每条对应评审报告的一项指控）：
  1. **判别力**：probe_runner.score_arm 必须带 composite 分，且对构造样本的排序
     能把助手腔排在真像样本之下（D > A > B）。这是「指标必须能分出助手腔」的
     回归测试——将来谁改评分公式把它改回去，这里立刻红。
  2. **anchor_ref 单一来源**：唯一定死场景基线派生值；画像不导出 anchor_density
     （曾有过两个真相来源、同一份产物差 3.2 分的教训，2026-09-13 复审 N3）。
  3. **holdout 消费**：scene_char_baseline 的语料加载可按 split 过滤，
     holdout 为零时是显式报错而不是写出空基线。
  4. **多指标门禁**：accept_check 对 before/after 两臂逐指标独立判定，任一退化即整体 FAIL；
     锚点密度走合并泊松精确检验（小计数不许用固定百分比门槛，N6/N7 两轮教训），
     噪声级波动不误报、可检测下限照打；缺产物是明确报错，不是静默通过。
  5. **A/B 盲评**：ab_blind 的 worksheet 确定性、不泄漏臂名、key 映射自洽、
     tally 数学正确。

模式与 test_score_golden.py 相同：子进程 + 预置 env（REPORT/DATA/CORPUS 全指
合成目录），全程离线——不调 LLM、不读真实语料（仅 W1 判别力测试读随仓库发布
的派生统计 data/，与 test_shipped_baseline_schema 同一性质）。
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import mock_clock as MOCK  # noqa: E402


def _load(name: str, path: Path):
    """按文件路径加载工具模块（与现有契约测试同一做法）。"""
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def _tool_env(report_dir: Path, data_dir: Path | None = None,
              corpus_dir: Path | None = None) -> dict:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8",
           "IDIOLECT_REPORT_DIR": str(report_dir),
           "IDIOLECT_CORPUS_DIR": str(corpus_dir or (report_dir / "__no_corpus_here__"))}
    if data_dir is not None:
        env["IDIOLECT_DATA_DIR"] = str(data_dir)
    env.pop(MOCK.ENV_VAR, None)
    return env


def _run_tool(args: list[str], env: dict) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-X", "utf8", *args],
                          cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env, timeout=300)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                    encoding="utf-8")


# ── 评审报告的构造样本（第三节）：A/D 像乐奈，B 是纯助手腔 ──
# 数字锚点：fidelity 把 B(84.9) 排在 A(82.0) 之上；接线 composite 后必须翻正。
CAND_A_IN_CHARACTER = ["嗯。", "……那边。", "猫。屋檐下面。", "嗯。", "不去。", "……有点吵。"]
CAND_B_ASSISTANT = ["我不太清楚。", "请你说得更具体一些。", "可以再描述一下吗？",
                    "我理解你的意思。", "这个问题有点难。", "我需要更多信息。"]
CAND_D_IN_CHARACTER_VERBOSE = ["嗯……你别哭。", "猫在这里。", "我陪你坐着。",
                               "……不想说话也行。", "屋上有猫。", "灯，别哭。喏，猫。"]


class ScoreArmCompositeTests(unittest.TestCase):
    """W1 契约：score_arm 输出 composite，且排序能分出助手腔。"""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load("probe_runner", ROOT / "tools" / "probe" / "probe_runner.py")
        cls.sf = _load("style_features", ROOT / "tools" / "distill" / "style_features.py")

    def _gold_rana(self) -> dict:
        """随仓库发布的乐奈画像（anchor_ref 由 score_arm 内部统一派生，画像不参与）。"""
        raw = json.loads((ROOT / "data" / "style_profiles.json").read_text(encoding="utf-8"))
        return dict(raw["rana"])

    def test_score_arm_has_composite_fields(self):
        gold = self._gold_rana()
        out = self.mod.score_arm("乐奈", CAND_A_IN_CHARACTER, gold)
        for field in ("composite", "anchor_density", "anchor_ref", "anchor_score", "fidelity"):
            with self.subTest(field=field):
                self.assertIn(field, out)
        self.assertGreater(out["anchor_ref"], 1.0,
                           "乐奈的 anchor_ref 不该退回 1.0 兜底（场景基线派生必须生效）")

    def test_anchor_ref_single_source(self):
        """N3 契约：anchor_ref 只有一个真相来源（场景基线派生值）。
        画像里塞什么字段都不能改变它——两个来源曾让同一份产物差 3.2 分。"""
        gold = self._gold_rana()
        want = self.mod.derive_anchor_ref("乐奈")
        plain = self.mod.score_arm("乐奈", CAND_A_IN_CHARACTER, gold)
        polluted = self.mod.score_arm("乐奈", CAND_A_IN_CHARACTER,
                                      {**gold, "anchor_density": 999.0})
        self.assertAlmostEqual(plain["anchor_ref"], round(want, 2), places=3,
                               msg="score_arm 输出的 anchor_ref（两位小数）必须等于派生值")
        self.assertEqual(plain["composite"], polluted["composite"],
                         "画像字段不得影响 composite——anchor_ref 只能来自场景基线派生")

    def test_composite_ranks_assistant_tone_below_in_character(self):
        """评审核心论断的反向契约：纯助手腔 B 的 composite 必须低于真像样本 A/D。"""
        gold = self._gold_rana()
        comp = {name: self.mod.score_arm("乐奈", reps, gold)["composite"]
                for name, reps in (("A", CAND_A_IN_CHARACTER), ("B", CAND_B_ASSISTANT),
                                   ("D", CAND_D_IN_CHARACTER_VERBOSE))}
        self.assertLess(comp["B"], comp["A"],
                        f"助手腔 composite({comp['B']}) 必须低于合格短句 A({comp['A']})")
        self.assertLess(comp["B"], comp["D"],
                        f"助手腔 composite({comp['B']}) 必须低于真在安慰的 D({comp['D']})")

    def test_fidelity_alone_would_fail_this_ordering(self):
        """钉住评审的原始发现：fidelity 口径下助手腔不输真像样本——
        这条测试若变红，说明 fidelity 公式变了，复合分权重需要重新评审。"""
        gold = self._gold_rana()
        fid = {name: self.mod.score_arm("乐奈", reps, gold)["fidelity"]
               for name, reps in (("A", CAND_A_IN_CHARACTER), ("B", CAND_B_ASSISTANT))}
        self.assertGreaterEqual(fid["B"], fid["A"] - 3.0,
                                "fidelity 已不再奖励助手腔——请回头评审 composite 权重")

    def test_derive_anchor_ref_matches_weighted_mean(self):
        """派生口径：该角色各场景格按 n 加权的 anchor_density 均值。"""
        base = json.loads((ROOT / "data" / "scene_char_baseline.json").read_text(encoding="utf-8"))
        cells = [c for k, c in base.items() if k.startswith("乐奈|")]
        want = sum(c["n"] * c["anchor_density"] for c in cells) / sum(c["n"] for c in cells)
        got = self.mod.derive_anchor_ref("乐奈")
        self.assertAlmostEqual(got, want, places=3)

    def test_anchor_ref_required_no_silent_fallback(self):
        """N4 契约：库 API 缺 anchor_ref 必须报错，不许静默兜底——
        默认路径曾让纯助手腔 composite 排第一（90.2），且无任何告警。
        gold 里塞字段也不许被采信（双来源教训）。"""
        sf = self.sf
        texts = ["猫。抹茶。", "嗯。"]
        gold = sf.profile_from_texts(texts, "cn")
        with self.assertRaises(ValueError):
            sf.composite_score(gold, gold, texts)
        gold_with_field = {**gold, "anchor_density": 999.0}
        with self.assertRaises(ValueError):
            sf.composite_score(gold_with_field, gold_with_field, texts)
        comp = sf.composite_score(gold, gold, texts, anchor_ref=5.0)
        self.assertEqual(comp["anchor_ref"], 5.0)


class ExportProfilesAnchorTests(unittest.TestCase):
    """N3 契约（2026-09-13 复审）：画像**不导出** anchor_density 字段。

    这个字段曾短暂存在又移除：它与场景基线派生值构成 anchor_ref 的两个真相
    来源（乐奈差 28%，同一份产物 composite 差 3.2 分）。钉住「不导出」，
    防止字段回潮重新造成双口径。
    """

    @classmethod
    def setUpClass(cls):
        cls.mod = _load("export_profiles", ROOT / "tools" / "distill" / "export_profiles.py")

    def test_build_excludes_anchor_density(self):
        fake = {k: ["猫。抹茶。", "嗯……", "去学校。", "RiNG 见。"] for k in
                ("anon", "tomori", "taki", "soyo", "rana")}
        old = self.mod.load_train
        self.mod.load_train = lambda lang="cn": fake
        try:
            out = self.mod.build("cn")
        finally:
            self.mod.load_train = old
        for key in fake:
            with self.subTest(char=key):
                self.assertNotIn("anchor_density", out[key],
                                 "画像不得导出 anchor_density——anchor_ref 唯一来源是场景基线派生")

    def test_shipped_profiles_have_no_anchor_density(self):
        """随仓库发布的画像同样不含该字段（与导出口径一致）。"""
        raw = json.loads((ROOT / "data" / "style_profiles.json").read_text(encoding="utf-8"))
        for key in ("anon", "tomori", "taki", "soyo", "rana"):
            with self.subTest(char=key):
                self.assertNotIn("anchor_density", raw[key])


class HoldoutSplitTests(unittest.TestCase):
    """W2 契约：scene_char_baseline 可按 split 过滤；holdout 为空显式报错。"""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load("scene_char_baseline", ROOT / "tools" / "distill" / "scene_char_baseline.py")

    def _write_corpus(self, tmp: str, rows: list[dict]) -> Path:
        cdir = Path(tmp) / "corpus"
        cdir.mkdir()
        _write_jsonl(cdir / "cn.jsonl", rows)
        return cdir

    def test_load_corpus_split_filter_is_exclusive_and_complete(self):
        rows = [
            {"character": "rana", "text": "猫。屋檐下面。", "split": "train"},
            {"character": "rana", "text": "抹茶芭菲。", "split": "holdout"},
            {"character": "tomori", "text": "……我在。", "split": "train"},
            {"character": "tomori", "text": "不要说了。", "split": "holdout"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            cdir = self._write_corpus(tmp, rows)
            old_corpus, old_require = self.mod.CORPUS_DIR, self.mod.require_corpus
            self.mod.CORPUS_DIR = cdir
            self.mod.require_corpus = lambda *a, **k: None  # 纯过滤逻辑测试，不碰语料前置检查
            try:
                train = self.mod.load_corpus("train")
                holdout = self.mod.load_corpus("holdout")
            finally:
                self.mod.CORPUS_DIR = old_corpus
                self.mod.require_corpus = old_require
        self.assertEqual(train, {"rana": ["猫。屋檐下面。"], "tomori": ["……我在。"]})
        self.assertEqual(holdout, {"rana": ["抹茶芭菲。"], "tomori": ["不要说了。"]})
        overlap = set(train["rana"]) & set(holdout["rana"])
        self.assertFalse(overlap, "train 与 holdout 不得互相泄漏")

    def test_holdout_zero_lines_stops_loudly(self):
        """holdout 行为 0 时必须非零退出 + [stop] 提示，且发生在模型加载之前。"""
        rows = [{"character": "rana", "text": "猫。屋檐下面。", "split": "train"}]
        with tempfile.TemporaryDirectory() as tmp:
            cdir = self._write_corpus(tmp, rows)
            env = _tool_env(Path(tmp) / "report", corpus_dir=cdir)
            r = _run_tool(["tools/distill/scene_char_baseline.py", "--split", "holdout"], env)
            self.assertNotEqual(r.returncode, 0, "holdout 为空必须失败，不许写出空基线")
            self.assertIn("[stop]", r.stdout + r.stderr)


class SceneDistillBaselineTests(unittest.TestCase):
    """W2 契约：scene_distill --baseline 指向哪个文件，参照物就来自哪个文件。"""

    def test_baseline_option_switches_reference(self):
        rows = [
            {"char": "乐奈", "scenario": "gen_comfort_rana", "scene": "comfort", "reply": "嗯，抱抱。"},
            {"char": "乐奈", "scenario": "gen_comfort_rana", "scene": "comfort", "reply": "猫借你。"},
        ]
        base_train = {"乐奈|comfort": {"char": "乐奈", "scene": "comfort", "n": 40,
                                       "length": {"p50": 7.0, "p90": 15.0},
                                       "n_sent": {"mean": 1.4}, "anchor_density": 1.0}}
        base_holdout = {"乐奈|comfort": {"char": "乐奈", "scene": "comfort", "n": 20,
                                         "length": {"p50": 42.0, "p90": 99.0},
                                         "n_sent": {"mean": 3.3}, "anchor_density": 2.0}}
        with tempfile.TemporaryDirectory() as tmp:
            report, data = Path(tmp) / "report", Path(tmp) / "data"
            report.mkdir()
            data.mkdir()
            _write_jsonl(report / "probe_t1.jsonl", rows)
            (data / "scene_char_baseline.json").write_text(
                json.dumps(base_train, ensure_ascii=False), encoding="utf-8")
            (report / "holdout_baseline.json").write_text(
                json.dumps(base_holdout, ensure_ascii=False), encoding="utf-8")
            env = _tool_env(report, data)
            r = _run_tool(["tools/score/scene_distill.py", "--labels", "t1",
                           "--baseline", str(report / "holdout_baseline.json")], env)
            self.assertEqual(r.returncode, 0, r.stderr[-400:])
            scored = json.loads((report / "scene_distill_t1_vs_holdout_baseline.json").read_text(encoding="utf-8"))
            self.assertEqual(scored[0]["base_med"], 42.0,
                             "--baseline 指定的 holdout 基线没有生效")
            self.assertIn("holdout_baseline.json", r.stdout,
                          "报告必须注明基线来源文件（验收可溯）")
            self.assertFalse((report / "scene_distill_t1.json").exists(),
                             "自定义基线的产物不得静默覆盖默认基线的评分结果")


# ── W3 门禁的合成产物：after 臂在 hard_v 上退化 ──
def _summary(composite: float, hard_v: float, hits: int = 40, chars: int = 1000) -> dict:
    """合成 summary。hits/chars 是 accept_check 泊松检验的输入（计数，不是密度）。"""
    return {"label": "x", "arm": "a", "runs": 6, "patch": "none",
            "summary": {"乐奈": {"n_bubbles": 12, "n_replies": 6, "composite": composite,
                                 "fidelity": 80.0, "hard_v_rate": hard_v,
                                 "anchor_density": round(hits / chars * 100, 2),
                                 "anchor_hits": hits, "anchor_chars": chars,
                                 "hard_any_rate": 0.1, "concrete_anchor_rate": 0.5}}}

DISTILL_OK = [{"char": "乐奈", "scene": "comfort", "n": 12, "distill": 0.6,
               "dev_total": 0.2, "char_mean_dev": 0.2, "excess": 0.0}]

PROBE_ROWS = [
    {"char": "乐奈", "scenario": "s1", "scene": "comfort", "reply": "嗯。", "error": ""},
    {"char": "乐奈", "scenario": "s1", "scene": "comfort", "reply": "猫。", "error": ""},
    {"char": "乐奈", "scenario": "s1", "scene": "comfort", "reply": "抹茶。", "error": ""},
]


class AcceptCheckTests(unittest.TestCase):
    """W3 契约：任一指标退化 → 整体 FAIL 且点名；全过 → rc 0；缺文件 → rc 2。"""

    def _setup(self, tmp: str, before_sum: dict, after_sum: dict,
               before_rows: list[dict] | None = None, after_rows: list[dict] | None = None,
               before_distill: list[dict] | None = None,
               after_distill: list[dict] | None = None) -> dict:
        report = Path(tmp) / "report"
        report.mkdir()
        for label, summ, rows, dist in (
                ("b1", before_sum, before_rows or [], before_distill or DISTILL_OK),
                ("a1", after_sum, after_rows or [], after_distill or DISTILL_OK)):
            (report / f"probe_{label}_summary.json").write_text(
                json.dumps(summ, ensure_ascii=False), encoding="utf-8")
            _write_jsonl(report / f"probe_{label}.jsonl", rows)
            (report / f"scene_distill_{label}.json").write_text(
                json.dumps(dist, ensure_ascii=False), encoding="utf-8")
        return _tool_env(report)

    def _run(self, env: dict) -> subprocess.CompletedProcess:
        return _run_tool(["tools/gates/accept_check.py", "--before", "b1", "--after", "a1"], env)

    def test_all_pass_rc0(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = self._setup(tmp, _summary(80.0, 0.0), _summary(81.0, 0.0),
                              PROBE_ROWS, PROBE_ROWS)
            r = self._run(env)
            self.assertEqual(r.returncode, 0, r.stdout[-400:] + r.stderr[-400:])
            self.assertIn("PASS", r.stdout)

    def test_composite_regression_fails_and_names_metric(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = self._setup(tmp, _summary(85.0, 0.0), _summary(80.0, 0.0),
                              PROBE_ROWS, PROBE_ROWS)
            r = self._run(env)
            self.assertEqual(r.returncode, 1, "composite 退化 5 分必须 FAIL")
            self.assertIn("composite", r.stdout)

    def test_hard_v_regression_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = self._setup(tmp, _summary(80.0, 0.0), _summary(80.0, 0.05),
                              PROBE_ROWS, PROBE_ROWS)
            r = self._run(env)
            self.assertEqual(r.returncode, 1, "硬规则 V 级率上升必须 FAIL")

    def test_repeat_regression_fails(self):
        repeated = [dict(row, reply="嗯。") for row in PROBE_ROWS]  # 3 条全同 → 重复度 2/3
        with tempfile.TemporaryDirectory() as tmp:
            env = self._setup(tmp, _summary(80.0, 0.0), _summary(80.0, 0.0),
                              PROBE_ROWS, repeated)
            r = self._run(env)
            self.assertEqual(r.returncode, 1, "同格重复度上升必须 FAIL")
            self.assertIn("重复", r.stdout)

    def test_distill_regression_fails(self):
        worse = [dict(DISTILL_OK[0], distill=0.5)]
        with tempfile.TemporaryDirectory() as tmp:
            env = self._setup(tmp, _summary(80.0, 0.0), _summary(80.0, 0.0),
                              PROBE_ROWS, PROBE_ROWS, DISTILL_OK, worse)
            r = self._run(env)
            self.assertEqual(r.returncode, 1, "distill 均值下降必须 FAIL")

    def test_anchor_density_regression_fails_despite_saturated_composite(self):
        """饱和契约（2026-09-13 复审）：composite 锚点项封顶后内容维度失聪
        （实测 3/5 角色 anchor_score ≈ 100），此时锚点密度**合并计数**的真实退化
        必须仍被抓——大计数下 −30% 是显著事件。"""
        with tempfile.TemporaryDirectory() as tmp:
            env = self._setup(tmp, _summary(86.9, 0.0, hits=400, chars=10000),
                              _summary(86.9, 0.0, hits=280, chars=10000),
                              PROBE_ROWS, PROBE_ROWS)
            r = self._run(env)
            self.assertEqual(r.returncode, 1, "composite 饱和不动时，锚点合并计数 −30% 必须 FAIL")
            self.assertIn("锚点", r.stdout)

    def test_anchor_noise_wobble_passes(self):
        """N7 空比较守护：小计数下的噪声级波动（20→16，−20% 但远未显著）
        不得报 FAIL——固定百分比门槛曾把这类噪声推到 ~95% 误报。"""
        with tempfile.TemporaryDirectory() as tmp:
            env = self._setup(tmp, _summary(80.0, 0.0, hits=20, chars=800),
                              _summary(80.0, 0.0, hits=16, chars=800),
                              PROBE_ROWS, PROBE_ROWS)
            r = self._run(env)
            self.assertEqual(r.returncode, 0, f"噪声级波动不得 FAIL：\n{r.stdout}")
            self.assertIn("可检测下限", r.stdout, "必须把当前样本量的功效边界印出来")

    def test_single_char_regression_below_mde_passes_with_diagnostics(self):
        """N6/N7 合力后的诚实边界：单角色 −25% 在 21 条/角色的计数下**任何**机械
        门槛都抓不准（逐角色取最差 = 取噪声极值）。契约是：整体 PASS、
        逐角色数字照打（人读诊断）、可检测下限照打（无结论要明说）。"""
        def mk(anchors: dict) -> dict:
            return {"label": "x", "arm": "a", "runs": 6, "patch": "none",
                    "summary": {c: {"n_bubbles": 12, "n_replies": 6, "composite": 85.0,
                                    "fidelity": 80.0, "hard_v_rate": 0.0,
                                    "anchor_density": round(h / x * 100, 2),
                                    "anchor_hits": h, "anchor_chars": x,
                                    "hard_any_rate": 0.1, "concrete_anchor_rate": 0.5}
                                for c, (h, x) in anchors.items()}}
        before = mk({"爱音": (3, 500), "灯": (10, 500), "立希": (5, 400),
                     "素世": (14, 500), "乐奈": (19, 400)})
        after = mk({"爱音": (3, 500), "灯": (10, 500), "立希": (5, 400),
                    "素世": (10, 500), "乐奈": (19, 400)})   # 只有素世 ~−25%
        with tempfile.TemporaryDirectory() as tmp:
            env = self._setup(tmp, before, after, PROBE_ROWS, PROBE_ROWS)
            r = self._run(env)
            self.assertEqual(r.returncode, 0, f"单角色小计数退化低于可检测下限，应 PASS：\n{r.stdout}")
            self.assertIn("素世", r.stdout, "逐角色诊断必须照打（退化靠人读）")

    def test_anchor_missing_counts_skips_and_fails(self):
        """旧批次 summary 没有 anchor_hits/chars → SKIP 且整体 FAIL（缺证据不算通过）。"""
        legacy = {"label": "x", "arm": "a", "runs": 6, "patch": "none",
                  "summary": {"乐奈": {"n_bubbles": 12, "n_replies": 6, "composite": 80.0,
                                      "fidelity": 80.0, "hard_v_rate": 0.0,
                                      "anchor_density": 2.0,
                                      "hard_any_rate": 0.1, "concrete_anchor_rate": 0.5}}}
        with tempfile.TemporaryDirectory() as tmp:
            env = self._setup(tmp, legacy, legacy, PROBE_ROWS, PROBE_ROWS)
            r = self._run(env)
            self.assertEqual(r.returncode, 1, "缺计数的产物必须 SKIP→FAIL")
            self.assertIn("probe_runner", r.stdout, "报错要指路重跑 probe_runner")

    def test_missing_artifacts_rc2(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "report").mkdir()
            r = self._run(_tool_env(Path(tmp) / "report"))
            self.assertEqual(r.returncode, 2, "缺产物必须是 rc 2 的明确报错")
            self.assertIn("找不到", r.stderr)


class AbBlindTests(unittest.TestCase):
    """W4 契约：worksheet 确定性、不泄漏臂名、key 自洽、tally 数学正确。"""

    ROWS_A = [
        {"char": "乐奈", "scenario": "s1", "scene": "comfort", "k": 0, "reply": "嗯。", "error": ""},
        {"char": "乐奈", "scenario": "s1", "scene": "comfort", "k": 1, "reply": "猫。", "error": ""},
        {"char": "乐奈", "scenario": "s2", "scene": "", "k": 0, "reply": "抹茶。", "error": ""},
    ]
    ROWS_B = [
        {"char": "乐奈", "scenario": "s1", "scene": "comfort", "k": 0, "reply": "我不清楚。", "error": ""},
        {"char": "乐奈", "scenario": "s1", "scene": "comfort", "k": 1, "reply": "请说具体些。", "error": ""},
        {"char": "乐奈", "scenario": "s2", "scene": "", "k": 0, "reply": "可以理解。", "error": ""},
    ]

    def _setup(self, tmp: str) -> tuple[dict, Path]:
        report = Path(tmp) / "report"
        report.mkdir()
        _write_jsonl(report / "probe_armAlpha.jsonl", self.ROWS_A)
        _write_jsonl(report / "probe_armBeta.jsonl", self.ROWS_B)
        return _tool_env(report), report

    def _run_blind(self, env: dict) -> subprocess.CompletedProcess:
        return _run_tool(["tools/score/ab_blind.py", "--a", "armAlpha", "--b", "armBeta"], env)

    def test_worksheet_deterministic_and_leak_free(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, report = self._setup(tmp)
            r1, r2 = self._run_blind(env), self._run_blind(env)
            self.assertEqual(r1.returncode, 0, r1.stderr[-400:])
            ws = report / "ab_blind_armAlpha_vs_armBeta.md"
            key = report / "ab_blind_armAlpha_vs_armBeta_key.json"
            self.assertTrue(ws.exists() and key.exists())
            text = ws.read_text(encoding="utf-8")
            self.assertEqual(r1.stdout, r2.stdout, "同输入连跑两次输出必须逐字相同")
            for label in ("armAlpha", "armBeta"):
                self.assertNotIn(label, text, f"worksheet 泄漏了臂名 {label}")
            mapping = json.loads(key.read_text(encoding="utf-8"))
            self.assertEqual(len(mapping["items"]), 3)
            for item_id, m in mapping["items"].items():
                with self.subTest(item=item_id):
                    self.assertIn(item_id, text)
                    self.assertEqual({m["left_arm"], m["right_arm"]}, {"armAlpha", "armBeta"})

    def test_tally_math(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, report = self._setup(tmp)
            r = self._run_blind(env)
            self.assertEqual(r.returncode, 0, r.stderr[-400:])
            key_path = report / "ab_blind_armAlpha_vs_armBeta_key.json"
            mapping = json.loads(key_path.read_text(encoding="utf-8"))
            ids = list(mapping["items"])
            # 答卷：第 1 题选左、第 2 题选右、第 3 题平局
            answers = {ids[0]: "left", ids[1]: "right", ids[2]: "tie"}
            ans_path = report / "answers.json"
            ans_path.write_text(json.dumps(answers, ensure_ascii=False), encoding="utf-8")
            t = _run_tool(["tools/score/ab_blind.py", "--tally", str(ans_path),
                           "--key", str(key_path)], env)
            self.assertEqual(t.returncode, 0, t.stderr[-400:])
            # 按 key 展开：左=left_arm 胜、右=right_arm 胜、平=各 0.5
            m0, m1 = mapping["items"][ids[0]], mapping["items"][ids[1]]
            wins = {m0["left_arm"]: 1.0, m0["right_arm"]: 0.0}
            wins[m1["right_arm"]] += 1.0
            wins[m0["left_arm"]] += 0.5
            wins[m0["right_arm"]] += 0.5
            for arm, w in wins.items():
                self.assertIn(f"{arm} {w:.1f}", t.stdout,
                              f"tally 结果里 {arm} 的胜场数不对：\n{t.stdout}")


class ReadmeMetricNamingTests(unittest.TestCase):
    """N1 契约（2026-09-13 复审）：三语 README 旗舰表的头号指标必须是 composite，
    fidelity 必须标注为对照列——落地页不许再把 fidelity 叫作「像不像」
    （docs/04 第 8 节已把那条列为常见误读，落地页与文档不得打架）。
    smoke 的 README 对账只管字数表，指标命名由这里守。"""

    READMES = {"README.md": "对照", "README.en.md": "control", "README.ja.md": "対照"}
    LIKENESS = {"README.md": "像不像", "README.en.md": "closest", "README.ja.md": "似ている"}
    HISTORICAL = {
        "README.md": "## 📊 历史探针批次（仅作定性示例）",
        "README.en.md": "## 📊 Historical probe batch (qualitative example only)",
        "README.ja.md": "## 📊 過去の probe バッチ（定性的な例のみ）",
    }

    def test_headline_metric_is_composite(self):
        for name, control_mark in self.READMES.items():
            text = (ROOT / name).read_text(encoding="utf-8")
            header = next((l for l in text.splitlines()
                           if l.startswith("|") and "fidelity" in l and "composite" in l), None)
            with self.subTest(readme=name):
                self.assertIsNotNone(header, f"{name} 旗舰表头必须同时含 composite 与 fidelity")
                self.assertLess(header.index("composite"), header.index("fidelity"),
                                "composite 必须排在 fidelity 前（头号指标位置）")
                fid_cell = next(c for c in header.split("|") if "fidelity" in c)
                self.assertIn(control_mark, fid_cell,
                              "fidelity 列必须标注为对照列")
                self.assertNotIn(self.LIKENESS[name], fid_cell,
                                 "fidelity 列不得再挂「像不像」的名义——那是误读，已移给 composite")

    def test_headline_table_is_visibly_historical(self):
        """未发布原始产物的数字必须在读者看到表格前标成历史定性示例。"""
        for name, marker in self.HISTORICAL.items():
            text = (ROOT / name).read_text(encoding="utf-8")
            table = text.find("composite")
            with self.subTest(readme=name):
                self.assertGreaterEqual(text.find(marker), 0, f"{name} 缺少显眼的历史批次标识")
                self.assertLess(text.find(marker), table, f"{name} 必须在旗舰数字表之前披露")


class ReadmeNumericParityTests(unittest.TestCase):
    """S2 契约（仓库质量评审）：三语 README 的数字必须一致。

    「三语同步」纪律此前靠人肉执行（M1 的同步漂移就是这么漏的）；实测三语独立
    数字个数曾差 1（ja 多一个，全是翻译排版分歧：九篇/9 本、五个/5 人分、
    all zero/全为 0）。口径：全部数字 token 的**多重集合**逐语言相等
    （含徽章与表格），多一个少一个都立刻红。"""

    READMES = ("README.md", "README.en.md", "README.ja.md")

    def test_numeric_tokens_identical_across_languages(self):
        import re
        from collections import Counter
        multisets = {}
        for name in self.READMES:
            text = (ROOT / name).read_text(encoding="utf-8")
            multisets[name] = Counter(re.findall(r"\d+(?:\.\d+)?", text))
        base = multisets["README.md"]
        for name in self.READMES[1:]:
            with self.subTest(readme=name):
                self.assertEqual(multisets[name], base,
                                 f"{name} 的数字与 README.md 不一致："
                                 f"多出来 {multisets[name] - base}｜缺 {base - multisets[name]}")


if __name__ == "__main__":
    unittest.main()
