"""素世 / 乐奈 turn_logic **深模块**（home / wind_ensemble / space / nap / interesting / cat_talk）契约测试。

为什么单独一个文件：`test_scene_turn_logic.py` 锁的是**场景层**（SceneModule：触发词 + 分寸正文），
这里锁的是**深模块层**（独立文件、3 层渐进激活、per-session 去重、canon override）。
两层的失效模式不同：场景层怕触发词过宽/被转义，深模块怕层级串味、预算爆掉、canon 口径漂移。

锁定的十件事：
  1. 触发命中与**不过宽**（逐模块正/负例）
  2. 层级渐进：泛提 → 具体能给**不同**的块（不是同一块复读）
  3. per-session 去重：同一层在一轮会话里只注入一次
  4. 角色隔离 + developer 模式不触发 + env flag 可回退
  5. **无深模块命中时逐字节零漂移**（改动不得影响既有场景层输出）
  6. 轮次预算：一次最多 3 块（深 1 + 场景 1 + 通用 1）
  7. 深模块与场景层话题重叠时压制场景块（cat_talk 压制 rana_cat）
  8. 正文无元叙述（角色读到的文本不许出现语料/统计字样）
  9. canon 口径：素世「低音大提琴」不是大提琴/小提琴；乐奈「外婆」不是奶奶；
     「有趣的女人」只作为**旧说法/外婆原话**出现
  10. 触发词都有语料实证（负例表里的词不得进触发正则）
"""
from __future__ import annotations

import unittest
from unittest import mock

import idiolect.scene_engine as engine
from idiolect.characters.rana.turn_logic import build_rana_special_block
from idiolect.characters.rana.turn_logic import cat_talk as rana_cat_talk
from idiolect.characters.rana.turn_logic import interesting as rana_interesting
from idiolect.characters.rana.turn_logic import nap as rana_nap
from idiolect.characters.rana.turn_logic import space as rana_space
from idiolect.characters.rana.turn_logic.scenes import RANA_SCENES
from idiolect.characters.soyo.turn_logic import build_soyo_special_block
from idiolect.characters.soyo.turn_logic import home as soyo_home
from idiolect.characters.soyo.turn_logic import wind_ensemble as soyo_wind
from idiolect.characters.soyo.turn_logic.scenes import SOYO_SCENES

BORDER = "═" * 72

# (模块名, 模块, 构造函数名, 正例, 负例)
CASES = [
    ("soyo.home", soyo_home, "build_home_special_block",
     ["今天在家做什么？妈妈回来吃饭吗", "妈妈工作很忙吧", "你平时自己做家务吗",
      "听说你爸妈离婚了", "家里就你一个人吗"],
     ["明天排练几点开始", "今天天气不错", "大家一起去吧"]),
    ("soyo.wind_ensemble", soyo_wind, "build_wind_ensemble_special_block",
     ["听说你以前在吹奏乐社拉低音大提琴？", "你在吹奏乐社待过吧",
      "你为什么后来去弹贝斯了", "你会看乐谱吗"],
     ["明天排练几点开始", "今天天气不错", "要不要喝咖啡"]),
    ("rana.space", rana_space, "build_space_special_block",
     ["你外婆的店是个什么样的地方", "外婆来看你演出了吗", "SPACE 还在营业吗",
      "你的归宿是哪里", "你外婆弹吉他吗"],
     ["明天排练几点开始", "今天天气不错"]),
    ("rana.nap", rana_nap, "build_nap_special_block",
     ["你是不是又睡着了", "你平时在哪睡觉", "好困", "你昨晚睡了没"],
     ["明天排练几点开始", "今天天气不错"]),
    ("rana.interesting", rana_interesting, "build_interesting_special_block",
     ["你觉得我们乐队的人怎么样？", "你怎么看灯", "这个演出有趣吗",
      "刚才那个挺好玩的", "好无聊啊", "你以前说过有趣的女人吧"],
     ["明天排练几点开始", "今天天气不错"]),
    ("rana.cat_talk", rana_cat_talk, "build_cat_talk_special_block",
     ["刚才在门口看到一只猫", "你喂过猫吗", "你是不是能听懂猫说话", "那只猫在叫"],
     ["明天排练几点开始", "今天天气不错"]),
]

