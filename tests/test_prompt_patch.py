"""prompt_patch 补丁框架的契约测试（2026-09-13 评审 C1 后补）。

钉住的约束：
  · find_persona_end 在发布版四层装配上必须返回**行首**的 style_target 层边界——
    旧锚点串「【所有角色共用·反客服腔硬约束】」在发布版 prompt 里只出现在一句
    交叉引用内部，返回句子中间的偏移，A/B 补丁会把句子腰斩；
  · 没有 style_target 层的 system（空占位夹具 / 外部 dump）必须显式报错，
    不许静默退化成「追加到末尾」（那会把被测块甩出 persona card）；
  · apply_patch 之后，插入点之后的原文逐字节保留（两臂差异只来自被测块）；
  · live_persona 重建的 persona card 与生产装配逐字节等价（canon + voice 同源）。
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT, ROOT / "tools" / "probe"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import prompt_patch as pp  # noqa: E402
from idiolect.assemble import build_system_prompt  # noqa: E402

CHARS = [("爱音", "anon"), ("灯", "tomori"), ("立希", "taki"),
         ("素世", "soyo"), ("乐奈", "rana")]


class FindPersonaEndTests(unittest.TestCase):
    def test_returns_line_start_of_style_target_layer(self):
        for cn, _ in CHARS:
            with self.subTest(char=cn):
                system = build_system_prompt(cn, "在干嘛")
                i = pp.find_persona_end(system)
                self.assertGreaterEqual(i, 0)
                self.assertTrue(system[i:].startswith(pp.PERSONA_END_MARK),
                                f"{cn}: 返回的不是 style_target 层边界")
                self.assertTrue(i == 0 or system[i - 1] == "\n",
                                f"{cn}: 返回的是句子中间的偏移，不是行首")

    def test_turn_logic_variants_still_land_on_boundary(self):
        # turn_logic 层在 style_target 之后，命中与否不影响 persona card 边界
        for cn, _ in CHARS:
            with self.subTest(char=cn):
                system = build_system_prompt(cn, "我今天被老师骂了", session_id="t:pp")
                i = pp.find_persona_end(system)
                self.assertTrue(system[i:].startswith(pp.PERSONA_END_MARK))
                self.assertTrue(system[i - 1] == "\n")

    def test_missing_boundary_raises(self):
        with self.assertRaises(SystemExit):
            pp.find_persona_end("完全没有层边界的一段普通文本")
        with self.assertRaises(SystemExit):
            pp.find_persona_end("")


class ApplyPatchTests(unittest.TestCase):
    def test_patch_preserves_tail_byte_for_byte(self):
        for cn, key in CHARS:
            with self.subTest(char=cn):
                system = build_system_prompt(cn, "我今天被老师骂了")
                i = pp.find_persona_end(system)
                out = pp.apply_patch(system, key, "targets_cap", pp.load_targets("cn"))
                self.assertTrue(out.endswith(system[i:]),
                                f"{cn}: 插入点之后的原文被改动——两臂差异不再只来自被测块")
                head = out[: len(out) - len(system[i:])]
                self.assertIn("【实测台词基线", head, f"{cn}: 被测块没有出现在 persona card 末尾")

    def test_patch_sits_directly_before_style_target_layer(self):
        system = build_system_prompt("乐奈", "我今天被老师骂了")
        out = pp.apply_patch(system, "rana", "targets_cap", pp.load_targets("cn"))
        # 旧 bug 的指纹是「……另见\n\n【实测台词基线·…」：块插进句子中间
        self.assertNotIn("另见\n\n【实测台词基线", out)
        self.assertIn("就停在那里**。\n\n【说话尺度·乐奈】", out,
                      "被测块应紧贴 style_target 层边界，而不是插进 voice 层内部")

    def test_live_persona_rebuild_matches_assembly_byte_for_byte(self):
        # drop_rana_register=False 时重建 card = canon + voice，应与生产装配完全一致
        for cn, key in CHARS:
            with self.subTest(char=cn):
                system = build_system_prompt(cn, "我今天被老师骂了")
                out = pp.apply_patch(system, key, "live_persona", pp.load_targets("cn"))
                self.assertEqual(out, system, f"{cn}: live_persona 重建结果与装配不一致")

    def test_live_persona_no_rana_reg_only_affects_rana(self):
        for cn, key in CHARS:
            with self.subTest(char=cn):
                system = build_system_prompt(cn, "我今天被老师骂了")
                out = pp.apply_patch(system, key, "live_persona_no_rana_reg", pp.load_targets("cn"))
                if key == "rana":
                    self.assertNotIn("【句式结构·这是你最大的辨识点】", out)
                    self.assertIn("【常用物件与话题】", out, "剔除范围溢出：句式块之后的节被误删")
                else:
                    self.assertEqual(out, system, f"{cn}: 非乐奈不应被剔除任何块")


if __name__ == "__main__":
    unittest.main()
