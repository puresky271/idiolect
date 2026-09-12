"""工具层契约测试：mock 时钟、装配完整性、元叙述门禁、探针装配不被覆盖。

这三类断言都对应**真实踩过的坑**，所以放在一起：

  1. **mock 时钟** —— 评测必须跑在固定白天时刻；时钟一旦能被真实时间污染，
     跨批次数字就不可比（原项目把这条写成硬规矩）。
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


if __name__ == "__main__":
    unittest.main()
