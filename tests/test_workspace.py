"""契约测试：idiolect/workspace.py（上下文工作区蒸馏件）。

每条断言对应上下文工作区的真实行为或调校值，防止蒸馏过程中走样：
  · 12 层顺序与工作区装配的参数顺序一致；
  · 执行包只贴本轮那条 user（贴不到就报错，不静默丢）；
  · 预算裁剪整块摘除、从层序尾部开始、pinned 不动，配不出来时发警告；
  · 同一层两路材料合并（`replace=True` 才覆盖）；
  · 重叠分公式（bigram 1.65 / trigram 2.15，强弱边界 2.0）是审计调校值，不是拍脑袋。
"""
from __future__ import annotations

import unittest

from idiolect.assemble import build_system_prompt
from idiolect.workspace import (
    LAYER_ORDER, ContextWorkspace, FactRecord, build_workspace_messages,
    overlap_score, recency_score, select_facts, topic_tokens,
)


class TestLayerSkeleton(unittest.TestCase):
    def test_layer_order_matches_origin(self):
        self.assertEqual(LAYER_ORDER[0], "persona")
        self.assertEqual(LAYER_ORDER[-1], "recent_dialogue_guard")
        self.assertEqual(len(LAYER_ORDER), 12)
        # fact_workspace 在 memory_recall 前（装配参数顺序）
        self.assertLess(LAYER_ORDER.index("fact_workspace"),
                        LAYER_ORDER.index("memory_recall"))

    def test_empty_blocks_are_skipped(self):
        ws = ContextWorkspace()
        ws.add("persona", "人格", pinned=True)
        ws.add("current_state", "   ")
        ws.add("memory_recall", "")
        messages = ws.assemble()
        self.assertEqual([m["content"] for m in messages], ["人格"])

    def test_custom_layer_sorts_after_known_layers(self):
        ws = ContextWorkspace()
        ws.add("recent_dialogue_guard", "护栏")
        ws.add("my_plugin", "自定义")
        ws.add("persona", "人格", pinned=True)
        messages = ws.assemble()
        self.assertEqual([m["content"] for m in messages], ["人格", "护栏", "自定义"])

    def test_budget_trims_unpinned_from_tail_only(self):
        ws = ContextWorkspace()
        ws.add("persona", "人格" * 10, pinned=True)
        ws.add("current_state", "状态" * 10)
        ws.add("cognitive", "认知" * 10)
        total = 20 + 20 + 20
        messages = ws.assemble(max_chars=40)
        # cognitive（尾部）先被整块摘除；current_state 达标后停止
        self.assertEqual([m["content"] for m in messages], ["人格" * 10, "状态" * 10])
        # 预算小到连 persona 都装不下时，pinned 仍然保留（并给出警告，见下一条用例）
        with self.assertWarns(RuntimeWarning):
            messages = ws.assemble(max_chars=5)
        self.assertEqual([m["content"] for m in messages], ["人格" * 10])
        self.assertEqual(total, 60)

    def test_budget_warns_when_pinned_layers_exceed_it(self):
        """pinned 层自己就超预算时不许静默超发。

        2026-09-13 实测：旧实现返回 500 字、不报错也不提示，调用方只会看到
        「预算设了没用」，查不出原因。
        """
        ws = ContextWorkspace()
        ws.add("persona", "人格" * 10, pinned=True)
        with self.assertWarns(RuntimeWarning) as ctx:
            ws.assemble(max_chars=5)
        self.assertIn("配不出来", str(ctx.warning))

    def test_no_warning_when_budget_is_met(self):
        import warnings as _w

        ws = ContextWorkspace()
        ws.add("persona", "人格", pinned=True)
        ws.add("cognitive", "认知")
        with _w.catch_warnings():
            _w.simplefilter("error")          # 达标时连警告都不该有
            ws.assemble(max_chars=100)

    def test_same_key_merges_instead_of_overwriting(self):
        """同一层两路材料都挂进来时要合并，不能静默丢先到的那份。

        2026-09-13 实测：旧实现直接覆盖，而且第二次不带 pinned 时连 pin 一起丢。
        """
        ws = ContextWorkspace()
        ws.add("memory_recall", "第一路召回", pinned=True)
        ws.add("memory_recall", "第二路召回")
        messages = ws.assemble()
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["content"], "第一路召回\n\n第二路召回")
        self.assertTrue(ws._blocks["memory_recall"].pinned, "pin 被第二次 add 弄丢了")

    def test_replace_flag_overwrites(self):
        ws = ContextWorkspace()
        ws.add("memory_recall", "旧")
        ws.add("memory_recall", "新", replace=True)
        self.assertEqual([m["content"] for m in ws.assemble()], ["新"])


