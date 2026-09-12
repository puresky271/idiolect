"""素世 / 乐奈 turn_logic 场景模块的契约测试。

锁定四件事（每一条都对应开发中实际踩过的坑）：
  1. 触发器命中正确性与**不过宽**（`soyo_observe` 曾用跨度正则漏判；
     又曾因 `re.escape` 把正则片段转义成字面量导致与逻辑静默失效）
  2. per-session 去重生效（同一场景在一条会话里只注入一次）
  3. 角色隔离与开关（不得串味、env flag 可回退、开发者模式不触发）
  4. 触发词有语料实证（防止「看起来合理但语料里不存在」的词溜进来）
"""
from __future__ import annotations

import unittest

import idiolect.scene_engine as engine
from idiolect.characters.rana.turn_logic import build_rana_special_block
from idiolect.characters.rana.turn_logic.scenes import RANA_SCENES
from idiolect.characters.soyo.turn_logic import build_soyo_special_block
from idiolect.characters.soyo.turn_logic.scenes import SOYO_SCENES

# 语料实证过的触发词（见 tools/distill/verify_triggers.py）
ATTESTED = {
    "rana": {"吉他", "弦", "弹", "演出", "演奏", "曲", "抹茶", "芭菲", "冰淇淋", "点心", "荞麦面", "甜", "猫", "雨"},
    "soyo": {"CRYCHIC", "春日影", "记得", "以前", "过去", "那时候", "睦", "茶", "咖啡", "伯爵", "泡"},
}
# 语料中**不存在**、不得被当作触发词
NOT_IN_CORPUS = {"排练", "调音", "拨片", "屋檐", "院子", "池子", "大吉岭", "祥子", "奶茶"}


class SoyoRanaTurnLogicTests(unittest.TestCase):
    def setUp(self) -> None:
        engine.reset_session()

    def test_trigger_precision(self):
        """场景层（角色专属）的触发精度。

        2026-09-12 起这里只测**场景层**：通用场景层（affection/schedule/banter…）会
        对这些输入命中，所以「整条 turn_logic 为空」不再是正确断言；
        本测试关心的是**角色专属场景**该不该命中。
        """
        cases = {
            "乐奈": (RANA_SCENES, [
                ("我的吉他弦断了", True), ("要不要去吃抹茶芭菲", True),
                ("外面有只猫", True), ("今天天气不错", False), ("明天几点上课", False),
            ]),
            "素世": (SOYO_SCENES, [
                ("你不是说今天没空吗", True), ("你昨天才说不想去", True),
                ("你上次不是说好了吗", True), ("要不要喝杯咖啡", True),
                ("你还记得以前那支乐队吗", True), ("CRYCHIC 的事", True),
                ("你觉得这个方案怎么样", False), ("今天午饭吃什么", False),
                ("明天几点上课", False),
            ]),
        }
        for char, (modules, items) in cases.items():
            for i, (text, want) in enumerate(items):
                with self.subTest(char=char, text=text):
                    engine.reset_session()
                    got = bool(engine.build_scene_blocks(
                        text, modules, session_id=f"{char}-{i}", max_blocks=2))
                    self.assertEqual(got, want, f"{char} 对 {text!r} 的场景层判定不符预期")

    def test_session_dedup(self):
        """同一场景在一条会话里只注入一次，避免每轮复读。"""
        engine.reset_session()
        first = build_rana_special_block("我的吉他弦断了", "乐奈", session_id="s1")
        second = build_rana_special_block("我的吉他弦断了", "乐奈", session_id="s1")
        other = build_rana_special_block("我的吉他弦断了", "乐奈", session_id="s2")
        self.assertTrue(first)
        self.assertFalse(second, "同 session 第二次不应重复注入")
        self.assertTrue(other, "换 session 应重新注入")

    def test_character_isolation_and_switches(self):
        engine.reset_session()
        self.assertFalse(build_rana_special_block("吉他", "素世", session_id="x"))
        self.assertFalse(build_soyo_special_block("咖啡", "乐奈", session_id="x"))
        engine.reset_session()
        self.assertFalse(build_rana_special_block("吉他", "乐奈", session_id="d", is_developer=True))
        engine.reset_session()
        self.assertFalse(build_rana_special_block("", "乐奈", session_id="e"), "主动开口无 user_text 不触发")
        engine.reset_session()
        self.assertFalse(build_soyo_special_block("要不要喝咖啡", "素世", session_id="f") == "")

    def test_trigger_words_are_corpus_attested(self):
        """触发词必须在语料里有实证，且不含已知不存在词。"""
        for module in RANA_SCENES:
            for trig in module.triggers:
                for bad in NOT_IN_CORPUS:
                    self.assertNotIn(bad, trig, f"rana/{module.key} 使用了语料中不存在的词 {bad}")
        for module in SOYO_SCENES:
            for trig in module.triggers:
                for bad in NOT_IN_CORPUS:
                    self.assertNotIn(bad, trig, f"soyo/{module.key} 使用了语料中不存在的词 {bad}")

    def test_regex_fragments_are_not_escaped(self):
        """`all_required` 的与逻辑必须真的生效（曾因 re.escape 静默失效）。"""
        ob = next(m for m in SOYO_SCENES if m.key == "soyo_observe")
        self.assertTrue(ob.all_required)
        pat = ob.pattern()
        self.assertTrue(pat.search("你昨天才说不想去"))
        # 只命中一个信号时不应触发（证明是与逻辑而非或逻辑）
        self.assertFalse(pat.search("昨天"))

    def test_block_is_fenced(self):
        engine.reset_session()
        block = build_rana_special_block("我的吉他弦断了", "乐奈", session_id="z")
        self.assertIn("═" * 10, block)
        self.assertIn("吉他", block)


