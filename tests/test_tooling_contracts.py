"""工具层契约测试：mock 时钟、装配完整性、元叙述门禁、探针装配不被覆盖。

这三类断言都对应**真实踩过的坑**，所以放在一起：

  1. **mock 时钟** —— 评测必须跑在固定白天时刻；时钟一旦能被真实时间污染，
     跨批次数字就不可比（这条是硬规矩）。
  2. **装配不被覆盖** —— `probe_runner` 曾把 `--assemble` 装好的 system
     原地覆盖成夹具自带的空字符串，模型收到空 system，回复退化成通用助手腔，
     而报告里只看得到「fidelity 低」。**静默失效比报错危险**，所以有一条
     端到端断言（dry-run 不调 LLM）。
  3. **元叙述门禁覆盖面** —— 门禁曾只扫 voice.py，漏掉 style_target 的块标题
     （写着「实测台词基线」，而「实测」就在禁词表里）。现在扫 canon /
     style_target / turn_logic 三个面，测试直接对**装配结果**断言。
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import mock_clock as MOCK  # noqa: E402

CHARS = ["爱音", "灯", "立希", "素世", "乐奈"]


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


class MockClockTests(unittest.TestCase):
    def tearDown(self) -> None:
        os.environ.pop(MOCK.ENV_VAR, None)

    def test_default_is_pinned_daytime(self):
        os.environ.pop(MOCK.ENV_VAR, None)
        now = MOCK.mock_now()
        self.assertEqual(now.isoformat(), MOCK.DEFAULT_MOCK_ISO)
        self.assertTrue(MOCK.is_mocked())
        self.assertEqual(now.hour, 15, "默认必须是白天——夜里会命中犯困/深夜类场景")

    def test_stable_across_calls(self):
        os.environ.pop(MOCK.ENV_VAR, None)
        self.assertEqual(MOCK.mock_now(), MOCK.mock_now(), "mock 时钟必须完全确定")

    def test_env_override_and_naive_iso_is_jst(self):
        os.environ[MOCK.ENV_VAR] = "2026-09-12T03:00:00"
        now = MOCK.mock_now()
        self.assertEqual(now.hour, 3)
        self.assertEqual(now.utcoffset().total_seconds(), 9 * 3600, "无时区按 JST 解释")

    def test_real_token_disables_pinning(self):
        os.environ[MOCK.ENV_VAR] = "real"
        self.assertFalse(MOCK.is_mocked())

    def test_bad_spec_raises(self):
        with self.assertRaises(ValueError):
            MOCK.parse_spec("昨天下午")


class AssemblyContractTests(unittest.TestCase):
    """四层装配：非空、有序、无元叙述。"""

    def test_prompt_is_never_empty(self):
        from idiolect.assemble import build_system_prompt

        for char in CHARS:
            system = build_system_prompt(char, "在干嘛", now=MOCK.mock_now())
            self.assertGreater(len(system), 5000, f"{char} 的 system 太短，装配可能没生效")

    def test_layer_order_is_canon_first(self):
        from idiolect.assemble import LAYER_ORDER, build_system_prompt

        self.assertEqual(LAYER_ORDER[0], "canon")
        system = build_system_prompt("乐奈", "明天几点上课", now=MOCK.mock_now())
        i_canon = system.find("一句话定位")
        i_voice = system.find("[语气清单]")
        self.assertGreaterEqual(i_canon, 0, "canon 没进 prompt")
        if i_voice >= 0:
            self.assertLess(i_canon, i_voice, "canon 必须在 voice 之前（稳定前缀优先）")

    def test_scene_hit_changes_length_target(self):
        """命中场景时说话尺度块必须变（否则场景化目标形同虚设）。"""
        from idiolect.style_target import build_style_target_block

        for char in CHARS:
            generic = build_style_target_block(char, "")
            crisis = build_style_target_block(char, "crisis")
            self.assertTrue(generic and crisis, f"{char} 缺说话尺度块")
            self.assertNotEqual(generic, crisis, f"{char} 的场景块与全局块相同")

    def test_no_meta_narrative_in_assembled_prompt(self):
        """装配结果里不许出现元叙述词汇——门禁的盲区正是这一类泄漏。"""
        from idiolect.assemble import build_system_prompt

        gate = _load(ROOT / "tools" / "gates" / "voice_meta_gate.py", "voice_meta_gate")
        msgs = ["在干嘛", "明天几点上课", "我一直在哭，快撑不住了", "爱音今天来练习了吗"]
        hits: list[str] = []
        for char in CHARS:
            for msg in msgs:
                system = build_system_prompt(char, msg, session_id=f"t:{char}", now=MOCK.mock_now())
                hits += [f"{char}/{msg[:6]}:{w}" for w in gate.META_HARD if w in system]
        self.assertEqual(hits, [], f"角色可见文本含元叙述：{sorted(set(hits))}")

    def test_turn_logic_respects_mock_clock(self):
        """turn_logic 必须能从外部拿到「现在」——否则 mock 时钟管不住它。"""
        import inspect

        from idiolect.registry import render_turn_special_block

        params = inspect.signature(render_turn_special_block).parameters
        self.assertIn("kwargs", params, "render_turn_special_block 应透传 now/now_jst")
        block = render_turn_special_block(
            "乐奈", "明天几点上课", session_id="t:clock", now_jst=MOCK.mock_now())
        self.assertTrue(block, "schedule 场景在 mock 时间下应当命中")


class ProbeAssembleRegressionTests(unittest.TestCase):
    """`--assemble` 必须真的进到发给模型的 messages 里（历史上被静默覆盖）。"""

    @classmethod
    def setUpClass(cls):
        cls.report = ROOT / "report"
        cls.report.mkdir(parents=True, exist_ok=True)
        cls.jsonl = cls.report / "probe_unittest.jsonl"

    def test_assemble_reaches_messages(self):
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        env.pop(MOCK.ENV_VAR, None)
        r = subprocess.run(
            [sys.executable, "-X", "utf8", "tools/probe/probe_runner.py",
             "--label", "unittest", "--dry-run", "--assemble", "--turn-logic",
             "--registry", "--cats", "通用场景", "--chars", "乐奈", "--runs", "1"],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
        self.assertEqual(r.returncode, 0, f"dry-run 失败：{r.stdout[-800:]}{r.stderr[-800:]}")
        rows = [json.loads(line) for line in self.jsonl.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertTrue(rows, "探针没落盘任何记录")
        thin = [row["scenario"] for row in rows if row["prompt_chars"] < 5000]
        self.assertEqual(thin, [], f"这些场景的 system 段是空的/被覆盖了：{thin}")
        self.assertTrue(any(row["turn_logic_chars"] > 0 for row in rows),
                        "整批都没注入 turn_logic——注入开关或触发链断了")

    @classmethod
    def tearDownClass(cls):
        for p in (cls.jsonl, cls.report / "probe_unittest.md",
                  cls.report / "probe_unittest_summary.json"):
            p.unlink(missing_ok=True)


class SmokeToolTests(unittest.TestCase):
    """冒烟脚本自身必须可跑、且真的零写（除了 report/）。"""

    def test_offline_smoke_fast_passes(self):
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        env.pop(MOCK.ENV_VAR, None)
        r = subprocess.run([sys.executable, "-X", "utf8", "tools/offline_smoke.py", "--fast"],
                           cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", env=env)
        self.assertEqual(r.returncode, 0, f"smoke 未通过：{r.stdout[-1200:]}")

    def test_dump_prompt_writes_layers(self):
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        env.pop(MOCK.ENV_VAR, None)
        r = subprocess.run([sys.executable, "-X", "utf8", "tools/gates/dump_prompt.py",
                            "--char", "乐奈", "--msg", "你今天又想去哪找猫"],
                           cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", env=env)
        self.assertEqual(r.returncode, 0, f"dump 失败：{r.stdout[-800:]}")

    def test_shipped_profiles_have_no_text(self):
        """随仓库发布的画像只能是聚合量，不能带原作文本。"""
        prof = json.loads((ROOT / "data" / "style_profiles.json").read_text(encoding="utf-8"))
        self.assertIn("note", prof)
        for key in ("anon", "tomori", "taki", "soyo", "rana"):
            node = prof[key]
            self.assertGreater(node["n"], 0)
            self.assertNotIn("texts", node)
            self.assertNotIn("examples", node)

    def test_publish_paths_can_strip_exemplars(self):
        """发布形态必须由工具自己产出：两个带例句的产物都要有 `--no-exemplars`。

        发布的 `data/scene_char_baseline.json` 与 `data/scene_stats.json` 是剥离例句后的
        形态。剥离动作一度只存在于临时的发布脚本里（人工步骤），于是「data/ 是怎么来的」
        无法从仓库复现。现在它是脚本的一个 flag。
        """
        for tool in ("scene_char_baseline.py", "scene_stats.py"):
            r = subprocess.run([sys.executable, "-X", "utf8", f"tools/distill/{tool}", "--help"],
                               cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                               errors="replace")
            self.assertEqual(r.returncode, 0, f"{tool} --help 失败")
            self.assertIn("--no-exemplars", r.stdout, f"{tool} 缺 --no-exemplars")
            self.assertIn("--out", r.stdout, f"{tool} 缺 --out")


class CorpusGuardTests(unittest.TestCase):
    """空语料必须**当场退出**，不许写出空产物。

    2026-09-13 踩过：语料路径存在但内容为 0 行时，所有统计脚本都会「成功」跑完并写出
    空文件（style_targets 空、0 个 cell），退出码还是 0。一次误调用就能把外部语料目录
    覆盖成空文件。现在两道守卫：读侧 require_corpus()、写侧零行拒绝。
    """

    def test_require_corpus_rejects_empty_file(self):
        import sys as _s

        _s.path.insert(0, str(ROOT / "tools"))
        import tempfile
        import _paths

        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "cn.jsonl"
            empty.write_text("", encoding="utf-8")
            old = _paths.CORPUS_DIR
            _paths.CORPUS_DIR = Path(tmp)
            try:
                with self.assertRaises(SystemExit) as ctx:
                    _paths.require_corpus("cn")
                self.assertIn("0 行", str(ctx.exception))
            finally:
                _paths.CORPUS_DIR = old

    def test_require_corpus_rejects_missing_file_without_traceback(self):
        """语料**不存在**时同样要给人话提示，不许抛 FileNotFoundError traceback。

        两者是同一种操作失误，走到脚本层面看到的东西应该一样（一行 [stop] 提示）。
        """
        import sys as _s

        _s.path.insert(0, str(ROOT / "tools"))
        import tempfile
        import _paths

        with tempfile.TemporaryDirectory() as tmp:
            old = _paths.CORPUS_DIR
            _paths.CORPUS_DIR = Path(tmp)  # 目录存在，但里面没有 cn.jsonl
            try:
                with self.assertRaises(SystemExit) as ctx:
                    _paths.require_corpus("cn")
                msg = str(ctx.exception)
                self.assertIn("[stop]", msg)
                self.assertIn("IDIOLECT_CORPUS_DIR", msg)
            finally:
                _paths.CORPUS_DIR = old

    def test_corpus_missing_end_to_end_is_one_line(self):
        """真跑一个脚本：缺语料时 stderr 只有提示、没有 traceback。"""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            env = {**os.environ, "PYTHONIOENCODING": "utf-8", "IDIOLECT_CORPUS_DIR": tmp}
            r = subprocess.run([sys.executable, "-X", "utf8", "tools/score/_noun_initial.py", "x"],
                               cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                               errors="replace", env=env)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("[stop]", r.stderr)
            self.assertNotIn("Traceback", r.stderr)

    def test_build_gold_refuses_empty_output(self):
        """源文件缺失时 build_gold 必须拒绝写出（否则会清空目标目录）。"""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            r = subprocess.run(
                [sys.executable, "-X", "utf8", "tools/corpus/build_gold.py",
                 "--out", tmp, "--langs", "cn"],
                cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
            self.assertEqual(r.returncode, 2, f"应当拒绝写出：{r.stdout[-400:]}")
            self.assertIn("拒绝写出", r.stdout)
            self.assertFalse((Path(tmp) / "cn.jsonl").exists(), "拒绝之后不应留下空文件")

    def test_build_gold_dry_run_needs_no_sources(self):
        r = subprocess.run(
            [sys.executable, "-X", "utf8", "tools/corpus/build_gold.py", "--dry-run", "--force-empty"],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(r.returncode, 0, f"dry-run 不该失败：{r.stdout[-400:]}")
        self.assertIn("dry-run", r.stdout)

    def test_logodds_is_deterministic_across_processes(self):
        """同名次并列的词必须有稳定顺序，否则「发布数据可重建」不成立。

        依据：`logodds_signature` 从 `set` 迭代取词，只按 logodds 排序时，同为 2.48 的
        两个词谁进 top-N 会随进程的字符串哈希随机化变化。
        """
        code = (
            "import sys; sys.path.insert(0, 'tools/distill'); sys.path.insert(0, 'tools');"
            "import json, style_features as S;"
            "t=['雨很大','躲雨','在大厅躲雨','雨','淋湿了','猫在屋檐下','躲','大厅里']*3;"
            "b=['吉他','练习','演出','谱','弦']*6;"
            "print(json.dumps(S.logodds_signature(t,b,'cn',top=8),ensure_ascii=False))"
        )
        outs = set()
        for _ in range(3):
            r = subprocess.run([sys.executable, "-X", "utf8", "-c", code], cwd=ROOT,
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
            self.assertEqual(r.returncode, 0, r.stderr[-300:])
            outs.add(r.stdout.strip())
        self.assertEqual(len(outs), 1, f"三次独立进程的结果不同：{outs}")


if __name__ == "__main__":
    unittest.main()