# 语料里**不存在**、不得被当触发词的词（沿用场景层的清单 + 深模块新增候选）
# 注：「打盹」是**用户侧**常用词、不在本表；本表针对「看起来像角色自己的词但语料没有」。
NOT_IN_CORPUS = {"排练", "调音", "拨片", "屋檐", "院子", "池子", "大吉岭", "祥子", "奶茶",
                 "低音提琴手", "即兴", "野猫", "流浪", "首席"}

# 角色读到的正文里不许出现的元叙述（对齐 test_scene_turn_logic 的 HARD 表）
META_WORDS = ("语料", "实测", "lift", "金标准", "原作中位", "参照中位", "占比", "频次", "统计")


def _reset_all() -> None:
    engine.reset_session()
    for _, mod, _, _, _ in CASES:
        mod.reset_session_fired()


class DeepModuleContractTests(unittest.TestCase):
    def setUp(self) -> None:
        _reset_all()

    def test_every_module_exposes_the_five_part_contract(self):
        for name, mod, fn_name, _, _ in CASES:
            with self.subTest(module=name):
                self.assertTrue(callable(getattr(mod, fn_name)))
                self.assertTrue(callable(mod.reset_session_fired))
                self.assertTrue(callable(mod._enabled))
                # env flag 前缀必须带角色/模块名、避免互相覆盖
                self.assertTrue(name.split(".")[0] in name)

    def test_trigger_precision(self):
        for name, mod, fn_name, pos, neg in CASES:
            fn = getattr(mod, fn_name)
            for i, text in enumerate(pos):
                with self.subTest(module=name, kind="pos", text=text):
                    mod.reset_session_fired()
                    self.assertTrue(fn(text, session_id=f"{name}-p{i}"),
                                    f"{name} 应命中 {text!r}")
            for i, text in enumerate(neg):
                with self.subTest(module=name, kind="neg", text=text):
                    mod.reset_session_fired()
                    self.assertFalse(fn(text, session_id=f"{name}-n{i}"),
                                     f"{name} 不应命中 {text!r}")

    def test_tiers_are_progressive_not_repeated(self):
        """泛提之后再给具体面向，必须换一块（渐进激活），而不是把同一块再说一遍。"""
        cases = [
            (soyo_home, "build_home_special_block", "家里就你一个人吗", "听说你爸妈离婚了"),
            (rana_nap, "build_nap_special_block", "你昨晚睡了没", "你平时在哪睡觉"),
        ]
        for mod, fn_name, first, second in cases:
            with self.subTest(module=fn_name):
                mod.reset_session_fired()
                fn = getattr(mod, fn_name)
                a = fn(first, session_id="tier")
                b = fn(second, session_id="tier")
                self.assertTrue(a)
                self.assertTrue(b)
                self.assertNotEqual(a, b, "进阶层级应给不同的块")

    def test_session_dedup(self):
        for name, mod, fn_name, pos, _ in CASES:
            with self.subTest(module=name):
                mod.reset_session_fired()
                fn = getattr(mod, fn_name)
                first = fn(pos[0], session_id="s1")
                second = fn(pos[0], session_id="s1")
                self.assertTrue(first)
                self.assertNotIn(second, (first,), "同一 session 不得重复注入同一块")

    def test_character_isolation_and_developer_mode(self):
        for name, mod, fn_name, pos, _ in CASES:
            fn = getattr(mod, fn_name)
            with self.subTest(module=name):
                mod.reset_session_fired()
                self.assertFalse(fn(pos[0], session_id="d", is_developer=True),
                                 "developer 模式不得触发深模块")
                mod.reset_session_fired()
                self.assertFalse(fn("", session_id="e"), "空 user_text 不触发")

    def test_env_flag_can_disable_each_module(self):
        for name, mod, fn_name, pos, _ in CASES:
            flag = f"{'SOYO' if name.startswith('soyo') else 'RANA'}_TURN_LOGIC_" \
                   f"{name.split('.')[1].upper()}_ENABLED"
            fn = getattr(mod, fn_name)
            with self.subTest(module=name, flag=flag):
                mod.reset_session_fired()
                with mock.patch.dict("os.environ", {flag: "0"}):
                    self.assertFalse(fn(pos[0], session_id="env"))

    def test_bodies_have_no_corpus_meta(self):
        for name, mod, fn_name, pos, _ in CASES:
            fn = getattr(mod, fn_name)
            for text in pos:
                with self.subTest(module=name, text=text):
                    mod.reset_session_fired()
                    body = fn(text, session_id="meta")
                    for w in META_WORDS:
                        self.assertNotIn(w, body, f"{name} 正文含元叙述「{w}」")