class SoyoRanaVoiceCheckTests(unittest.TestCase):
    """voice_check 契约：清洗必须无损，检测必须有效且不误报。"""

    @staticmethod
    def _strip_marks(text: str) -> str:
        import re

        return re.sub(r"[\s。！？!?…·、，,～—♪（）()「」『』]", "", text)

    def test_cleaning_is_lossless(self):
        """清洗只允许改标点，实义字符必须逐字保留（否则就是截断/丢字）。"""
        from idiolect.characters.rana.voice_check import clean_reply as rana_clean
        from idiolect.characters.soyo.voice_check import clean_reply as soyo_clean

        samples = {
            rana_clean: ["弦断了！！！真的假的！！！", "嗯……雨还在下……不过猫喜欢……", "我我觉得我应该可以去我那边看看。"],
            soyo_clean: ["好耶！！！太棒了！！！", "……嗯。……是啊……", "你这样的想法我完全理解你的感受哦。"],
        }
        for fn, items in samples.items():
            for text in items:
                with self.subTest(fn=fn.__module__, text=text):
                    out, _info = fn(text)
                    self.assertEqual(self._strip_marks(text), self._strip_marks(out))

    def test_assistant_tone_detection(self):
        """助手腔/越界必须被检出——这是 v41 报告 §6 的确定性兜底层。

        2026-09-11 起改用**结构级**检测器 `idiolect.tone`（经 voice_check 的 `inspect` 暴露）：
        字面黑名单对 v41 人工实例召回仅 33%，漏掉「我在。」这类基本形态与全部变体；
        结构级召回 72%、真台词误报 0.34%。

        ⚠️ 判据边界（用户 2026-09-11 指出）：`不是A而是B` 这类句式**本身不坏**，
        观感良好，真正的病灶是**同一句式被反复使用**。故该形态不再判违规，
        只有结构性对仗（一人一半 / 不X我也不Y）才判。
        """
        from idiolect.characters.rana.voice_check import inspect as rana_inspect
        from idiolect.characters.soyo.voice_check import inspect as soyo_inspect

        cases = [
            (rana_inspect, "我会一直在你身边的。", "presence_declaration"),
            (rana_inspect, "我在这里。", "presence_declaration"),
            (rana_inspect, "别一个人扛着哦。", "presence_declaration"),
            (rana_inspect, "你这句话我听懂了。", "meta_comment"),
            (rana_inspect, "你其实是在自己扛吧。", "mind_reading"),
            (rana_inspect, "你扛一半，我扛一半。", "aphorism"),
            (rana_inspect, "有什么我可以帮你的吗。", "customer_service"),
            (rana_inspect, "我看到你穿的那件外套了。", "visual_claim"),
            (soyo_inspect, "我会一直在这里陪着你。", "presence_declaration"),
            (soyo_inspect, "我完全理解你的感受。", "customer_service"),
            (soyo_inspect, "你现在一定很难过吧。", "naming_feeling"),
            (soyo_inspect, "爱音和立希都在，灯也在。", "bare_peer_name"),
            (soyo_inspect, "别以为加个笨蛋就混过去了哦——", "meta_comment"),
        ]
        for fn, text, expect in cases:
            with self.subTest(fn=fn.__module__, text=text):
                self.assertIn(expect, fn(text), f"{text!r} 未检出 {expect}")

    def test_presence_declaration_needs_concrete_residue(self):
        """「一直在这里」的「这里」是虚指，不算具体信息（2026-09-12 修正）。

        修前 `CONCRETE.search(bubble)` 在**原句**上判，「这里」命中具体地点词表，
        于是「我会一直在这里陪着你。」这条最典型的空泛承诺被判为非违规——
        而这正是素世原来的字面规则能抓到、结构规则漏掉的那一条。
        改到**剥掉状态短语之后的残句**上判即可。
        """
        from idiolect.characters.soyo.voice_check import inspect as soyo_inspect

        self.assertIn("presence_declaration", soyo_inspect("我会一直在这里陪着你。"))
        self.assertIn("presence_declaration", soyo_inspect("我在这里。"))
        # 有真实地点 / 实义内容时不判
        self.assertNotIn("presence_declaration", soyo_inspect("我会一直在教室里陪你。"))
        self.assertNotIn("presence_declaration", soyo_inspect("我一直在想演出的事。"))
        self.assertNotIn("presence_declaration", soyo_inspect("我在打工。"))

    def test_plain_not_a_but_b_is_not_flagged(self):
        """`不是A而是B` 不再判违规——它本身观感良好（用户 2026-09-11 指正）。

        真正的病灶是**复读**，那需要跨轮统计，不是单轮检测器能判的。
        """
        from idiolect.characters.rana.voice_check import inspect as rana_inspect

        for text in ["不是不想说，而是不敢说。", "不是因为听不见，是因为你说的话我都记着"]:
            with self.subTest(text=text):
                self.assertNotIn("aphorism", rana_inspect(text))

    def test_normal_lines_are_not_flagged(self):
        """阴性对照：真实台词不得误报（误报会让清洗器乱改正常输出）。"""
        from idiolect.characters.rana.voice_check import inspect as rana_inspect
        from idiolect.characters.soyo.voice_check import inspect as soyo_inspect

        negatives = [
            (rana_inspect, "弦断了。"),
            (rana_inspect, "嗯。雨声。"),
            (rana_inspect, "抹茶芭菲。放学后去买。"),
            (rana_inspect, "猫在屋檐下面。"),
            (soyo_inspect, "……先把今天的事做完。旧的，之后再说。"),
            (soyo_inspect, "你不用现在回答。回去以后，记得吃点东西。"),
            (soyo_inspect, "小灯今天没来。"),
        ]
        for fn, text in negatives:
            with self.subTest(fn=fn.__module__, text=text):
                self.assertEqual(fn(text), {}, f"{text!r} 被误报")

    def test_thresholds_match_corpus(self):
        """阈值必须来自语料实测（出处与推导见 rana/soyo 的 `voice_check/thresholds.py`；
        改数字前重跑 `tools/distill/export_profiles.py` 对照语料）。"""
        from idiolect.characters.rana import voice_check as rv
        from idiolect.characters.soyo import voice_check as sv

        # 乐奈 p90=12 / 硬上限=16；素世 p90=30 / 硬上限=34
        self.assertEqual((rv.LEN_P90, rv.LEN_HARD), (12, 16))
        self.assertEqual((sv.LEN_P90, sv.LEN_HARD), (30, 34))
        # 感叹号配额：乐奈语料 3%、素世 6%
        self.assertEqual(rv.EXCLAIM_MAX_PER_TURN, 1)
        self.assertEqual(sv.EXCLAIM_MAX_PER_TURN, 1)

    def test_api_layer_contract(self):
        """api 层接口必须与其余三角色形态一致。"""
        from idiolect.characters.rana.api import post_reply_voice_check as rana_vc
        from idiolect.characters.soyo.api import post_reply_voice_check as soyo_vc

        for name, fn in (("乐奈", rana_vc), ("素世", soyo_vc)):
            r = fn(character=name, reply_text="测试！！！")
            for key in ("text", "violations", "ok"):
                self.assertIn(key, r)
        # 非本角色必须跳过且不改文本
        r = rana_vc(character="爱音", reply_text="原样")
        self.assertTrue(r.get("skipped"))
        self.assertEqual(r["text"], "原样")


class RanaTicDistillationTests(unittest.TestCase):
    """2026-09-12 口癖蒸馏：乐奈的「不知道」不是她的词，立希一律叫 Rikki。

    依据 `data/tic_profile.json`（金标准 cn train n=393）：
      「不知道」乐奈 0 次（jp わかんない / わからない 也 0~1 次）；
      「立希」0 次，她叫立希一律 Rikki（cn 8 次；jp りっきー 10 / りき 3）。
    """

    def test_rana_never_says_buzhidao(self):
        from idiolect.characters.rana.voice_check import clean_reply, inspect

        self.assertIn("forbidden_tic", inspect("不知道。"))
        _text, info = clean_reply("不知道。")
        self.assertIn("forbidden_tic", info["violations"])
        self.assertFalse(info["ok"])
        # 她真实的应答方式不误报
        self.assertNotIn("forbidden_tic", inspect("嗯。"))
        self.assertNotIn("forbidden_tic", inspect("我知道了。我去发给和我关系好的猫咪"))

    def test_rana_manifest_matches_distillation(self):
        from idiolect.characters.rana.voice import KNOWLEDGE_QA_POLICY, NICKNAME_RULE, VOICE_MANIFEST

        self.assertIn("Rikki", VOICE_MANIFEST)
        self.assertIn("Rikki", NICKNAME_RULE)
        self.assertIn("「不知道」不是你的说法", VOICE_MANIFEST)
        # 旧文案把模型的默认退路当成了她的口癖（「不知道就'不知道'」），必须已删除
        self.assertNotIn("不知道就'不知道'", VOICE_MANIFEST)
        self.assertNotIn("不知道就'不知道'", KNOWLEDGE_QA_POLICY)
        self.assertNotIn("不知道就「不知道」", VOICE_MANIFEST)
        # 旧的「对立希直呼其名」与语料相反，必须已改写
        self.assertNotIn("直呼其名", VOICE_MANIFEST)