class TestExecutionPacket(unittest.TestCase):
    def test_packet_appended_to_last_history_user(self):
        """assemble() 自己贴时，贴的是它已有的最后一条 user（即历史的上一轮）。"""
        ws = ContextWorkspace()
        ws.add("persona", "人格", pinned=True)
        history = [
            {"role": "user", "content": "第一句"},
            {"role": "assistant", "content": "回复"},
            {"role": "user", "content": "第二句"},
        ]
        messages = ws.assemble(history=history, execution_packet="【执行】≤19 字")
        self.assertEqual(messages[-1]["content"], "第二句\n\n【执行】≤19 字")
        self.assertEqual(messages[1]["content"], "第一句")  # 前面的 user 不受影响

    def test_packet_without_user_raises(self):
        """没有可贴的 user 时必须报错，不能静默丢弃执行指令。

        2026-09-13 实测过：旧实现直接 `break` 掉，产物里根本没有这段文本，
        表现成「模型不遵守长度预算」，从产物上查不出原因。
        """
        ws = ContextWorkspace()
        ws.add("persona", "人格", pinned=True)
        with self.assertRaises(ValueError) as ctx:
            ws.assemble(execution_packet="【执行】≤19 字")
        self.assertIn("execution_packet", str(ctx.exception))

    def test_packet_with_only_assistant_history_raises(self):
        ws = ContextWorkspace()
        ws.add("persona", "人格", pinned=True)
        with self.assertRaises(ValueError):
            ws.assemble(history=[{"role": "assistant", "content": "回复"}],
                        execution_packet="【执行】≤19 字")

    def test_no_packet_is_fine_without_user(self):
        ws = ContextWorkspace()
        ws.add("persona", "人格", pinned=True)
        messages = ws.assemble()
        self.assertEqual(len(messages), 1)


class TestBuildWorkspaceMessages(unittest.TestCase):
    def test_persona_is_four_layer_prompt(self):
        # include_turn_logic=False：turn_logic 有 per-session 渲染变体（既有契约），
        # 这里只断言「persona 位放的是四层装配结果」这一件事。
        user_text = "你今天又想去哪找猫"
        messages = build_workspace_messages(
            "乐奈", user_text, include_turn_logic=False,
            blocks=[("current_state", "乐奈在 RiNG")], history=[{"role": "user", "content": "之前"}])
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[0]["content"],
                         build_system_prompt("乐奈", user_text, include_turn_logic=False))
        self.assertEqual(messages[1]["content"], "乐奈在 RiNG")
        self.assertEqual(messages[-1], {"role": "user", "content": user_text})

    def test_external_block_cannot_take_persona_slot(self):
        messages = build_workspace_messages(
            "乐奈", "找猫", blocks=[("persona", "冒牌人格")])
        self.assertNotIn("冒牌人格", [m["content"] for m in messages])

    def test_execution_packet_lands_on_this_turn(self):
        """执行包必须贴在本轮 user 上（最后一条），不是历史的上一轮。

        2026-09-13 这是文档与实现的一次真分歧：docs/08 与 README 都写「贴最后一条
        user、离生成端最近」，而实现把它贴到历史那条，本轮 user 之后才 append。
        """
        messages = build_workspace_messages(
            "乐奈", "你今天又想去哪找猫", include_turn_logic=False,
            history=[{"role": "user", "content": "在干嘛"},
                     {"role": "assistant", "content": "练习。"}],
            execution_packet="【本轮执行】回复 ≤19 字")
        self.assertEqual(messages[-1]["role"], "user")
        self.assertTrue(messages[-1]["content"].startswith("你今天又想去哪找猫"))
        self.assertTrue(messages[-1]["content"].endswith("【本轮执行】回复 ≤19 字"))
        self.assertEqual(messages[-3]["content"], "在干嘛")  # 历史的 user 不被污染

    def test_execution_packet_survives_without_history(self):
        """没有 history 时也不能丢——这是旧版最坑的一条（静默丢包）。"""
        messages = build_workspace_messages(
            "乐奈", "找猫", include_turn_logic=False,
            execution_packet="【本轮执行】≤19 字")
        self.assertIn("【本轮执行】≤19 字", messages[-1]["content"])
        self.assertEqual(messages[-1]["role"], "user")


