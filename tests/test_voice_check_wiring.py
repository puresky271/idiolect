"""voice_check 接线的契约测试（2026-09-12 接线时先写）。

钉住的约束：
  · tomori / taki / anon 的 `post_reply_voice_check` 真正调用各自 voice_check 包的
    `clean_reply`（不再是永远 skipped 的 stub）；
  · 清洗是**确定性的**：同一输入两次调用产出同一文本（随机步骤按输入定种）；
  · env 总开关 `<CHAR>_VOICE_CHECK_ENABLED` 命中统一假值表时整体回退为透传；
  · 非本角色 / 未知角色一律透传且不报错；
  · 返回契约：`text` 永远在、`violations` 是 dict（与 soyo/rana 对齐）。
"""
import os
import unittest
from unittest import mock

from idiolect.registry import postprocess_reply


class TakiWiringTests(unittest.TestCase):
    """立希：只删不换的确定性清洗（用例取自 taki.voice_check 自测）。"""

    def test_exact_cleanups(self):
        cases = [
            ("行呀。", "行。"),                       # 句末撒娇词
            ("嗯嗯，知道了", "知道了"),               # 句首软回应
            ("好啊♪", "好啊"),                       # 装饰符号
            ("好啊！！！", "好啊！"),                 # 多重感叹减到 1
        ]
        for raw, want in cases:
            with self.subTest(raw=raw):
                got = postprocess_reply("立希", raw)
                self.assertEqual(got["text"], want)
                self.assertIsInstance(got["violations"], dict)
                self.assertTrue(got["violations"], "清洗过就必须记 violations")

    def test_canonical_reply_untouched(self):
        for raw in ("哈？又不是没做过。", "那家伙、又没吃饭吧。", "······挺好的。"):
            with self.subTest(raw=raw):
                got = postprocess_reply("立希", raw)
                self.assertEqual(got["text"], raw)
                self.assertTrue(got["ok"])


class TomoriWiringTests(unittest.TestCase):
    """灯：省略号归一 / 呀啊清洗 / 随机步骤定种。"""

    def test_ascii_ellipsis_normalized(self):
        got = postprocess_reply("灯", "等我...")
        self.assertEqual(got["text"], "等我······")

    def test_ya_a_enumeration_stripped(self):
        got = postprocess_reply("灯", "石头呀、树叶啊")
        self.assertIn("石头、树叶", got["text"])
        self.assertNotIn("呀", got["text"])
        self.assertNotIn("啊", got["text"])

    def test_deterministic_per_input(self):
        raw = "我想写歌词，但是写不出来。今天也在想。嗯。"
        first = postprocess_reply("灯", raw)["text"]
        second = postprocess_reply("灯", raw)["text"]
        self.assertEqual(first, second, "同一输入两次清洗必须同输出（随机步骤定种）")

    def test_different_inputs_may_differ(self):
        # 定种是按文本的：两条标点结构相同的文本不应共享同一份随机选择
        a = postprocess_reply("灯", "今天的云，看起来像石头。嗯。")["text"]
        b = postprocess_reply("灯", "昨天捡到的石头，圆圆的。啊。")["text"]
        self.assertTrue(a and b)  # 两条都正常产出即可（不强制不同，防脆弱断言）


class AnonWiringTests(unittest.TestCase):
    """爱音：mood gate 装饰 + 永远跑的省略号归一。"""

    def test_ascii_ellipsis_normalized(self):
        got = postprocess_reply("爱音", "嗯...")
        self.assertEqual(got["text"], "嗯······")

    def test_deterministic_per_input(self):
        raw = "真的吗，这也太可爱了吧？我也想去"
        first = postprocess_reply("爱音", raw)["text"]
        second = postprocess_reply("爱音", raw)["text"]
        self.assertEqual(first, second)

    def test_reply_not_blank_after_decoration(self):
        got = postprocess_reply("爱音", "好啊，一起去看吧")
        self.assertTrue(got["text"].strip())
        self.assertIn("一起去看吧", got["text"], "装饰类清洗不许删掉正文内容")


class KillSwitchTests(unittest.TestCase):
    """env 总开关：命中统一假值表（含 off/no）时透传。"""

    CASES = [
        ("TOMORI_VOICE_CHECK_ENABLED", "灯", "等我..."),
        ("TAKI_VOICE_CHECK_ENABLED", "立希", "行呀。"),
        ("ANON_VOICE_CHECK_ENABLED", "爱音", "嗯..."),
    ]

    def test_off_disables_cleaning(self):
        for env, char, raw in self.CASES:
            for value in ("0", "off", "no", "false"):
                with self.subTest(env=env, value=value):
                    with mock.patch.dict(os.environ, {env: value}):
                        got = postprocess_reply(char, raw)
                    self.assertEqual(got["text"], raw, f"{env}={value} 时必须透传")


class PassthroughContractTests(unittest.TestCase):
    def test_unknown_character_passthrough(self):
        got = postprocess_reply("不存在的人", "行呀。")
        self.assertEqual(got["text"], "行呀。")
        self.assertTrue(got.get("skipped"))

    def test_wrong_character_passthrough(self):
        got = postprocess_reply("素世", "行呀。")
        self.assertEqual(got["text"], "行呀。", "立希的清洗不许落到素世头上")

    def test_text_key_always_present(self):
        for char in ("爱音", "灯", "立希", "素世", "乐奈"):
            with self.subTest(char=char):
                got = postprocess_reply(char, "嗯。")
                self.assertIn("text", got)
                self.assertIsInstance(got["violations"], dict)


if __name__ == "__main__":
    unittest.main()