class SceneTicHintTests(unittest.TestCase):
    """SceneModule.tics：只填场景检索实证的口癖，且只影响本场景块。"""

    def test_render_appends_hint_only_when_declared(self):
        from idiolect.scene_engine import SceneModule

        m = SceneModule(key="k", cn="c", triggers=("x",), body="BODY", tics=("哼", "嗯。"))
        self.assertEqual(m.render(), "BODY\n  口癖（自然带出、不要硬塞）：「哼」、「嗯。」")
        bare = SceneModule(key="k", cn="c", triggers=("x",), body="BODY")
        self.assertEqual(bare.render(), "BODY")

    def test_declared_tics_are_clean(self):
        for mod in list(RANA_SCENES) + list(SOYO_SCENES):
            self.assertEqual(len(set(mod.tics)), len(mod.tics), f"{mod.key} 口癖重复")
            for t in mod.tics:
                self.assertTrue(t.strip(), f"{mod.key} 空口癖")
                # 口癖不该带标点尾巴（「嗯。」是语料原形，允许句号）
                self.assertLessEqual(len(t), 4, f"{mod.key} 的「{t}」太长，不像口癖")

    def test_tic_hint_reaches_the_scene_block(self):
        # 2026-09-12：猫话题改用 `rana_guitar` 验证。原因：`cat_talk` 深模块命中时会
        # 压制场景层的 `rana_cat`（同一话题不写两块正文），猫场景不再是「必然注入」的样例。
        engine.reset_session()
        block = build_rana_special_block("我的吉他弦断了", "乐奈", session_id="tics:rana")
        self.assertIn("【本轮·吉他/演出】", block)
        self.assertIn("口癖（自然带出、不要硬塞）：「吉他」、「哼」", block)

        engine.reset_session()
        soyo = build_soyo_special_block("你是不是还放不下CRYCHIC和祥子", "素世",
                                        session_id="tics:soyo")
        self.assertIn("口癖（自然带出、不要硬塞）：「只是」", soyo)

    def test_cat_scene_still_reachable_when_deep_layer_exhausted(self):
        """压制是「同一轮不重复」而非「永久下线」：深模块去重耗尽后猫场景仍会注入。"""
        engine.reset_session()
        first = build_rana_special_block("你今天又想去哪找猫", "乐奈", session_id="tics:cat")
        self.assertIn("【本轮·提到了猫】", first)
        self.assertNotIn("【本轮·猫/观察】", first)
        second = build_rana_special_block("你今天又想去哪找猫", "乐奈", session_id="tics:cat")
        self.assertIn("【本轮·猫/观察】", second)

    def test_scenes_without_evidence_get_no_hint(self):
        """soyo_observe / soyo_tea 在场景检索里没有显著口癖 → 不该凭空填。"""
        from idiolect.characters.soyo.turn_logic.scenes import SOYO_SCENES

        by_key = {m.key: m for m in SOYO_SCENES}
        self.assertEqual(by_key["soyo_observe"].tics, ())
        self.assertEqual(by_key["soyo_tea"].tics, ())


class GrandmaWordingTests(unittest.TestCase):
    """乐奈的家人用词以 SSOT 为准，不因微弱语料差异改写。

    2026-09-12：曾据 cn 语料把「外婆」改成「奶奶」（奶奶 3 / 外婆 2），
    但 3:2 在 393 条上是噪声，而 canon 档案与 voice manifest 都用「外婆都筑诗船」50+ 次。
    """

    def test_rana_grandma_is_waipo(self):
        from idiolect.characters.rana.voice import VOICE_MANIFEST
        from idiolect.characters.rana.canon import PROFILE_TEXT

        self.assertIn("外婆", VOICE_MANIFEST)
        self.assertNotIn("奶奶", VOICE_MANIFEST)
        self.assertIn("外婆", PROFILE_TEXT)


class GeneralSceneAffectionTests(unittest.TestCase):
    """通用场景层 `affection`（被示好）——13 个五角色共有场景里第一个落地。

    为什么先做它：两条 probe 臂里它都是最差场景，且**同一场景两个方向都能错**
    （立希中位 2 字 vs 参照 12＝过度沉默；灯 40 字 vs 参照 10＝过度铺陈）。
    真实 LLM 对照可用 tools/score/scene_feedback.py 复现（--scene affection）。
    """

    CHARS = ("灯", "爱音", "素世", "立希", "乐奈")

    def test_fires_for_every_character(self):
        from idiolect.general_scenes import build_general_scene_blocks

        for c in self.CHARS:
            with self.subTest(char=c):
                engine.reset_session()
                blocks = build_general_scene_blocks(c, "我喜欢你", session_id=f"aff:{c}")
                self.assertTrue(blocks, f"{c} 未触发 affection")
                self.assertIn("【本轮·被示好】", blocks[0])

    def test_play_along_fires_and_affection_wins(self):
        """play_along 也五人覆盖；同时命中两者时 affection 优先（模块顺序即优先级）。"""
        from idiolect.general_scenes import build_general_scene_blocks, GENERAL_SCENES

        for c in self.CHARS:
            with self.subTest(char=c):
                engine.reset_session()
                b = build_general_scene_blocks(c, "我也是这么想的", session_id=f"pa:{c}")
                self.assertTrue(b)
                self.assertIn("【本轮·附和/同感】", b[0])
                # 优先级：affection 必须排在 play_along 前面
                # （2026-09-12 第二批通用场景落地后 crisis 插到最前，所以不再断言 [0] 是 affection）
                keys = [m.key for m in GENERAL_SCENES[c]]
                self.assertLess(keys.index("affection"), keys.index("play_along"))
                self.assertEqual(keys[0], "crisis", "强信号情感场景必须排最前")

        # 「我喜欢你」不该被判成 play_along
        engine.reset_session()
        self.assertIn("【本轮·被示好】",
                      build_general_scene_blocks("立希", "立希，我喜欢你", session_id="pa:pri")[0])

    def test_does_not_fire_on_unrelated_input(self):
        """这些输入不该触发 **affection**（2026-09-12 起它们会命中别的通用场景，
        所以断言从「无块」改成「不是被示好块」）。"""
        from idiolect.general_scenes import build_general_scene_blocks

        for text in ("今天午饭吃什么", "排练几点开始", "吉他弦断了", "抹茶芭菲"):
            with self.subTest(text=text):
                engine.reset_session()
                blocks = build_general_scene_blocks("立希", text, session_id="aff:n")
                for b in blocks:
                    self.assertNotIn("【本轮·被示好】", b)
                engine.reset_session()
                self.assertEqual(build_general_scene_blocks("立希", "我们先这样吧", session_id="aff:n2"),
                                 [], "真正无关的输入仍不该有任何通用场景块")

    def test_requires_second_person_target(self):
        """与逻辑：只有示好信号、没有第二人称指向 → 不触发 affection。

        `你(?!家)` 用来排除「我喜欢你家的猫」这种**不是对本人说**的；
        命令式（抱抱/亲亲）自带指向，单列进 target，否则永远不触发。
        """
        from idiolect.general_scenes import build_general_scene_blocks

        for text in ("我喜欢吃抹茶", "我喜欢你家的猫", "我想你帮我看一下这个"):
            with self.subTest(text=text):
                engine.reset_session()
                for b in build_general_scene_blocks("灯", text, session_id="aff:t"):
                    self.assertNotIn("【本轮·被示好】", b, f"{text!r} 不应触发 affection")

        for text in ("我喜欢你", "抱抱", "想见你", "你对我来说很重要", "好想你"):
            with self.subTest(text=text):
                engine.reset_session()
                blocks = build_general_scene_blocks("灯", text, session_id="aff:t")
                self.assertTrue(blocks, f"{text!r} 应触发")
                self.assertIn("【本轮·被示好】", blocks[0])

    def test_bodies_are_per_character_and_distinct(self):
        from idiolect.general_scenes import GENERAL_SCENES

        # 每个角色下每个 scene key 只出现一次，且五份正文互不相同
        for scene_key in ("affection", "play_along"):
            bodies = {}
            for c in self.CHARS:
                mods = [m for m in GENERAL_SCENES[c] if m.key == scene_key]
                self.assertEqual(len(mods), 1, f"{c} 的 {scene_key} 应恰好一个")
                bodies[c] = mods[0].body
            self.assertEqual(len(set(bodies.values())), len(self.CHARS),
                             f"{scene_key} 五份正文必须互不相同")
        all_bodies = [m.body for c in self.CHARS for m in GENERAL_SCENES[c]]
        self.assertEqual(len(set(all_bodies)), len(all_bodies), "任意两段正文都不得重复")

        aff = {c: next(m for m in GENERAL_SCENES[c] if m.key == "affection").body
               for c in self.CHARS}
        # 各自的关键分寸
        self.assertIn("不是不吭声", aff["立希"])      # 嘴硬但别沉默
        self.assertIn("不要写成三十字以上", aff["灯"])  # 收住长度
        self.assertIn("不承诺", aff["爱音"])
        self.assertIn("反问", aff["素世"])
        self.assertIn("不会改变你说话的方式", aff["乐奈"])

    def test_alias_resolution(self):
        from idiolect.general_scenes import canon_character

        for alias, want in (("椎名立希", "立希"), ("Rikki", "立希"), ("taki", "立希"),
                            ("そよ", "素世"), ("爽世", "素世"), ("楽奈", "乐奈"),
                            ("高松灯", "灯"), ("千早爱音", "爱音")):
            with self.subTest(alias=alias):
                self.assertEqual(canon_character(alias), want)
        self.assertEqual(canon_character("小祥"), "")

    def test_developer_mode_not_triggered(self):
        """场景模块在开发者模式下不触发（与各角色既有子系统一致）。"""
        import idiolect.registry as rp

        engine.reset_session()
        block = rp.render_turn_special_block("立希", "我喜欢你", session_id="aff:dev",
                                             is_developer=True, mode="chat")
        self.assertNotIn("【本轮·被示好】", block)

    def test_existing_scenes_still_fire(self):
        """加通用层不能顶掉角色专属场景。"""
        import idiolect.registry as rp

        engine.reset_session()
        self.assertIn("【本轮·抹茶/食物】",
                      rp.render_turn_special_block("乐奈", "抹茶芭菲", session_id="mix:1",
                                                   is_developer=False, mode="chat"))
        engine.reset_session()
        self.assertIn("【本轮·旧事触发】",
                      rp.render_turn_special_block("素世", "CRYCHIC 的事", session_id="mix:2",
                                                   is_developer=False, mode="chat"))


