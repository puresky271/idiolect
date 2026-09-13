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
  2. **anchor_ref 三来源**：gold 自带 → 场景基线派生 → 1.0 兜底，各自正确。
  3. **holdout 消费**：scene_char_baseline 的语料加载可按 split 过滤，
     holdout 为零时是显式报错而不是写出空基线。
  4. **多指标门禁**：accept_check 对 before/after 两臂逐指标独立判定，
     任一退化即整体 FAIL；缺产物是明确报错，不是静默通过。
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
        """随仓库发布的乐奈画像 + 派生 anchor_ref（复现 probe_runner 无语料路径）。"""
        raw = json.loads((ROOT / "data" / "style_profiles.json").read_text(encoding="utf-8"))
        gold = dict(raw["rana"])
        if gold.get("anchor_density") is None:
            ref = self.mod.derive_anchor_ref("乐奈")
            self.assertIsNotNone(ref, "场景基线派生 anchor_ref 失败")
            gold["anchor_density"] = ref
        return gold

    def test_score_arm_has_composite_fields(self):
        gold = self._gold_rana()
        out = self.mod.score_arm("乐奈", CAND_A_IN_CHARACTER, gold)
        for field in ("composite", "anchor_density", "anchor_ref", "anchor_score", "fidelity"):
            with self.subTest(field=field):
                self.assertIn(field, out)
        self.assertGreater(out["anchor_ref"], 1.0,
                           "乐奈的 anchor_ref 不该退回 1.0 兜底（场景基线派生必须生效）")

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

    def test_anchor_ref_fallback_chain(self):
        """gold 自带 anchor_density 时优先使用，不覆盖。"""
        sf = self.sf
        texts = ["猫。抹茶。", "嗯。"]
        gold = sf.profile_from_texts(texts, "cn")
        gold["anchor_density"] = 5.0
        comp = sf.composite_score(gold, gold, texts)
        self.assertEqual(comp["anchor_ref"], 5.0)
        # 缺字段且无显式 anchor_ref → 1.0 兜底（记录在案的旧行为，只作最后防线）
        gold2 = sf.profile_from_texts(texts, "cn")
        comp2 = sf.composite_score(gold2, gold2, texts)
        self.assertEqual(comp2["anchor_ref"], 1.0)


class ExportProfilesAnchorTests(unittest.TestCase):
    """W1 契约：export_profiles 的画像必须含 anchor_density 字段（聚合量，可发布）。"""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load("export_profiles", ROOT / "tools" / "distill" / "export_profiles.py")

    def test_build_includes_anchor_density(self):
        """用模块内函数直接构造（语料加载被换成合成文本），画像必须带 anchor_density。"""
        sf = _load("style_features", ROOT / "tools" / "distill" / "style_features.py")
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
                self.assertIn("anchor_density", out[key])
                self.assertAlmostEqual(out[key]["anchor_density"],
                                       round(sf.anchor_density(fake[key]), 3), places=3)


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
def _summary(composite: float, hard_v: float) -> dict:
    return {"label": "x", "arm": "a", "runs": 6, "patch": "none",
            "summary": {"乐奈": {"n_bubbles": 12, "n_replies": 6, "composite": composite,
                                 "fidelity": 80.0, "hard_v_rate": hard_v,
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


if __name__ == "__main__":
    unittest.main()