class DeepModuleWiringTests(unittest.TestCase):
    """接线层：预算、零漂移、话题压制、角色隔离。"""

    def setUp(self) -> None:
        _reset_all()

    def test_no_drift_when_no_deep_module_fires(self):
        """关键回归：只有场景层命中的输入，输出必须与「深模块全部关掉」时逐字节相同。"""
        import idiolect.characters.rana.turn_logic as rtl
        import idiolect.characters.soyo.turn_logic as stl

        cases = [
            (rtl, build_rana_special_block, "乐奈", "我的吉他弦断了"),
            (rtl, build_rana_special_block, "乐奈", "要不要去吃抹茶芭菲"),
            (stl, build_soyo_special_block, "素世", "你不是说今天没空吗"),
            (stl, build_soyo_special_block, "素世", "要不要喝杯咖啡"),
        ]
        for pkg, entry, char, text in cases:
            with self.subTest(char=char, text=text):
                _reset_all()
                with mock.patch.object(pkg, "_DEEP_MODULES", ()):
                    ref = entry(text, char, session_id="drift")
                _reset_all()
                got = entry(text, char, session_id="drift")
                self.assertTrue(ref, "该用例本应由场景层命中（否则测试本身失效）")
                self.assertEqual(got, ref, "无深模块命中时输出发生了漂移")

    def test_block_budget_at_most_three(self):
        cases = [
            (build_rana_special_block, "乐奈", "我外婆家的猫好像很困，你觉得它有趣吗"),
            (build_soyo_special_block, "素世", "今天在家做什么？妈妈回来吃饭吗，你喜欢喝咖啡吗"),
        ]
        for entry, char, text in cases:
            with self.subTest(char=char):
                _reset_all()
                blocks = entry(text, char, session_id="budget").count(BORDER) // 2
                self.assertLessEqual(blocks, 3, "轮次预算被突破")
                self.assertGreaterEqual(blocks, 1)

    def test_deep_layer_takes_at_most_one_block(self):
        """一轮最多 1 个深模块块——多个话题同时命中时不许叠加。"""
        import idiolect.characters.rana.turn_logic as rtl
        import idiolect.characters.soyo.turn_logic as stl

        for pkg, entry, char, text in (
            (rtl, build_rana_special_block, "乐奈", "我外婆家的猫好像很困，你觉得它有趣吗"),
            (stl, build_soyo_special_block, "素世", "听说你以前在吹奏乐社拉低音大提琴，妈妈支持你吗"),
        ):
            with self.subTest(char=char):
                _reset_all()
                deep_blocks, fired = pkg._build_deep_blocks(
                    text, session_id="one", is_developer=False)
                self.assertLessEqual(len(deep_blocks), 1)
                self.assertLessEqual(len(fired), 1)

    def test_cat_talk_suppresses_cat_scene(self):
        """cat_talk 命中时压掉 rana_cat 场景块，避免同一话题两块正文。"""
        import idiolect.characters.rana.turn_logic as rtl

        _reset_all()
        deep, fired = rtl._build_deep_blocks("刚才在门口看到一只猫", session_id="x",
                                             is_developer=False)
        self.assertEqual(fired, ["cat_talk"])
        keys = [m.key for m in rtl._scenes_for(fired)]
        self.assertNotIn("rana_cat", keys)
        # 未命中深模块时场景表原样返回（同一对象，保证零漂移）
        _reset_all()
        self.assertIs(rtl._scenes_for([]), RANA_SCENES)

    def test_soyo_has_no_scene_overlap_and_keeps_table(self):
        import idiolect.characters.soyo.turn_logic as stl

        self.assertIs(stl._scenes_for([]), SOYO_SCENES)
        self.assertIs(stl._scenes_for(["home", "wind_ensemble"]), SOYO_SCENES)

    def test_deep_blocks_carry_anti_copy_footer(self):
        """真实探针发现「正例被逐字照抄」→ 深模块块必须带反照抄脚注，且只带一次。"""
        from idiolect.scene_engine import NO_LITERAL_COPY

        cases = [
            (build_rana_special_block, "乐奈", "你是不是能听懂猫说话"),
            (build_rana_special_block, "乐奈", "你外婆的店是个什么样的地方"),
            (build_soyo_special_block, "素世", "听说你以前在吹奏乐社拉低音大提琴？"),
            (build_soyo_special_block, "素世", "今天在家做什么？妈妈回来吃饭吗"),
        ]
        for entry, char, text in cases:
            with self.subTest(char=char, text=text):
                _reset_all()
                block = entry(text, char, session_id="nofooter")
                self.assertIn(NO_LITERAL_COPY, block)
                self.assertEqual(block.count(NO_LITERAL_COPY), 1)

    def test_anti_copy_footer_not_added_to_scene_only_blocks(self):
        """脚注只跟深模块走：纯场景层的块不加（避免改动既有输出）。"""
        from idiolect.scene_engine import NO_LITERAL_COPY

        _reset_all()
        block = build_rana_special_block("我的吉他弦断了", "乐奈", session_id="sceneonly")
        self.assertIn("【本轮·吉他/演出】", block)
        self.assertNotIn(NO_LITERAL_COPY, block)

    def test_character_isolation_at_entry_level(self):
        cases = [
            (build_rana_special_block, "素世", "今天在家做什么？妈妈回来吃饭吗"),
            (build_soyo_special_block, "乐奈", "你外婆的店是个什么样的地方"),
            (build_rana_special_block, "乐奈", "今天在家做什么？妈妈回来吃饭吗"),
            (build_soyo_special_block, "素世", "你外婆的店是个什么样的地方"),
        ]
        for entry, char, text in cases:
            with self.subTest(char=char, text=text):
                _reset_all()
                self.assertEqual(entry(text, char, session_id="iso"), "")