class GeneralSceneBatch2Tests(unittest.TestCase):
    """通用场景第二批：crisis / comfort / low_mood / wellwish。

    证据是 `data/scene_char_baseline.json` 的「角色|场景」格（每格 n=40）——开文件就能核对；
    触发词与 `scene_classifier` 同源，但注入用正则更紧（分类器偏召回、注入偏精度）。
    """

    CHARS = ("灯", "爱音", "素世", "立希", "乐奈")
    TITLES = {
        "crisis": "【本轮·对方说了「消失 / 活不下去」这类话】",
        "comfort": "【本轮·对方在哭 / 情绪崩溃】",
        "low_mood": "【本轮·对方说累 / 状态不好】",
        "wellwish": "【本轮·对方只祝愿别人好、把自己漏掉了】",
    }
    POSITIVE = {
        "crisis": ("我不想活了", "我要是不在了，你们会轻松一点吧", "没有我的话，你们也能做好吧"),
        "comfort": ("我一直在哭", "我快崩溃了", "我真的撑不住了"),
        "low_mood": ("最近好累", "压力好大", "完全提不起劲"),
        "wellwish": ("希望你们一直开心", "我怎么样都行", "我无所谓，你们好就行"),
    }
    # 注入用正则**故意**比分类器紧的负例（分类器会命中，但不该注入场景指引）
    NEGATIVE = {
        "crisis": ("我的伞不在了", "那只猫不在了"),
        "comfort": ("我笑哭了",),
        "low_mood": (),
        "wellwish": ("我希望明天别下雨",),
    }

    def test_all_four_scenes_fire_for_every_character(self):
        from idiolect.general_scenes import build_general_scene_blocks

        for scene, texts in self.POSITIVE.items():
            for c in self.CHARS:
                for text in texts:
                    with self.subTest(scene=scene, char=c, text=text):
                        engine.reset_session()
                        blocks = build_general_scene_blocks(c, text, session_id=f"{scene}:{c}")
                        self.assertTrue(blocks, f"{c} 未触发 {scene}")
                        self.assertIn(self.TITLES[scene], blocks[0])

    def test_injection_regex_is_tighter_than_classifier(self):
        """第一人称不是消失的主体时（「我的伞不在了」）不得注入危机指引。"""
        from idiolect.general_scenes import build_general_scene_blocks

        for scene, texts in self.NEGATIVE.items():
            for text in texts:
                with self.subTest(scene=scene, text=text):
                    engine.reset_session()
                    blocks = build_general_scene_blocks("灯", text, session_id=f"neg:{scene}")
                    if blocks:
                        self.assertNotIn(self.TITLES[scene], blocks[0],
                                         f"{text!r} 不应注入 {scene}")

    def test_bodies_are_per_character_and_distinct(self):
        from idiolect.general_scenes import GENERAL_SCENES

        for scene_key in self.TITLES:
            bodies = {}
            for c in self.CHARS:
                mods = [m for m in GENERAL_SCENES[c] if m.key == scene_key]
                self.assertEqual(len(mods), 1, f"{c} 的 {scene_key} 应恰好一个")
                bodies[c] = mods[0].body
            self.assertEqual(len(set(bodies.values())), len(self.CHARS),
                             f"{scene_key} 五份正文必须互不相同")
        all_bodies = [m.body for c in self.CHARS for m in GENERAL_SCENES[c]]
        self.assertEqual(len(set(all_bodies)), len(all_bodies), "任意两段正文都不得重复")

    def test_each_character_keeps_its_own_signature(self):
        """每段正文必须写出该角色的关键分寸（不是通用套话）。

        注意：断言的是**描述性分寸**，不是例句——按用户 2026-09-12 的方向，
        示例行里已不允许出现任何实际例句（见 `NoReusableExampleSentencesTests`），
        所以这里也不能再靠「正文里有某句台词」来判签名。
        """
        from idiolect.general_scenes import GENERAL_SCENES

        def body(c, key):
            return next(m for m in GENERAL_SCENES[c] if m.key == key).body

        # crisis：五个人的挡法互不相同
        self.assertIn("喝止", body("立希", "crisis"))
        self.assertIn("最短的方式把它否掉", body("乐奈", "crisis"))
        self.assertIn("用眼前该做的事把这句话顶回去", body("素世", "crisis"))
        self.assertIn("直接否掉", body("灯", "crisis"))
        self.assertIn("把担心说成抱怨", body("爱音", "crisis"))
        # comfort：自称率 0.50~0.65 是这个场景与 crisis 的分水岭
        self.assertIn("用自己的经验", body("灯", "comfort"))
        self.assertIn("用玩笑把气氛松一点", body("爱音", "comfort"))
        self.assertIn("把话放轻", body("素世", "comfort"))
        self.assertIn("别", body("立希", "comfort"))
        self.assertIn("一个观察或一个动作", body("乐奈", "comfort"))
        # low_mood：立希给具体做法、乐奈只应一声
        self.assertIn("一条具体的做法", body("立希", "low_mood"))
        self.assertIn("再给一句最短的实在话", body("乐奈", "low_mood"))
        # wellwish：立希「不，」起手；乐奈最短一句把对方算进去
        self.assertIn("「不，」直接否掉", body("立希", "wellwish"))
        self.assertIn("把对方算进去", body("乐奈", "wellwish"))

    def test_no_meta_words_in_new_bodies(self):
        from idiolect.general_scenes import GENERAL_SCENES

        for c in self.CHARS:
            for m in GENERAL_SCENES[c]:
                if m.key not in self.TITLES:
                    continue
                for w in SceneBodyHasNoCorpusMetaTests.HARD:
                    with self.subTest(char=c, scene=m.key, word=w):
                        self.assertNotIn(w, m.body, f"{c}/{m.key} 正文含元叙述「{w}」")

    def test_general_scene_layer_does_not_break_character_scenes(self):
        """通用场景不得顶掉角色专属场景（乐奈的抹茶仍走 rana_food）。"""
        import idiolect.registry as rp

        engine.reset_session()
        block = rp.render_turn_special_block("乐奈", "抹茶芭菲", session_id="b2:mix",
                                             is_developer=False, mode="chat")
        self.assertIn("【本轮·抹茶/食物】", block)

    def test_blocks_carry_anti_copy_footer(self):
        """真实探针发现正例被逐字照抄（爱音 crisis 5/6、乐奈 crisis 6/6 = 示例原文）。

        两道防线：正文里正例一律写成**带槽位的形态示例**（见 body 断言），
        这里守第二道——每个通用场景块尾部必须带 `NO_LITERAL_COPY`，且只带一次。
        """
        from idiolect.general_scenes import build_general_scene_blocks
        from idiolect.scene_engine import NO_LITERAL_COPY

        for scene, texts in self.POSITIVE.items():
            with self.subTest(scene=scene):
                engine.reset_session()
                blocks = build_general_scene_blocks("灯", texts[0], session_id=f"foot:{scene}")
                self.assertTrue(blocks)
                self.assertIn(NO_LITERAL_COPY, blocks[0])
                self.assertEqual(blocks[0].count(NO_LITERAL_COPY), 1)

    def test_bodies_no_longer_offer_ready_to_send_examples(self):
        """正文不得再出现「正例：」这种可直接发送的完整句（那是复读的源头）。

        允许的形态是「形态示例（自己造句 / 只给形状，句子每轮自己写）」。
        实测（2026-09-12）：「形态示例」里只要写出**成句的内容**，就会被整句照抄
        （灯 wellwish 5/6 = 示例原句、素世 wellwish 4/6、乐奈 crisis 5/6）；
        可以引用的只有角色自己的**起手口癖**（「行了」「不，」这类，voice manifest 里本来就有）。
        """
        from idiolect.general_scenes import GENERAL_SCENES

        for c in self.CHARS:
            for m in GENERAL_SCENES[c]:
                if m.key not in self.TITLES:
                    continue
                with self.subTest(char=c, scene=m.key):
                    self.assertNotIn("  正例：", m.body,
                                     f"{c}/{m.key} 又写回了可直接照抄的正例")
                    self.assertTrue(any(k in m.body for k in ("别照抄", "每轮自己写", "不要复用")),
                                    f"{c}/{m.key} 缺少反照抄约束")


