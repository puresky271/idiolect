"""契约测试：idiolect/workspace.py（上下文工作区蒸馏件）。

每条断言对应上下文工作区的真实行为或调校值，防止蒸馏过程中走样：
  · 12 层顺序与工作区装配的参数顺序一致；
  · 执行包只贴最后一条 user（没有 user 就不贴，不另起块）；
  · 预算裁剪整块摘除、从层序尾部开始、pinned 不动；
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
        # 预算小到连 persona 都装不下时，pinned 仍然保留
        messages = ws.assemble(max_chars=5)
        self.assertEqual([m["content"] for m in messages], ["人格" * 10])
        self.assertEqual(total, 60)


class TestExecutionPacket(unittest.TestCase):
    def test_packet_appended_to_last_user(self):
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

    def test_packet_dropped_without_user(self):
        ws = ContextWorkspace()
        ws.add("persona", "人格", pinned=True)
        messages = ws.assemble(execution_packet="【执行】≤19 字")
        self.assertEqual(len(messages), 1)
        self.assertNotIn("【执行】", messages[0]["content"])


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
