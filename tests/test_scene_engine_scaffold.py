"""scene_engine 共享脚手架的契约测试（2026-09-12 重构下沉时先写）。

钉住的约束：
  · env_enabled 的假值表全仓统一（off/no 与 0/false 同等生效）；
  · wrap_blocks 的双线 fence 形态逐字固定（五角色 turn_logic 的输出契约）；
  · run_modules 的执行语义：异常不中断、needs_text 跳过、max_blocks 只数产出块、
    literal_copy_note 追加脚注、per_module_kwargs 透传；
  · SessionStore 的 LRU 上限：session 数不超 max_sessions、最久未用先淘汰；
  · scene_engine 模块级 reset_session / _mark_fired 行为不变（含空 session 共享桶）。
"""
import unittest

from idiolect import scene_engine as se


class EnvEnabledTests(unittest.TestCase):
    def test_unset_means_enabled(self):
        self.assertTrue(se.env_enabled(None))

    def test_unified_false_values(self):
        for raw in ("0", "false", "False", "off", "no", ""):
            with self.subTest(raw=raw):
                self.assertFalse(se.env_enabled(raw))

    def test_other_values_mean_enabled(self):
        for raw in ("1", "true", "yes", "on", "anything"):
            with self.subTest(raw=raw):
                self.assertTrue(se.env_enabled(raw))


class WrapBlocksTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(se.wrap_blocks([]), "")
        self.assertEqual(se.wrap_blocks([""]), "")

    def test_single_block_fence_form(self):
        got = se.wrap_blocks(["abc"])
        self.assertEqual(got, f"{se.BLOCK_BORDER}\nabc\n{se.BLOCK_BORDER}")

    def test_blocks_joined_with_blank_line_and_rstripped(self):
        got = se.wrap_blocks(["a  ", "b\n"])
        self.assertEqual(
            got,
            f"{se.BLOCK_BORDER}\na\n{se.BLOCK_BORDER}\n\n{se.BLOCK_BORDER}\nb\n{se.BLOCK_BORDER}")

    def test_border_is_72_fullwidth_equals(self):
        self.assertEqual(se.BLOCK_BORDER, "═" * 72)


class RunModulesTests(unittest.TestCase):
    def test_order_and_fired_keys(self):
        def b1(text, **kw): return "B1"
        def b2(text, **kw): return "B2"
        blocks, fired = se.run_modules((("m1", b1), ("m2", b2)), "hi", label="T", shared_kwargs={})
        self.assertEqual(blocks, ["B1", "B2"])
        self.assertEqual(fired, ["m1", "m2"])

    def test_exception_does_not_stop_later_modules(self):
        def boom(text, **kw): raise RuntimeError("x")
        def ok(text, **kw): return "B"
        with self.assertLogs(se._log.name, level="WARNING") as cm:
            blocks, fired = se.run_modules(
                (("bad", boom), ("good", ok)), "hi", label="T", shared_kwargs={})
        self.assertEqual(blocks, ["B"])
        self.assertEqual(fired, ["good"])
        self.assertTrue(any("[T/bad] error: x" in line for line in cm.output))

    def test_max_blocks_counts_only_produced(self):
        def empty(text, **kw): return ""
        def ok(text, **kw): return "B"
        def later(text, **kw): return "C"
        blocks, fired = se.run_modules(
            (("e", empty), ("o", ok), ("l", later)), "hi",
            label="T", shared_kwargs={}, max_blocks=1)
        self.assertEqual(blocks, ["B"])
        self.assertEqual(fired, ["o"])

    def test_needs_text_skips_when_empty(self):
        def ok(text, **kw): return "B"
        blocks, fired = se.run_modules(
            (("m", ok),), "", label="T", shared_kwargs={}, needs_text=("m",))
        self.assertEqual(blocks, [])
        self.assertEqual(fired, [])

    def test_literal_copy_note_appended(self):
        def ok(text, **kw): return "B\n"
        blocks, _ = se.run_modules(
            (("m", ok),), "hi", label="T", shared_kwargs={}, literal_copy_note=True)
        self.assertEqual(blocks, [f"B\n{se.NO_LITERAL_COPY}"])

    def test_per_module_kwargs_merged(self):
        seen = {}
        def ok(text, **kw): seen.update(kw); return "B"
        se.run_modules((("m", ok),), "hi", label="T",
                       shared_kwargs={"session_id": "s"},
                       per_module_kwargs={"m": {"now_jst": 123}})
        self.assertEqual(seen, {"session_id": "s", "now_jst": 123})


class SessionStoreTests(unittest.TestCase):
    def test_mark_dedups_within_session(self):
        st = se.SessionStore()
        self.assertFalse(st.mark("s", "k"))
        self.assertTrue(st.mark("s", "k"))
        self.assertFalse(st.mark("s2", "k"))

    def test_has_is_read_only(self):
        st = se.SessionStore()
        self.assertFalse(st.has("s", "k"))
        st.mark("s", "k")
        self.assertTrue(st.has("s", "k"))
        self.assertFalse(st.has("s", "other"))
        self.assertEqual(len(st), 1, "has 不许新增桶")

    def test_reset(self):
        st = se.SessionStore()
        st.mark("s", "k")
        st.reset("s")
        self.assertFalse(st.mark("s", "k"))
        st.mark("a", "k")
        st.mark("b", "k")
        st.reset()
        self.assertEqual(len(st), 0)

    def test_lru_evicts_oldest_beyond_cap(self):
        st = se.SessionStore(max_sessions=2)
        st.mark("s1", "k")
        st.mark("s2", "k")
        st.mark("s3", "k")
        self.assertEqual(len(st), 2)
        self.assertTrue(st.mark("s2", "k"), "s2 不应被淘汰")
        self.assertFalse(st.mark("s1", "k"), "s1 应已被淘汰")

    def test_touch_refreshes_recency(self):
        st = se.SessionStore(max_sessions=2)
        st.mark("s1", "k")
        st.mark("s2", "k")
        st.mark("s1", "k")          # 触及 s1 → s2 变成最旧
        st.mark("s3", "k")
        self.assertTrue(st.mark("s1", "k"))
        self.assertFalse(st.mark("s2", "k"))


class ModuleLevelApiTests(unittest.TestCase):
    def setUp(self):
        se.reset_session()

    def test_mark_fired_shared_bucket_for_empty_session(self):
        self.assertFalse(se._mark_fired("", "k"))
        self.assertTrue(se._mark_fired(None, "k"), "空 session 应共享同一去重桶")
        se.reset_session("")
        self.assertFalse(se._mark_fired(None, "k"))

    def test_reset_session_none_clears_all(self):
        se._mark_fired("a", "k")
        se._mark_fired("b", "k")
        se.reset_session()
        self.assertFalse(se._mark_fired("a", "k"))


class AppendGeneralSceneBlocksTests(unittest.TestCase):
    def setUp(self):
        se.reset_session()

    def test_appends_for_known_char(self):
        blocks = []
        se.append_general_scene_blocks(blocks, "灯", "我一直在哭，快撑不住了",
                                       label="T", session_id="scaffold:g1")
        self.assertTrue(blocks and blocks[0], "通用场景层应命中 comfort")

    def test_failure_only_logs(self):
        blocks = []
        # 未知角色：helper 只记日志、不抛异常（单点故障不拖垮整轮装配）
        se.append_general_scene_blocks(blocks, "不存在角色", "我一直在哭，快撑不住了",
                                       label="T", session_id="scaffold:g2")


if __name__ == "__main__":
    unittest.main()