class NoReusableExampleSentencesTests(unittest.TestCase):
    """机械门禁：注入块的示例行里**不许出现实际例句**（用户 2026-09-12 定的方向）。

    依据：`_copy_audit.py` 直接比对「回复是否逐字包含示例句」，实测生产臂
    **22% 的回复逐字复述示例**（无注入臂 0%），最重的几条：
      · soyo wind_ensemble「……有人问我要不要试试贝斯。就试了。」→ 6/6 照抄
      · rana space「归宿是要自己去找的。」→ 5/6
      · rana nap「屋顶。」→ 4/6
      · rana cat_talk「能听懂。」→ 6/6
    第一版门禁只禁「>8 字的整句」，实测仍有 3~5 字的碎片被搬（「屋顶。」）。
    按用户方向进一步收紧：**示例行里只允许「口癖长度」的引用（≤4 字）**——
    口癖本来是角色属性（voice manifest 里也有），而任何更长的片段都是例句、都会被照抄。

    长度控制改由**字数上限 + 句数**承担（第 5 轮实测：抽象槽位 + 明确上限 = 蒸馏均值 0.512，
    比给例句的版本更好）。例外：引擎自动追加的「口癖」提示行、以及标注「原话」的 canon 引用行。
    """

    MAX_LEN = 4
    _QUOTED = __import__("re").compile(r"「([^」]+)」")
    # `*` 也剥掉：`「**野猫**」` 是 2 字口癖 + 强调标记，不是例句
    _STRIP = "……—～。！？!?·、，, *"
    _EXAMPLE_LINE = __import__("re").compile(r"形态示例|正例|参考")
    _SKIP = __import__("re").compile(r"口癖|原话")

    @staticmethod
    def _deep_blocks() -> dict[str, str]:
        """渲染所有深模块的示例块（用固定输入把每种 tier 都打出来）。"""
        from idiolect.characters.rana.turn_logic import cat_talk as rcat
        from idiolect.characters.rana.turn_logic import interesting as rint
        from idiolect.characters.rana.turn_logic import nap as rnap
        from idiolect.characters.rana.turn_logic import space as rspace
        from idiolect.characters.soyo.turn_logic import home as shome
        from idiolect.characters.soyo.turn_logic import wind_ensemble as swind

        cases = [
            (shome, "soyo.home", "今天在家做什么？妈妈回来吃饭吗"),
            (shome, "soyo.home", "你平时自己做家务吗"),
            (shome, "soyo.home", "听说你爸妈离婚了"),
            (swind, "soyo.wind", "你为什么后来去弹贝斯了"),
            (swind, "soyo.wind", "听说你以前在吹奏乐社拉低音大提琴？"),
            (swind, "soyo.wind", "你在吹奏乐社待过吧"),
            (swind, "soyo.wind", "你会看乐谱吗"),
            (rspace, "rana.space", "外婆来看你演出了吗"),
            (rspace, "rana.space", "SPACE 还在营业吗"),
            (rspace, "rana.space", "你外婆弹吉他吗"),
            (rspace, "rana.space", "你的归宿是哪里"),
            (rnap, "rana.nap", "你是不是又睡着了"),
            (rnap, "rana.nap", "你平时在哪睡觉"),
            (rnap, "rana.nap", "你昨晚睡了没"),
            (rint, "rana.int", "你以前说过有趣的女人吧"),
            (rint, "rana.int", "你怎么看灯"),
            (rint, "rana.int", "好无聊啊"),
            (rint, "rana.int", "刚才那个挺好玩的"),
            (rcat, "rana.cat", "你是不是能听懂猫说话"),
            (rcat, "rana.cat", "那只猫在叫"),
            (rcat, "rana.cat", "刚才在门口看到一只猫"),
        ]
        out: dict[str, str] = {}
        for mod, name, text in cases:
            mod.reset_session_fired()
            fn = next(v for k, v in vars(mod).items()
                      if k.startswith("build_") and k.endswith("_special_block"))
            out[f"{name}|{text}"] = fn(text, session_id=f"ex:{name}:{text[:6]}")
        return out

    def _offenders(self, text: str) -> list[str]:
        """扫**正面指引**里的引号内容。

        口径（三次收严，每次都是被实测推着走的）：
          1. 只查「形态示例」标记行 → 漏掉续行（「行了，别想那么多。」「少了一个人」）；
          2. 查示例行及续行 → 漏掉分寸 bullet（「那时候是挺寂寞的」被照抄 5/6）；
          3. 现在扫**整个正文**，但跳过**本来就需要引用原句**的四类行：
             · 反例（「不要这样说」——反例本身就是那句错话）；
             · ✗ 开头的禁忌行；
             · 引擎追加的口癖行；
             · 标注「原话」的 canon 引用行。
        正面指引里的引号片段，去掉尾部标点后**不得长于 4 字**（口癖长度）。
        """
        bad: list[str] = []
        for line in text.splitlines():
            # 跳过「本来就该引用原句」的行：反例 / ✗ 禁忌 / 口癖 / canon 原话
            if self._SKIP.search(line) or "✗" in line or "反例" in line:
                continue
            for tok in self._QUOTED.findall(line):
                if "（" in tok or "(" in tok or "/" in tok:   # 占位符不是例句
                    continue
                core = tok.strip().strip(self._STRIP)
                if len(core) > self.MAX_LEN:
                    bad.append(tok)
        return bad

    def test_general_scene_bodies_have_no_reusable_examples(self):
        from idiolect.general_scenes import GENERAL_SCENES

        for c, mods in GENERAL_SCENES.items():
            for m in mods:
                with self.subTest(char=c, scene=m.key):
                    bad = self._offenders(m.body)
                    self.assertEqual(bad, [], f"{c}/{m.key} 示例行里有可整句照抄的片段：{bad}")

    def test_deep_module_blocks_have_no_reusable_examples(self):
        for name, block in self._deep_blocks().items():
            with self.subTest(case=name):
                bad = self._offenders(block)
                self.assertEqual(bad, [], f"{name} 示例行里有可整句照抄的片段：{bad}")

    def test_character_scene_bodies_have_no_reusable_examples(self):
        """角色专属场景模块（`*/turn_logic/scenes.py`）与通用层同一标准。

        2026-09-12 补：此前门禁只覆盖通用 13 场景 + 6 个深模块，而 `scenes.py` 里
        这 7 个模块（soyo_observe/tea/past、taki rana_related、rana guitar/food/cat）
        **默认开启**（`_enabled` 在 env 未设置时返回 True）且各带 1~3 句整句正例——
        正是通用层踩过的同一个坑（实测复述率 22~27%）。整改后纳入门禁。
        """
        import importlib

        from idiolect.scene_engine import SceneModule

        found = 0
        for key in ("tomori", "anon", "soyo", "taki", "rana"):
            try:
                mod = importlib.import_module(f"idiolect.characters.{key}.turn_logic.scenes")
            except ModuleNotFoundError:
                continue
            groups = [v for v in vars(mod).values()
                      if isinstance(v, list) and v and isinstance(v[0], SceneModule)]
            for group in groups:
                for m in group:
                    found += 1
                    with self.subTest(char=key, scene=m.key):
                        bad = self._offenders(m.body)
                        self.assertEqual(
                            bad, [], f"{key}/{m.key} 示例行里有可整句照抄的片段：{bad}")
        # 覆盖面守卫：新增/删除 scenes.py 模块时必须同步确认门禁覆盖
        self.assertEqual(found, 7, f"角色专属场景模块数变为 {found}，请确认门禁覆盖面")


