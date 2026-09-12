"""评分链（tools/score/）的 golden-file 与契约测试。

这批工具此前**零测试覆盖**，而它们是「用数据证明真的变像了」的最后一公里——
输出一旦漂移（舍入、排序、列口径、静默丢行）很难被肉眼发现，正是
「静默失效比报错危险」最典型的位置。覆盖的五个工具：

  · power_calc.py    样本量计算（纯函数 n_for + 两种 CLI 形态）
  · scene_distill.py 逐场景蒸馏评分（probe jsonl + 场景基线 → md/json，全舍入、排序确定）
  · _pool_arms.py    两臂池化比较（纯 stdout）
  · _copy_audit.py   示例复述审计（渲染注入块 → 逐字包含 + 最长公共子串）
  · probe_report.py  跑完探针后的编排器（串子步骤、聚合退出码）

模式（与 test_tooling_contracts.py 相同）：`tools/_paths.py` 在 **import 时**读取
IDIOLECT_REPORT_DIR / IDIOLECT_DATA_DIR，所以一律**子进程 + 预置 env**；
输入全合成（probe jsonl 与场景基线都写进 TemporaryDirectory），全程离线——
不调 LLM、不读语料、不依赖当前时间。

golden 文件在 tests/golden/ 下，由本文件的合成输入跑出后经人眼核对提交。
失配时先确认是**预期改动**，再用同一套输入重新生成（不要手改 golden）。
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

CHARS = ["爱音", "灯", "立希", "素世", "乐奈"]
GOLDEN_DIR = ROOT / "tests" / "golden"


def _load(name: str, path: Path):
    """按文件路径加载工具模块（工具不在包内，与现有契约测试同一做法）。"""
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def _tool_env(report_dir: Path, data_dir: Path | None = None) -> dict:
    """子进程 env：REPORT/DATA 指到合成目录；语料指到不存在的位置。

    语料指向空路径是刻意的——这批工具**不该**读语料；谁将来偷读，
    谁在这个测试里当场失败（离线红线），而不是悄悄用上真实语料。
    """
    env = {**os.environ, "PYTHONIOENCODING": "utf-8",
           "IDIOLECT_REPORT_DIR": str(report_dir),
           "IDIOLECT_CORPUS_DIR": str(report_dir / "__no_corpus_here__")}
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


# ── 合成场景基线：只含评分实际读的四个字段（length.p50/p90、n_sent.mean、anchor_density）──
SCENE_BASELINE = {
    "灯|crisis": {"char": "灯", "scene": "crisis", "n": 40,
                  "length": {"p50": 13.5, "p90": 25.1}, "n_sent": {"mean": 1.325},
                  "anchor_density": 0.864},
    "乐奈|comfort": {"char": "乐奈", "scene": "comfort", "n": 40,
                     "length": {"p50": 7.0, "p90": 15.0}, "n_sent": {"mean": 1.4},
                     "anchor_density": 1.0},
}

# scene_distill 的合成探针输出：3 格可评分 + 2 行必须被静默丢弃
DISTILL_ROWS = [
    {"char": "灯", "scenario": "gen_crisis_tomori", "scene": "crisis", "reply": "不要说了。……我在。"},
    {"char": "灯", "scenario": "gen_crisis_tomori", "scene": "crisis", "reply": "别说这种话。我陪你。"},
    {"char": "灯", "scenario": "gen_crisis_tomori", "scene": "crisis", "reply": "我在。……一直都在。"},
    {"char": "乐奈", "scenario": "gen_comfort_rana", "scene": "comfort", "reply": "嗯，抱抱。"},
    {"char": "乐奈", "scenario": "gen_comfort_rana", "scene": "comfort", "reply": "猫借你。"},
    # scene="" 的行退回角色全局基线（STYLE_TARGETS），产出 "(全局)" 格
    {"char": "乐奈", "scenario": "rana_d1_nap", "scene": "", "reply": "抹茶芭菲。"},
    # 下面两行按当前契约被**静默丢弃**：没有 scene 键 / reply 为空
    {"char": "灯", "scenario": "s_no_scene_key", "reply": "这行没有 scene 键，不会进任何格。"},
    {"char": "灯", "scenario": "s_empty_reply", "scene": "crisis", "reply": ""},
]

# _pool_arms 的两臂：off 臂明显偏长（蒸馏分触底 0.000），on 臂贴近基线
POOL_OFF_ROWS = [
    {"char": "灯", "scenario": "gen_crisis_tomori", "scene": "crisis",
     "reply": "我能理解你的心情，这种感受很多人都会经历，不要太难过，一切都会好起来的，你可以跟我说说发生了什么。"},
    {"char": "灯", "scenario": "gen_crisis_tomori", "scene": "crisis",
     "reply": "听到你这样说我很担心，你不是一个人，大家都很关心你，有什么困难可以慢慢讲给我听，我会认真听你说完。"},
    {"char": "乐奈", "scenario": "gen_comfort_rana", "scene": "comfort",
     "reply": "别哭了，我在这里陪着你呢，有什么难过的事情都可以说出来，说出来心里会好受一些的。"},
    {"char": "乐奈", "scenario": "gen_comfort_rana", "scene": "comfort",
     "reply": "没关系没关系，每个人都会有撑不住的时候，先深呼吸一下，然后告诉我发生了什么好不好。"},
]
POOL_ON_ROWS = [
    {"char": "灯", "scenario": "gen_crisis_tomori", "scene": "crisis", "reply": "不要说了。……我在。"},
    {"char": "灯", "scenario": "gen_crisis_tomori", "scene": "crisis", "reply": "别说这种话。我陪你。"},
    {"char": "乐奈", "scenario": "gen_comfort_rana", "scene": "comfort", "reply": "嗯，抱抱。"},
    {"char": "乐奈", "scenario": "gen_comfort_rana", "scene": "comfort", "reply": "猫借你。"},
]


class PowerCalcTests(unittest.TestCase):
    """钉的约束：n_for 的口径（docstring 里引用的数）+ `--sd/--effect` 形态零写盘
    + 三个 rana_reg_* 探针产物缺失时回退模块内置的实测 sd。"""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load("power_calc", ROOT / "tools" / "score" / "power_calc.py")

    def test_n_for_matches_documented_numbers(self):
        """docstring 与实测表引用的样本量必须能从公式复算出来（sd=0.382 口径）。"""
        for effect, want in ((0.15, 25), (0.10, 57), (0.05, 225), (0.03, 623)):
            with self.subTest(effect=effect):
                self.assertEqual(self.mod.n_for(effect, 0.382), want)

    def test_n_for_edge_and_monotonicity(self):
        """非正效应量是「做不到」的哨兵值（1e9），不是崩；n 随效应量/噪声单调变化。"""
        n_for = self.mod.n_for
        self.assertEqual(n_for(0.0, 0.382), 10 ** 9)
        self.assertEqual(n_for(-0.05, 0.382), 10 ** 9)
        self.assertGreater(n_for(0.03, 0.382), n_for(0.05, 0.382))
        self.assertGreater(n_for(0.05, 0.45), n_for(0.05, 0.347))

    def test_cli_sd_effect_writes_nothing(self):
        """`--sd 0.382 --effect 0.05` 是纯 stdout 计算——**零写盘**是它唯一能进 CI 的形态。"""
        with tempfile.TemporaryDirectory() as tmp:
            r = _run_tool(["tools/score/power_calc.py", "--sd", "0.382", "--effect", "0.05"],
                          _tool_env(Path(tmp)))
            self.assertEqual(r.returncode, 0, r.stderr[-400:])
            self.assertIn("效应 5pp 需 225 条/臂", r.stdout)
            self.assertEqual(list(Path(tmp).iterdir()), [], "此形态不得写任何文件")

    def test_cli_table_mode_falls_back_to_measured_sd(self):
        """REPORT 里没有三个 rana_reg_* 探针产物时，回退到模块里的实测 sd 表（离线可跑）。"""
        with tempfile.TemporaryDirectory() as tmp:
            r = _run_tool(["tools/score/power_calc.py"], _tool_env(Path(tmp)))
            self.assertEqual(r.returncode, 0, r.stderr[-400:])
            self.assertIn("nominal_start", r.stdout)
            out = json.loads((Path(tmp) / "power_calc.json").read_text(encoding="utf-8"))
            self.assertEqual(out["nominal_start"]["single_sd"], 0.382)
            self.assertEqual(out["nominal_start"]["n_for_5pp"], 225)


class SceneDistillGoldenTests(unittest.TestCase):
    """scene_distill 全量输出 golden：字段固定舍入、按 excess 降序 → 可逐字比对。

    钉的约束：
      1. 输出只依赖 probe jsonl + 场景基线（两者全合成，离线可复现）；
      2. 缺 scene 键 / 空 reply 的行被**静默丢弃**（当前契约——已知缝隙，见交付报告）；
      3. scene="" 的行退回角色全局基线（STYLE_TARGETS），场景名显示 "(全局)"；
      4. 打印到 stdout 的报告与落盘的 scene_distill.md 内容一致；
      5. 同输入连跑两次，输出逐字相同（确定性）。
    """

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="idio_distill_")
        cls.addClassCleanup(cls._tmp.cleanup)
        base = Path(cls._tmp.name)
        cls.report, cls.data = base / "report", base / "data"
        cls.report.mkdir()
        cls.data.mkdir()
        _write_jsonl(cls.report / "probe_t1.jsonl", DISTILL_ROWS)
        (cls.data / "scene_char_baseline.json").write_text(
            json.dumps(SCENE_BASELINE, ensure_ascii=False), encoding="utf-8")
        cls.env = _tool_env(cls.report, cls.data)
        cls.runs = [_run_tool(["tools/score/scene_distill.py", "--labels", "t1"], cls.env)
                    for _ in range(2)]
        for r in cls.runs:
            if r.returncode != 0:
                raise AssertionError(f"scene_distill 跑失败：{r.stdout[-400:]}{r.stderr[-400:]}")

    def _scored(self) -> list[dict]:
        return json.loads((self.report / "scene_distill_t1.json").read_text(encoding="utf-8"))

    def test_json_golden_matches(self):
        got = self._scored()
        want = json.loads((GOLDEN_DIR / "scene_distill_t1.json").read_text(encoding="utf-8"))
        self.assertEqual(got, want,
                         "与 golden 失配——若是预期改动，用本测试的合成输入重新生成 "
                         "tests/golden/scene_distill_t1.json")

    def test_markdown_golden_matches(self):
        got = (self.report / "scene_distill.md").read_text(encoding="utf-8")
        want = (GOLDEN_DIR / "scene_distill.md").read_text(encoding="utf-8")
        self.assertEqual(got, want,
                         "与 golden 失配——若是预期改动，用本测试的合成输入重新生成 "
                         "tests/golden/scene_distill.md")

    def test_stdout_is_identical_to_markdown_file(self):
        """同一份 lines 的两次输出（stdout / 落盘 md）不得漂移。"""
        md = (self.report / "scene_distill.md").read_text(encoding="utf-8")
        self.assertEqual(self.runs[0].stdout, md)

    def test_silent_drops_produce_exactly_three_cells(self):
        """无 scene 键、空 reply 的两行**不报错也不留痕**地被丢弃——钉住这个丢弃面，
        将来收窄（改成显式警告）或扩大（多丢了不该丢的）都会立刻红。"""
        cells = {(s["char"], s["scene"]) for s in self._scored()}
        self.assertEqual(cells, {("灯", "crisis"), ("乐奈", "comfort"), ("乐奈", "(全局)")})

    def test_blank_scene_uses_global_fallback(self):
        """scene="" 的格子参照物是 STYLE_TARGETS 的角色全局数字（乐奈：中位 6 / p90 13）。"""
        cell = next(s for s in self._scored() if s["scene"] == "(全局)")
        self.assertEqual(cell["base_med"], 6.0)
        self.assertEqual(cell["base_p90"], 13.0)

    def test_deterministic_across_reruns(self):
        self.assertEqual(self.runs[0].stdout, self.runs[1].stdout,
                         "同一输入连跑两次输出不同——排序/舍入里混进了不确定因素")

    def test_shipped_baseline_schema(self):
        """随仓库发布的基线是 scene_distill 的参照物：130 格、五角色、四个评分字段齐全。"""
        base = json.loads((ROOT / "data" / "scene_char_baseline.json").read_text(encoding="utf-8"))
        self.assertEqual(len(base), 130, "26 场景 × 5 角色 = 130 格")
        self.assertEqual({k.split("|")[0] for k in base}, set(CHARS))
        for key, cell in base.items():
            with self.subTest(cell=key):
                self.assertIn("p50", cell["length"])
                self.assertIn("p90", cell["length"])
                self.assertIn("mean", cell["n_sent"])
                self.assertIn("anchor_density", cell)


class PoolArmsTests(unittest.TestCase):
    """_pool_arms：两臂池化后的蒸馏均值比较（纯 stdout，零写盘）。

    钉的约束：
      1. 两臂有共同可评分格时输出完整比较（蒸馏均值 Δ、逐格胜负、长度比值、明细表）；
      2. 探针产物找不到时是优雅 [skip]（rc 0），不是报错；
      3. stdout 全量 golden + 连跑两次逐字相同。

    刻意避开「文件都在但共同格为 0」的输入——那会 fmean([]) 崩溃，
    是已记录的坑（见交付报告），不是本测试要钉的契约。
    """

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="idio_pool_")
        cls.addClassCleanup(cls._tmp.cleanup)
        base = Path(cls._tmp.name)
        cls.report, cls.data = base / "report", base / "data"
        cls.report.mkdir()
        cls.data.mkdir()
        _write_jsonl(cls.report / "probe_pooloff.jsonl", POOL_OFF_ROWS)
        _write_jsonl(cls.report / "probe_poolon.jsonl", POOL_ON_ROWS)
        (cls.data / "scene_char_baseline.json").write_text(
            json.dumps(SCENE_BASELINE, ensure_ascii=False), encoding="utf-8")
        cls.env = _tool_env(cls.report, cls.data)
        cls.runs = [_run_tool(["tools/score/_pool_arms.py", "pooloff", "poolon"], cls.env)
                    for _ in range(2)]
        for r in cls.runs:
            if r.returncode != 0:
                raise AssertionError(f"_pool_arms 跑失败：{r.stdout[-400:]}{r.stderr[-400:]}")

    def test_stdout_golden_matches(self):
        want = (GOLDEN_DIR / "pool_arms_stdout.txt").read_text(encoding="utf-8")
        self.assertEqual(self.runs[0].stdout, want,
                         "与 golden 失配——若是预期改动，用本测试的合成输入重新生成 "
                         "tests/golden/pool_arms_stdout.txt")

    def test_deterministic_across_reruns(self):
        self.assertEqual(self.runs[0].stdout, self.runs[1].stdout)

    def test_key_figures_present(self):
        """池化的核心结论：off 臂蒸馏分触底、on 臂两格全改善、长度比值回到 1 附近。"""
        out = self.runs[0].stdout
        self.assertIn("共有 2 格", out)
        self.assertIn("蒸馏均值：0.000 → 0.256", out)
        self.assertIn("逐格：2 改善 / 0 退化 / 0 持平", out)
        self.assertIn("更接近 1.0 的格：2/2", out)

    def test_writes_nothing(self):
        """池化是纯 stdout 工具——REPORT 里只能有输入的那两个 jsonl。"""
        self.assertEqual(sorted(p.name for p in self.report.iterdir()),
                         ["probe_pooloff.jsonl", "probe_poolon.jsonl"])

    def test_missing_labels_skip_gracefully(self):
        """找不到探针产物 → 打 [skip] 提示并 rc 0（调用方常批量拼臂，缺一个不该炸全场）。"""
        r = _run_tool(["tools/score/_pool_arms.py", "ghost1", "ghost2"], self.env)
        self.assertEqual(r.returncode, 0, r.stderr[-400:])
        self.assertIn("[skip]", r.stdout)


class CopyAuditPureTests(unittest.TestCase):
    """example_literals / lcs 是纯函数，直接 import 单测（不经子进程）。"""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load("_copy_audit", ROOT / "tools" / "score" / "_copy_audit.py")

    def test_lcs_basics(self):
        """最长公共子串：空串为 0、全等即全长、中英混合按字符计、对参数对称。"""
        lcs = self.mod.lcs
        self.assertEqual(lcs("", "任何串"), 0)
        self.assertEqual(lcs("不要难过", "不要难过"), 4)
        self.assertEqual(lcs("abcdef", "zbcdew"), 4)      # 公共段 "bcde"
        self.assertEqual(lcs("今天下雨了", "明天下雨了"), 4)  # 公共段 "天下雨了"
        for a, b in (("abcdef", "zbcdew"), ("今天下雨了", "明天下雨了")):
            with self.subTest(a=a, b=b):
                self.assertEqual(lcs(a, b), lcs(b, a))

    def test_example_literals_scope(self):
        """抽取口径（2026-09-12 收紧后的当前契约）：
        扫**所有行**的「」引用，只排两处——口癖提示行（口癖本来就该她说）、
        占位符（含（）/·— 或纯 ASCII）与 1 字 token。
        """
        block = "\n".join([
            "- 形态示例：「我会一直在你身边」",
            "- 口癖提示：「嗯。」「行了。」",       # 整行排除
            "- 参考：「（名字）今天也很可爱」",      # 占位符排除
            "- 正例：「嗯」",                        # 1 字排除
            "- 备注：「SPACE」",                     # 纯 ASCII 排除
            "- 没有示例标记的普通一行：「普通引用也收」",  # 仍要收（现在扫所有行）
        ])
        got = self.mod.example_literals(block)
        self.assertIn("我会一直在你身边", got)
        self.assertIn("普通引用也收", got)
        for bad in ("嗯。", "行了。", "（名字）今天也很可爱", "嗯", "SPACE"):
            with self.subTest(token=bad):
                self.assertNotIn(bad, got)


class CopyAuditEndToEndTests(unittest.TestCase):
    """复述审计全链路：渲染注入块 → 把示例片段拼进 reply → 工具必须报出逐字命中。

    钉的约束：
      1. label 不含 "off" 的臂渲染注入块；把块里 ≥3 字的示例片段逐字拼进 reply
         → 必报「逐字复述」；
      2. label 含 "off" 的臂**不渲染**块 → 同样的 reply 复述率 0%（巧合重叠下限）；
      3. 夹具 id 在 probe_scenarios 里查不到的格被**静默跳过**（当前契约——已知缝隙）；
      4. 渲染确定性：测试进程渲染出的块与工具子进程渲染的逐字相同，
         否则拼进去的片段不会命中——这条本身就是契约。
    """

    FIXTURE_ID = "gen_crisis_tomori"  # 通用场景 · 灯 · crisis 的真实夹具 id

    @classmethod
    def setUpClass(cls):
        cls.mod = _load("_copy_audit", ROOT / "tools" / "score" / "_copy_audit.py")
        import idiolect.registry as RP
        import probe_scenarios as PS  # noqa: E402  （_copy_audit 的引导已把 tools/probe 挂上 sys.path）

        cls.fixture_text = next(sc["text"] for sc in PS.SCENARIOS["灯"] if sc["id"] == cls.FIXTURE_ID)
        block = RP.render_turn_special_block("灯", cls.fixture_text,
                                             session_id="test:copy_audit:setup",
                                             is_developer=False, mode="chat")
        if not block:
            raise AssertionError("crisis 夹具没渲染出注入块——触发链断了")
        lits = [x for x in cls.mod.example_literals(block) if x not in cls.mod.canon_text("灯")]
        cls.lit = max(lits, key=len)
        if len(cls.lit) < 3:
            raise AssertionError("注入块里没有 ≥3 字、可稳定制造复述命中的片段")

        cls._tmp = tempfile.TemporaryDirectory(prefix="idio_ca_")
        cls.addClassCleanup(cls._tmp.cleanup)
        cls.report = Path(cls._tmp.name) / "report"
        cls.report.mkdir()
        rows = [
            {"char": "灯", "scenario": cls.FIXTURE_ID, "scene": "crisis",
             "reply": f"……{cls.lit}"},                 # 逐字复述注入块示例
            {"char": "灯", "scenario": cls.FIXTURE_ID, "scene": "crisis",
             "reply": "不要说了。我在。"},                # 干净对照
            {"char": "灯", "scenario": "no_such_fixture_id", "scene": "crisis",
             "reply": "这行的夹具 id 不存在，会被静默跳过。"},
        ]
        for lab in ("cauditoff", "cauditon"):
            _write_jsonl(cls.report / f"probe_{lab}.jsonl", rows)
        cls.env = _tool_env(cls.report)
        cls.result = _run_tool(
            ["tools/score/_copy_audit.py", "--cat", "通用场景",
             "--labels", "cauditoff,cauditon", "--detail"], cls.env)
        if cls.result.returncode != 0:
            raise AssertionError(f"_copy_audit 跑失败：{cls.result.stdout[-400:]}"
                                 f"{cls.result.stderr[-400:]}")

    def _row(self, label: str) -> list[str]:
        """汇总表里某臂的一行 → 按空白切 token：
        [臂, 格数, 回复数, 逐字复述, 复述率, 近似复述, 最长引用, 最长公共子串]。"""
        for line in self.result.stdout.splitlines():
            parts = line.split()
            if parts and parts[0] == label:
                return parts
        raise AssertionError(f"汇总表里找不到臂 {label}：\n{self.result.stdout}")

    def test_on_arm_reports_verbatim_hit(self):
        row = self._row("cauditon")
        self.assertEqual(row[1], "1", "格数：unknown 夹具 id 那格被静默跳过，只剩 1 格")
        self.assertEqual(row[2], "2", "回复数：跳过的那行不计入")
        self.assertEqual(row[3], "1", "逐字复述：拼进去的那条必须被报出")
        self.assertEqual(row[4], "50%")
        self.assertEqual(row[5], "0", "干净对照不得触发近似复述")
        self.assertEqual(row[6], str(len(self.lit)), "最长引用 = 最长示例片段")
        self.assertEqual(row[7], str(len(self.lit)), "逐字包含 → 最长公共子串即片段全长")

    def test_off_arm_is_zero_floor(self):
        """off 臂不渲染注入块 → 同样的 reply 复述率 0%（它量的是巧合重叠下限）。"""
        row = self._row("cauditoff")
        self.assertEqual(row[1], "1")
        self.assertEqual(row[3], "0")
        self.assertEqual(row[4], "0%")

    def test_detail_lists_the_copied_literal(self):
        """--detail 必须点名被复述的是哪一句——「抄了哪句」正是这个工具存在的理由。"""
        self.assertIn("被复述的示例句", self.result.stdout)
        self.assertIn(self.lit, self.result.stdout)

    def test_audit_function_dict_contract(self):
        """不经子进程直接调 audit()：钉返回结构的字段口径（cells / hits）。"""
        old = self.mod.REPORT
        self.mod.REPORT = self.report
        try:
            res = self.mod.audit("cauditon", "通用场景")
        finally:
            self.mod.REPORT = old
        cell = res["cells"][("灯", self.FIXTURE_ID)]
        self.assertEqual(cell["n"], 2)
        self.assertEqual(cell["n_hit"], 1)
        self.assertEqual(cell["n_near"], 0)
        self.assertEqual(self.mod.hit_counter if False else res["hits"].get(self.lit), 1)


class ProbeReportTests(unittest.TestCase):
    """编排器 probe_report：串子步骤、把 env 透传给子进程、聚合退出码。

    钉的约束：
      1. probe_<label>.jsonl 存在 → 最小必跑 scene_distill 与 _repeat_rate，rc 0；
      2. 缺文件 → stderr 一行提示 + rc 2，且**不跑任何子步骤**（快速失败）；
      3. 子步骤失败不中断后续步骤，但最终 rc 非零（rc |= 聚合）。
    """

    def _setup_report(self, tmp: str, rows: list[dict], label: str) -> dict:
        report, data = Path(tmp) / "report", Path(tmp) / "data"
        report.mkdir()
        data.mkdir()
        _write_jsonl(report / f"probe_{label}.jsonl", rows)
        (data / "scene_char_baseline.json").write_text(
            json.dumps(SCENE_BASELINE, ensure_ascii=False), encoding="utf-8")
        return _tool_env(report, data)

    def test_minimal_run_executes_required_steps(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = self._setup_report(tmp, DISTILL_ROWS[:2], "rep")
            r = _run_tool(["tools/score/probe_report.py", "--label", "rep"], env)
            self.assertEqual(r.returncode, 0, r.stderr[-400:])
            for marker in ("$ scene_distill.py --labels rep", "$ _repeat_rate.py rep",
                           "[probe_report] 完成"):
                with self.subTest(marker=marker):
                    self.assertIn(marker, r.stdout)
            report = Path(tmp) / "report"
            scored = json.loads((report / "scene_distill_rep.json").read_text(encoding="utf-8"))
            self.assertEqual(len(scored), 1, "只有 灯|crisis 一格可评分")
            self.assertTrue((report / "scene_distill.md").exists())

    def test_missing_probe_file_fails_fast(self):
        """缺输入时 stderr 只有一行人话提示、不跑任何子步骤——编排器不许「半截报告」。"""
        with tempfile.TemporaryDirectory() as tmp:
            env = _tool_env(Path(tmp))
            r = _run_tool(["tools/score/probe_report.py", "--label", "ghost"], env)
            self.assertEqual(r.returncode, 2)
            lines = r.stderr.strip().splitlines()
            self.assertEqual(len(lines), 1, f"stderr 应只有一行提示：{r.stderr!r}")
            self.assertIn("[probe_report] 找不到", lines[0])
            self.assertIn("先跑 probe_runner", lines[0])
            self.assertEqual(r.stdout.strip(), "", "快速失败之前不得跑任何子步骤")

    def test_child_failure_aggregates_to_nonzero_rc(self):
        """子步骤崩溃不中断编排，但 rc 必须非零——「跑完了」与「全成功」是两回事。

        触发方式：probe 文件存在但 0 有效行 → _repeat_rate 除零崩溃（已记录的坑，
        见交付报告）；这里钉的是编排器的聚合契约：继续跑完 + rc 1。
        """
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "report"
            report.mkdir()
            (report / "probe_zero.jsonl").write_text("\n", encoding="utf-8")
            r = _run_tool(["tools/score/probe_report.py", "--label", "zero"],
                          _tool_env(report))
            self.assertEqual(r.returncode, 1, f"子步骤失败必须反映到退出码：{r.returncode}")
            self.assertIn("[probe_report] 完成", r.stdout, "子步骤失败不应中断后续步骤")


if __name__ == "__main__":
    unittest.main()