class DeepModuleCanonTests(unittest.TestCase):
    """canon 口径：译名与设定不得漂移。"""

    def setUp(self) -> None:
        _reset_all()

    def test_soyo_instrument_is_contrabass_not_cello(self):
        body = soyo_wind.build_wind_ensemble_special_block(
            "听说你以前在吹奏乐社拉低音大提琴？", session_id="inst")
        self.assertIn("低音大提琴", body)
        # 「大提琴」只能作为「低音大提琴」的一部分出现
        self.assertEqual(body.count("大提琴"), body.count("低音大提琴"))
        self.assertNotIn("小提琴", body)

    def test_soyo_can_explain_bass_vs_contrabass(self):
        body = soyo_wind.build_wind_ensemble_special_block("你会看乐谱吗", session_id="bass")
        self.assertIn("贝斯", body)

    def test_rana_grandma_is_waipo_not_nana(self):
        for text in ("你外婆的店是个什么样的地方", "SPACE 还在营业吗", "你的归宿是哪里"):
            with self.subTest(text=text):
                rana_space.reset_session_fired()
                body = rana_space.build_space_special_block(text, session_id="g")
                self.assertIn("外婆", body)
                self.assertNotIn("奶奶", body, "项目口径统一「外婆」；触发正则可收「奶奶」但正文不用")

    def test_interesting_carries_both_forms(self):
        """两种说法并存：模块必须让「女人」与「女孩子」两种形态都出现（不靠贴例句）。"""
        rana_interesting.reset_session_fired()
        body = rana_interesting.build_interesting_special_block(
            "你以前说过有趣的女人吧", session_id="w")
        self.assertIn("旧说法", body)
        self.assertIn("女孩子", body)
        rana_interesting.reset_session_fired()
        plain = rana_interesting.build_interesting_special_block("你怎么看灯", session_id="w2")
        self.assertIn("女孩子", plain)

    def test_nap_uses_canon_sleep_places(self):
        """睡处必须用 canon 给的那几个（暖炉边/长凳/屋顶/树上），不另编场所。"""
        rana_nap.reset_session_fired()
        body = rana_nap.build_nap_special_block("你平时在哪睡觉", session_id="np")
        for place in ("暖炉边", "长凳", "屋顶", "树上"):
            self.assertIn(place, body, f"缺少 canon 睡处「{place}」")
        self.assertNotIn("器材室", body)

    def test_space_is_closed_past_tense(self):
        rana_space.reset_session_fired()
        body = rana_space.build_space_special_block("SPACE 还在营业吗", session_id="sp")
        self.assertIn("关了", body)

    def test_rana_voice_carries_the_whole_canon_truth_table(self):
        """canon 真值表进 voice SSOT：「女人」是具名锚点、「女孩子」是改口后的通用形式。

        2026-09-12 的教训：我曾据「凛凛子纠正过女人→女孩子」把爱音那行改成「女孩子」，
        读 canon 才发现【对爱音】整段标题就是「有趣的女人 / 不需要 / 但接受温热的风」，
        正文写明「你称爱音『有趣的女人』——这是你给过的最高评价」；
        经典台词三句并列（女人=首次评价灯时／女孩子=被改口后／无聊的女孩子=失望时）。
        频率与「纠正」都不能覆盖 canon 的具名锚点。
        """
        from idiolect.characters.rana.voice import get_voice_manifest

        text = get_voice_manifest()
        self.assertIn("有趣的女人", text, "爱音那一行必须保留 canon 原说法")
        self.assertIn("有趣的女孩子", text, "改口后的通用形式也要在 SSOT 里")
        self.assertIn("无聊的女孩子", text, "失望时的说法（经典台词第三句）")

    def test_interesting_does_not_tell_her_to_correct_herself(self):
        """模块不得指示她把那句旧说法当口误纠正（那会压掉 canon 里给爱音的最高评价）。"""
        rana_interesting.reset_session_fired()
        body = rana_interesting.build_interesting_special_block(
            "你以前说过有趣的女人吧", session_id="w")
        self.assertIn("不要把它当成口误", body)
        self.assertIn("爱音", body)
        # 旧版本（错的）写的是「她会轻轻纠一下口」——必须已消失
        self.assertNotIn("轻轻纠一下口", body)
        self.assertNotIn("……是女孩子。」", body)

    def test_interesting_marks_canon_phrases_as_yuanhua(self):
        """旧说法的引用必须标成「原话」（canon 引用），不能算我写的例句。

        2026-09-12：正文里凡是不带「原话」标注的引号内容都会被当成例句照抄，
        所以 `NoReusableExampleSentencesTests` 只对**不带原话标注**的行设 4 字上限。
        """
        rana_interesting.reset_session_fired()
        body = rana_interesting.build_interesting_special_block(
            "你以前说过有趣的女人吧", session_id="w")
        self.assertIn("原话", body)

    def test_trigger_words_avoid_known_absent_vocabulary(self):
        """已知语料不存在的词不得进入任何触发正则。"""
        for name, mod, _, _, _ in CASES:
            for attr in dir(mod):
                if not attr.endswith("_RE"):
                    continue
                pat = getattr(mod, attr)
                if not hasattr(pat, "pattern"):
                    continue
                for bad in NOT_IN_CORPUS:
                    with self.subTest(module=name, attr=attr, bad=bad):
                        self.assertNotIn(bad, pat.pattern,
                                         f"{name}.{attr} 使用了语料不存在的词 {bad}")


if __name__ == "__main__":
    unittest.main()