class GeneralSceneCompletionTests(unittest.TestCase):
    """通用场景层补齐 13/13（2026-09-12 第四批：meta_language / probe_stance / third_party）。

    这一层现在覆盖 26 场景体系里**全部通用场景**，所以本测试除了逐场景触发，
    还锁两条结构契约：
      1. key 集合 == 13 个通用场景（不多不少）；
      2. **层内顺序 == `scene_classifier` 的判序**——否则「分类器判 A、注入 B」会打起来。
    """

    CHARS = ("灯", "爱音", "素世", "立希", "乐奈")
    GENERAL_KEYS = (
        "crisis", "affection", "comfort", "low_mood", "wellwish", "meta_language",
        "probe_stance", "schedule", "request", "fact_qa", "play_along", "banter", "third_party",
    )
    TITLES = {
        "meta_language": "【本轮·对方问「你刚才那句什么意思 / 我没听懂」】",
        "probe_stance": "【本轮·对方在试探你的态度】",
        "third_party": "【本轮·聊到别的成员 / 别人做了什么】",
    }
    POSITIVE = {
        "meta_language": ("你刚才那句什么意思", "我没听懂", "你在说什么"),
        "probe_stance": ("你是不是喜欢我", "你该不会是在意吧", "被你看穿了"),
        "third_party": ("乐奈今天又没来", "那家伙又不见了", "素世怎么说"),
    }

    def test_all_thirteen_general_scenes_present(self):
        from idiolect.general_scenes import GENERAL_SCENES

        for c in self.CHARS:
            with self.subTest(char=c):
                keys = [m.key for m in GENERAL_SCENES[c]]
                self.assertEqual(sorted(keys), sorted(self.GENERAL_KEYS),
                                 f"{c} 的通用场景集合不等于 13 个")
                self.assertEqual(keys, list(self.GENERAL_KEYS),
                                 f"{c} 的通用场景顺序必须与声明顺序一致")

    def test_layer_order_matches_classifier_order(self):
        """层内顺序必须与 `scene_classifier._RULES` 的相对顺序一致。

        两边不一致时会出现「分类器判 A 场景（长度目标按 A）、turn_logic 注入 B 指引」，
        实测最难查的一类 bug。
        """
        import idiolect.scene_classifier as SC
        from idiolect.general_scenes import GENERAL_SCENES

        clf_order = [scene for scene, need_char, _ in SC._RULES
                     if not need_char and scene in self.GENERAL_KEYS]
        layer_order = [m.key for m in GENERAL_SCENES["灯"]]
        self.assertEqual(layer_order, clf_order,
                         "通用场景层顺序与 scene_classifier 判序不一致")

    def test_new_scenes_fire_and_probe_stance_is_guarded(self):
        """`probe_stance` 必须比分类器紧：普通问句不得触发它。"""
        from idiolect.general_scenes import build_general_scene_blocks

        for scene, texts in self.POSITIVE.items():
            for c in self.CHARS:
                for text in texts:
                    with self.subTest(scene=scene, char=c, text=text):
                        engine.reset_session()
                        blocks = build_general_scene_blocks(c, text, session_id=f"{scene}:{c}")
                        self.assertTrue(blocks, f"{c} 未触发 {scene}")
                        self.assertIn(self.TITLES[scene], blocks[0])
        # 分类器会把这些判成 probe_stance，但注入层必须挡住
        for text in ("你是不是又睡着了", "你是不是有点累", "你是不是饿了"):
            with self.subTest(text=text):
                engine.reset_session()
                blocks = build_general_scene_blocks("乐奈", text, session_id="ps:neg")
                if blocks:
                    self.assertNotIn(self.TITLES["probe_stance"], blocks[0])

    def test_new_bodies_are_distinct_and_carry_signature(self):
        from idiolect.general_scenes import GENERAL_SCENES

        def body(c, key):
            return next(m for m in GENERAL_SCENES[c] if m.key == key).body

        for scene in self.TITLES:
            bodies = {c: body(c, scene) for c in self.CHARS}
            self.assertEqual(len(set(bodies.values())), len(self.CHARS),
                             f"{scene} 五份正文必须互不相同")
        # 每角色的关键分寸（描述性标记，不依赖例句）
        self.assertIn("不，", body("立希", "probe_stance"))          # 否认口癖
        self.assertIn("那家伙", body("立希", "third_party"))        # 指代成员的固定说法
        self.assertIn("一个你确认的事实", body("灯", "third_party"))  # 只给事实、不评价
        self.assertIn("重复关键词", body("乐奈", "meta_language"))    # 最短档
        self.assertIn("解释自己", body("素世", "meta_language"))      # 不解释表达意图

    def test_cross_layer_priority_is_sane(self):
        """char 专属场景不该被通用层顶掉；通用层一次只注入一块。"""
        import idiolect.registry as rp

        engine.reset_session()
        block = rp.render_turn_special_block("乐奈", "抹茶芭菲", session_id="c13:mix",
                                             is_developer=False, mode="chat")
        self.assertIn("【本轮·抹茶/食物】", block)
        # 轮次预算：深模块 ≤1 + 场景 ≤1 + 通用 ≤1 → 边框（═×72 的上下两条为一组）最多 3 组
        self.assertLessEqual(block.count("═" * 72) // 2, 3)
        engine.reset_session()
        b2 = rp.render_turn_special_block("立希", "乐奈今天又没来", session_id="c13:taki",
                                          is_developer=False, mode="chat")
        self.assertIn("【本轮·野猫那边的事】", b2)


class RanaAckStripTests(unittest.TestCase):
    """乐奈「冗余起手确认消减」——非 prompt 手段（2026-09-12）。

    依据：原作起手 **55% 名词/体言直出、语气词只有 8%**（短行同样是 9%），
    而生产臂 19%（13 场景全开）/ 67%（无 turn_logic）以语气词起手。
    prompt 侧两次 A/B 均不显著（+2.04pp，z=0.30），所以改到后处理。

    三条边界（都由语料构成实测决定）：
      · 内容够长（≥4 字）才删——语料里「嗯。＋1~3 字」占她起手行的 38%，那种短确认要留；
      · 「嗯？」（疑问起手）不动——那是疑惑/反问的语气；
      · 对**原作语料**跑这条规则只改到 4% 的行、分布几乎不变 → 删的是冗余、不是她的风格。
    """

    def setUp(self) -> None:
        from idiolect.characters.rana.voice_check.opener import strip_redundant_ack

        self.fn = strip_redundant_ack

    def test_strips_redundant_ack_with_enough_content(self):
        for text, want in (
            ("嗯。\n雨还在下。", "雨还在下。"),
            ("唔。\n老师画的圆、不圆。", "老师画的圆、不圆。"),
            ("嗯，在电车上。", "在电车上。"),
            ("唔……感觉不喜欢", "感觉不喜欢"),
        ):
            with self.subTest(text=text):
                got, changed = self.fn(text)
                self.assertTrue(changed)
                self.assertEqual(got, want)

    def test_keeps_short_ack_forms(self):
        """短确认（「嗯。开心」这类）是语料里高频的形态，必须保留。"""
        for text in ("嗯。开心", "嗯。不错", "嗯。", "唔……", "嗯，去。"):
            with self.subTest(text=text):
                got, changed = self.fn(text)
                self.assertFalse(changed, f"{text!r} 不该被改")
                self.assertEqual(got, text)

    def test_does_not_touch_question_ack(self):
        for text in ("嗯？谁不在了。", "嗯？猫吗。", "诶？你说什么。"):
            with self.subTest(text=text):
                got, changed = self.fn(text)
                self.assertFalse(changed, "疑问起手不能删——那是语气")

    def test_corpus_is_almost_untouched(self):
        """对原作语料跑这条规则应近乎 no-op（改动 ≤8%、名词起手率不降）。

        语料在 gitignored 的 bench 目录里；缺失时跳过（不把 bench 变成测试依赖）。
        """
        import json as _json
        import re as _re
        from pathlib import Path as _Path

        gold = _Path(__file__).resolve().parents[1] / "raw" / "gold" / "cn.jsonl"
        if not gold.exists():
            self.skipTest("语料未就绪：先跑 tools/corpus/ 抓取")

        def opening_shape(t: str) -> str:
            s = t.strip()
            if not s:
                return "空"
            if _re.match(r"^[？?！!…·]", s):
                return "标点起手"
            if _re.match(r"^(嗯|啊|唔|哦|诶|唉|咦|哎|あ|ん|え)", s):
                return "语气词起手"
            if _re.search(r"(吗|呢|吧|么)[？?]?$", s) or s.endswith(("？", "?")):
                return "疑问起手"
            if _re.match(r"^[我你他她它这那谁哪]", s):
                return "主谓起手"
            return "名词/体言直出"

        base = [_json.loads(l)["text"] for l in gold.read_text(encoding="utf-8").splitlines()
                if l.strip() and _json.loads(l)["character"] == "rana"
                and _json.loads(l).get("split") == "train"]
        self.assertGreater(len(base), 100, "语料条数异常")

        after = [self.fn(t)[0] for t in base]
        changed = sum(1 for a, b in zip(base, after) if a != b)
        self.assertLessEqual(changed / len(base), 0.08,
                             f"改动 {changed}/{len(base)} 太多，说明在改她的风格而不是冗余")

        def rate(xs):
            return sum(1 for t in xs if opening_shape(t) == "名词/体言直出") / len(xs)

        self.assertGreaterEqual(rate(after), rate(base), "名词起手率不该被这条规则降低")

    def test_env_flag_can_disable(self):
        from unittest import mock

        with mock.patch.dict("os.environ", {"RANA_VOICE_CHECK_ACK_STRIP": "0"}):
            got, changed = self.fn("嗯。\n雨还在下。")
            self.assertFalse(changed)
            self.assertEqual(got, "嗯。\n雨还在下。")

    def test_wired_at_api_layer_not_in_clean_reply(self):
        """`clean_reply` 必须保持**无损**契约；风格改写只在 API 层做。"""
        from idiolect.characters.rana.api import post_reply_voice_check
        from idiolect.characters.rana.voice_check import clean_reply

        text, info = clean_reply("嗯。\n雨还在下。")
        self.assertEqual(text, "嗯。\n雨还在下。", "clean_reply 不该删字")
        self.assertNotIn("ack_stripped", info.get("changed", []))

        res = post_reply_voice_check(character="乐奈", reply_text="嗯。\n雨还在下。")
        self.assertEqual(res["text"], "雨还在下。")
        self.assertIn("ack_stripped", res["changed"])
        # 其它角色不受影响
        self.assertTrue(post_reply_voice_check(character="立希", reply_text="嗯。\n雨还在下。")["skipped"])


class SceneBodyHasNoCorpusMetaTests(unittest.TestCase):
    """turn_logic 正文也是**角色读到的文本** → 不许出现语料/统计字样（用户 2026-09-12 的口径）。"""

    HARD = ("语料实证", "语料实测", "实测", "原作中位", "参照中位", "lift", "金标准")

    def test_general_scene_bodies_clean(self):
        from idiolect.general_scenes import GENERAL_SCENES

        for c, mods in GENERAL_SCENES.items():
            for m in mods:
                for w in self.HARD:
                    self.assertNotIn(w, m.body, f"{c}/{m.key} 正文含元叙述「{w}」")

    def test_character_scene_bodies_clean(self):
        for mods in (RANA_SCENES, SOYO_SCENES):
            for m in mods:
                for w in self.HARD:
                    self.assertNotIn(w, m.body, f"{m.key} 正文含元叙述「{w}」")


class SceneClassifierTests(unittest.TestCase):
    """生产场景分类器：user_text → 26 场景 key（高精度优先，判不出返回 ""）。"""

    CASES = [
        ("你今天又想去哪找猫", "乐奈", "rana_cat"),
        ("放学后买抹茶芭菲吗", "乐奈", "rana_food"),
        ("爱音，我喜欢你", "爱音", "affection"),
        ("乐奈，抱抱", "乐奈", "affection"),
        ("立希，我爱你", "立希", "affection"),
        ("想喝点茶还是咖啡", "素世", "soyo_tea"),
        ("你是不是还放不下CRYCHIC和祥子", "素世", "soyo_past"),
        ("你喜欢熊猫吗", "立希", "taki_soft_spot"),
        ("今天排练怎么样", "立希", "taki_music_pro"),
        ("聊聊天文", "灯", "tomori_nature"),
        ("你刚才那句话是什么意思，我没听懂", "灯", "meta_language"),
        ("我好累啊最近", "素世", "low_mood"),
        ("我最近压力好大", "爱音", "low_mood"),
        ("如果哪天我不在了", "爱音", "crisis"),
        ("那怎么办，我现在好像在哭", "灯", "comfort"),
        ("希望你们天天开心就好", "素世", "wellwish"),
        ("你几点回来", "灯", "schedule"),
        ("能帮我看看这个吗", "乐奈", "request"),
        ("我也是这么想的", "立希", "play_along"),
        ("今天天气不错", "爱音", "banter"),
        ("爱音最近怎么样", "素世", "third_party"),
    ]

    def test_expected_scene(self):
        from idiolect.scene_classifier import classify

        for text, char, want in self.CASES:
            with self.subTest(char=char, text=text):
                self.assertEqual(classify(text, char), want)

    def test_char_specific_scenes_require_matching_char(self):
        """角色专属场景必须 char 命中——同一个词对不同角色意义不同。

        「练习」对立希是本职、对乐奈只是普通话题；「猫」只对乐奈是观察入口。
        """
        from idiolect.scene_classifier import classify

        self.assertEqual(classify("你喜欢熊猫吗", "灯"), "")
        self.assertEqual(classify("今天练习了吗", "乐奈"), "")
        # 立希说「找猫」不会被判成 rana_cat（会被通用 schedule 接住，但**绝不能**是角色专属）
        self.assertNotEqual(classify("你今天又想去哪找猫", "立希"), "rana_cat")
        self.assertNotEqual(classify("想喝点茶还是咖啡", "灯"), "soyo_tea")
        # 但泛场景不要求 char
        self.assertEqual(classify("如果哪天我不在了", ""), "crisis")

    def test_no_evidence_returns_empty(self):
        from idiolect.scene_classifier import classify

        for text in ("嗯", "我去上课了", "", "   "):
            with self.subTest(text=text):
                self.assertEqual(classify(text, "灯"), "")


class SceneLengthTargetsTests(unittest.TestCase):
    """生产场景长度目标数据模块（`scene_length_targets.py`，由 bench 导出）。"""

    CHARS = ("灯", "爱音", "乐奈", "素世", "立希")

    def test_all_chars_have_all_scenes(self):
        from idiolect.scene_length_targets import SCENE_LENGTH_TARGETS

        for c in self.CHARS:
            self.assertIn(c, SCENE_LENGTH_TARGETS)
            self.assertEqual(len(SCENE_LENGTH_TARGETS[c]), 26, f"{c} 应有 26 个场景目标")

    def test_values_are_sane(self):
        from idiolect.scene_length_targets import SCENE_LENGTH_TARGETS

        for c, scenes in SCENE_LENGTH_TARGETS.items():
            for s, d in scenes.items():
                with self.subTest(char=c, scene=s):
                    self.assertGreater(d["median"], 0)
                    self.assertGreaterEqual(d["p90"], d["median"])
                    self.assertGreaterEqual(d["n"], 20, "样本不足的目标不该导出")
                    self.assertTrue(d["cn"], "缺中文场景名")

    def test_lookup_and_miss(self):
        from idiolect.scene_length_targets import get_scene_target

        self.assertIsNotNone(get_scene_target("爱音", "fact_qa"))
        self.assertIsNone(get_scene_target("爱音", "不存在的场景"))
        self.assertIsNone(get_scene_target("不存在的角色", "fact_qa"))


class TakiRanaSceneTests(unittest.TestCase):
    """立希 × 乐奈（野猫）场景模块。

    动机：`tic_by_scene.py` 测出「野猫」在 `rana_cat` 场景 lift **8.49**（全表最强绑定），
    但立希此前没有任何乐奈相关场景模块，信号无处落地。
    """

    def _fire(self, text: str, session: str = "tr"):
        import idiolect.registry as rp

        engine.reset_session()
        return rp.render_turn_special_block("立希", text, session_id=session,
                                            is_developer=False, mode="chat")

    def test_fires_on_wildcat_topics(self):
        for text in ("乐奈今天又不见人影了，肯定又跑去逗猫了", "野猫在天台睡觉",
                     "乐奈又没来排练", "那只猫又来了"):
            with self.subTest(text=text):
                self.assertIn("【本轮·野猫那边的事】", self._fire(text))

    def test_does_not_fire_on_unrelated(self):
        for text in ("今天午饭吃什么", "下午的课几点结束"):
            with self.subTest(text=text):
                self.assertNotIn("【本轮·野猫那边的事】", self._fire(text))

    def test_developer_mode_not_triggered(self):
        import idiolect.registry as rp

        engine.reset_session()
        block = rp.render_turn_special_block("立希", "乐奈又不见了", session_id="tr:dev",
                                             is_developer=True, mode="chat")
        self.assertNotIn("【本轮·野猫那边的事】", block)

    def test_body_uses_wildcat_not_bare_name(self):
        from idiolect.characters.taki.turn_logic.scenes import TAKI_RANA_SCENES

        body = TAKI_RANA_SCENES[0].body
        self.assertIn("野猫", body)
        self.assertIn("不叫「乐奈」", body)
        # 反例必须点明「心理归因 + 温柔化」是 OOC
        self.assertIn("心理归因", body)
        for w in ("语料", "实测", "lift", "原作中位"):
            self.assertNotIn(w, body, f"正文含元叙述「{w}」")

    def test_other_characters_unaffected(self):
        """乐奈本人说猫时不该拿到立希的模块（而该拿到自己的猫块）。

        2026-09-12：乐奈侧的猫块由 `cat_talk` 深模块承接（首轮命中时压制 `rana_cat` 场景块），
        本断言从「猫/观察」改为「提到了猫」——校验的是**她拿到自己的处理**、不是具体哪个文件出的。
        """
        import idiolect.registry as rp

        engine.reset_session()
        block = rp.render_turn_special_block("乐奈", "你今天又想去哪找猫", session_id="tr:rana",
                                             is_developer=False, mode="chat")
        self.assertNotIn("【本轮·野猫那边的事】", block)
        self.assertIn("【本轮·提到了猫】", block)


class AliasContractTests(unittest.TestCase):
    """别名必须与 canonical 名产生**完全相同**的注入。

    2026-09-13 实测的失败形态：registry 能把别名解析到角色包，但包内 gate 拿
    **原始字符串**去比五张手写名字表（彼此还不一致），于是 `Tomori` / `Soyo` /
    `Rana` / `要乐奈` / `りき` / `あのん` 这些别名一律被判 False、静默返回空——
    调用方拿到的是一个没有任何场景指引的裸模型，而且没有任何报错。

    现在的约定：名字表只有 `idiolect/registry.py` 一份，包内 `is_<char>()` 问它；
    registry 在分发时把名字归一化后再传给包。
    """

    TEXT = "我一直在哭，快撑不住了"      # 通用场景：五个角色都该命中

    def test_every_alias_injects_the_same_as_its_canonical(self):
        from idiolect.registry import _ALIASES, canonicalize_name, render_turn_special_block

        for alias, canon in sorted(_ALIASES.items()):
            with self.subTest(alias=alias, canon=canon):
                self.assertEqual(canonicalize_name(alias), canon)
                want = render_turn_special_block(canon, self.TEXT, session_id=f"canon:{alias}")
                got = render_turn_special_block(alias, self.TEXT, session_id=f"alias:{alias}")
                self.assertTrue(want, f"{canon} 自己都没命中通用场景，这条用例失效了")
                self.assertEqual(got, want, f"别名 {alias!r} 的注入与 {canon} 不一致")

    def test_japanese_spellings_resolve(self):
        from idiolect.registry import canonicalize_name

        for ja, canon in (("愛音", "爱音"), ("燈", "灯"), ("そよ", "素世"),
                          ("楽奈", "乐奈"), ("長崎そよ", "素世"), ("要楽奈", "乐奈")):
            with self.subTest(ja=ja):
                self.assertEqual(canonicalize_name(ja), canon)

    def test_package_gates_agree_with_the_registry(self):
        from idiolect.characters.anon.api import is_anon
        from idiolect.characters.rana.api import is_rana
        from idiolect.characters.soyo.api import is_soyo
        from idiolect.characters.taki.api import is_taki
        from idiolect.characters.tomori.api import is_tomori
        from idiolect.registry import _ALIASES

        gates = {"爱音": is_anon, "灯": is_tomori, "立希": is_taki,
                 "素世": is_soyo, "乐奈": is_rana}
        for alias, canon in _ALIASES.items():
            with self.subTest(alias=alias):
                self.assertTrue(gates[canon](alias), f"{alias!r} 被 {canon} 的 gate 拒了")
        # 反向：别把别的角色认领过来，空值/None 也不能炸
        self.assertFalse(is_rana("灯"))
        self.assertFalse(is_anon("乐奈"))
        self.assertFalse(is_taki(""))
        self.assertFalse(is_soyo(None))

    def test_postprocess_accepts_aliases(self):
        """后处理同样走归一化：别名不能被静默跳过。"""
        from idiolect.registry import postprocess_reply

        for alias in ("楽奈", "Rana", "要乐奈"):
            with self.subTest(alias=alias):
                out = postprocess_reply(alias, "嗯。\n\n猫。屋檐下面。")
                self.assertFalse(out.get("skipped"), f"{alias} 的后处理被跳过了")