class TestFactSelector(unittest.TestCase):
    def test_stop_tokens_are_not_topic_evidence(self):
        tokens = topic_tokens("今天现在明天")
        self.assertFalse(tokens & {"今天", "现在", "明天"})

    def test_overlap_formula_anchor_values(self):
        # 单个共享 bigram：min(4,2)/2 + 1×0.65 = 1.65（弱档，< 2.0 阈值）
        self.assertAlmostEqual(overlap_score({"池袋"}, "池袋"), 1.65)
        # 单个共享 trigram：min(4,3)/2 + 0.65 = 2.15（强档，≥ 2.0）
        self.assertAlmostEqual(overlap_score({"见面地"}, "见面地"), 2.15)
        self.assertEqual(overlap_score(set(), "任何文本"), 0.0)

    def test_recency_bands(self):
        hour = 60 * 60 * 1000
        newest = 100 * 24 * hour
        self.assertEqual(recency_score(newest, newest), 2.5)
        self.assertEqual(recency_score(newest, newest - 3 * hour), 2.0)
        self.assertEqual(recency_score(newest, newest - 20 * hour), 1.5)
        self.assertEqual(recency_score(newest, newest - 50 * hour), 1.0)
        self.assertEqual(recency_score(newest, newest - 200 * hour), 0.5)
        self.assertEqual(recency_score(newest, newest - 400 * hour), 0.1)
        self.assertEqual(recency_score(0, newest), 0.0)

    def test_zero_overlap_is_dropped(self):
        selected = select_facts("猫去哪了", [FactRecord("立希今天打工到六点")])
        self.assertEqual(selected, [])

    def test_weak_overlap_gets_no_kind_channel_bonus(self):
        # 共享一个 bigram（弱档）：只有 overlap + recency，不给 kind/channel 加权
        selected = select_facts("池袋的猫", [
            FactRecord("池袋", kind="correction", channel="schedule_recall"),
        ])
        self.assertEqual(len(selected), 1)
        self.assertAlmostEqual(selected[0]["score"], 1.65)

    def test_strong_overlap_ranks_correction_first(self):
        selected = select_facts("见面地点在哪", [
            FactRecord("见面地点是 RiNG", kind="fact"),
            FactRecord("见面地点改成车站了", kind="correction"),
        ])
        self.assertEqual(selected[0]["kind"], "correction")
        self.assertGreater(selected[0]["score"], selected[1]["score"])

    def test_dedup_and_budgets(self):
        records = [FactRecord("见面地点是 RiNG")] * 3
        self.assertEqual(len(select_facts("见面地点", records)), 1)
        many = [FactRecord(f"见面地点是 RiNG 之{i}") for i in range(5)]
        self.assertEqual(len(select_facts("见面地点", many, max_records=2)), 2)
        long_one = [FactRecord("见面地点是 RiNG " + "长" * 100), FactRecord("见面地点在车站")]
        selected = select_facts("见面地点", long_one, max_chars=30)
        self.assertEqual([row["text"] for row in selected], ["见面地点在车站"])


if __name__ == "__main__":
    unittest.main()
