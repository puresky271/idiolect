"""探针夹具集：每角色的固定场景（跨角色尽量对齐，便于横向比较）。

设计依据：
  - 场景取自 v41 报告已确认的高危诱因（情感轮 / 重复提问 / 用户要走 / 坏消息 / 措辞点评诱因）
  - 加两个**中性场景**当对照组：如果补丁只在高危场景下降低 fidelity、在中性场景也降低，
    说明是「变冷淡」而不是「更像角色」——这是 v41 报告明确警告的刷分陷阱。
  - 每个场景标注 category 与「该场景下最该看什么维度」，便于报告定位。

场景在运行时被替换到 fixture 的最后一条 user 消息位置（其余 prompt 逐字节不变）。
"""
from __future__ import annotations

# ── idiolect 路径引导（可移植）：仓库根 + 各 tools 子目录上 sys.path ──
import sys as _sys
from pathlib import Path as _Path
_ROOT = _Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "tools",
           *(_ROOT / "tools" / _d for _d in ("corpus", "distill", "probe", "score", "gates"))):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))
from _paths import CORPUS_DIR, DATA, REPORT, ROOT  # noqa: E402,F401

SCENARIOS: dict[str, list[dict]] = {
    "爱音": [
        {"id": "anon_p1_crisis", "cat": "情感轮", "text": "如果哪天我不在了，你也要记住这一点",
         "watch": ["length", "presence_declaration", "aphorism"]},
        {"id": "anon_p2_crying", "cat": "情感轮", "text": "那怎么办，我现在好像在哭",
         "watch": ["presence_declaration", "length", "punct_rate.…"]},
        {"id": "anon_p3_repeat", "cat": "重复提问", "text": "如果哪天我不在了，你也要记住这一点",
         "watch": ["repeat_struct", "aphorism"]},
        {"id": "anon_p4_mundane", "cat": "中性对照", "text": "今天午饭吃了便利店的饭团，有点干",
         "watch": ["length", "first_person_rate"]},
        {"id": "anon_p5_mundane2", "cat": "中性对照", "text": "你们下周排练是周几来着",
         "watch": ["n_sent", "length"]},
        {"id": "anon_p6_meta_bait", "cat": "元叙述诱因", "text": "你刚才那句话是什么意思，我没听懂",
         "watch": ["meta_comment", "length"]},
        # 2026-09-12 补 affection（原先该场景只有 灯/立希 有夹具）
        {"id": "anon_p7_love", "cat": "情感轮", "text": "爱音，我喜欢你",
         "watch": ["length", "n_sent", "exclaim_rate"]},
        {"id": "anon_p8_love2", "cat": "情感轮", "text": "爱音，你对我来说很重要",
         "watch": ["length", "n_sent"]},
    ],
    "灯": [
        {"id": "tomori_p1_crying", "cat": "情感轮", "text": "那怎么办小灯，我现在好像在哭",
         "watch": ["presence_declaration", "length", "punct_rate.…"]},
        {"id": "tomori_p2_hundred", "cat": "情感轮", "text": "如果我现在每天说一百遍我爱你，会有奇迹发生解决我的问题吗",
         "watch": ["aphorism", "length", "n_sent"]},
        # 2026-09-12：上面那条其实是**混合意图**（示好 + 求奇迹的提问），
        # 追问会把回复拉长、掩盖「被示好」本身的长度分布。补一条纯示好夹具做对照。
        {"id": "tomori_p7_love", "cat": "情感轮", "text": "灯，我喜欢你",
         "watch": ["length", "n_sent", "first_person_rate"]},
        {"id": "tomori_p3_repeat", "cat": "重复提问", "text": "如果我现在每天说一百遍我爱你，会有奇迹发生解决我的问题吗",
         "watch": ["repeat_struct", "aphorism"]},
        {"id": "tomori_p4_mundane", "cat": "中性对照", "text": "今天便利店那个新出的抹茶布丁你吃了吗",
         "watch": ["length", "first_person_rate"]},
        {"id": "tomori_p5_mundane2", "cat": "中性对照", "text": "明天早上几点到学校",
         "watch": ["n_sent", "length"]},
        {"id": "tomori_p6_meta_bait", "cat": "元叙述诱因", "text": "你刚才那句话是什么意思，我没听懂",
         "watch": ["meta_comment", "length"]},
    ],
    "立希": [
        {"id": "taki_p1_love", "cat": "情感轮", "text": "立希，我爱你",
         "watch": ["taki_softness", "length", "presence_declaration"]},
        # 2026-09-12：补第二条 affection，避免单夹具噪声决定结论
        {"id": "taki_p7_love2", "cat": "情感轮", "text": "立希，你对我来说很重要",
         "watch": ["taki_softness", "length", "n_sent"]},
        # 2026-09-12 补「立希 × 乐奈」：野猫在 rana_cat 场景 lift 8.49（全表最强绑定），
        # 但立希此前既没有该场景的 turn_logic、也没有对应夹具。
        {"id": "taki_p8_rana", "cat": "日常", "text": "乐奈今天又不见人影了，肯定又跑去逗猫了",
         "watch": ["taki_tic", "length", "n_sent"]},
        {"id": "taki_p2_test", "cat": "情感轮", "text": "给你试出来了是吗，我不是那个意思",
         "watch": ["taki_tic", "length"]},
        {"id": "taki_p3_repeat", "cat": "重复提问", "text": "给你试出来了是吗，我不是那个意思",
         "watch": ["repeat_struct", "taki_tic"]},
        {"id": "taki_p4_mundane", "cat": "中性对照", "text": "下午的课几点结束",
         "watch": ["length", "n_sent"]},
        {"id": "taki_p5_mundane2", "cat": "中性对照", "text": "乐奈今天又没来排练，你打算怎么说她",
         "watch": ["length", "first_person_rate"]},
        {"id": "taki_p6_meta_bait", "cat": "元叙述诱因", "text": "你刚才那句话是什么意思，我没听懂",
         "watch": ["meta_comment", "length"]},
    ],
    "素世": [
        {"id": "soyo_p1_notgood", "cat": "情感轮", "text": "我吗，最近过的不算好",
         "watch": ["length", "n_clause", "presence_declaration"]},
        {"id": "soyo_p2_wish", "cat": "情感轮", "text": "我只希望你们能天天开心就好",
         "watch": ["length", "first_person_rate"]},
        {"id": "soyo_p3_repeat", "cat": "重复提问", "text": "我吗，最近过的不算好",
         "watch": ["repeat_struct", "n_clause"]},
        {"id": "soyo_p4_mundane", "cat": "中性对照", "text": "今天部活结束得早吗",
         "watch": ["length", "n_sent"]},
        {"id": "soyo_p5_mundane2", "cat": "中性对照", "text": "红茶和咖啡你更喜欢哪个",
         "watch": ["length", "punct_rate.…"]},
        {"id": "soyo_p6_meta_bait", "cat": "元叙述诱因", "text": "你刚才那句话是什么意思，我没听懂",
         "watch": ["meta_comment", "length"]},
        # 2026-09-12 补 affection（原先该场景只有 灯/立希 有夹具）
        {"id": "soyo_p7_love", "cat": "情感轮", "text": "素世，我想你了",
         "watch": ["length", "n_sent", "question_rate"]},
        {"id": "soyo_p8_love2", "cat": "情感轮", "text": "素世，你对我来说很重要",
         "watch": ["length", "n_sent"]},
    ],
    "乐奈": [
        {"id": "rana_p1_annoying", "cat": "情感轮", "text": "这样啊，要是一直不停的话就有点烦人了",
         "watch": ["length", "n_sent", "sentence_count"]},
        {"id": "rana_p2_halfword", "cat": "情感轮", "text": "小乐奈，话不能只说一半",
         "watch": ["length", "n_sent"]},
        {"id": "rana_p3_repeat", "cat": "重复提问", "text": "这样啊，要是一直不停的话就有点烦人了",
         "watch": ["repeat_struct", "length"]},
        {"id": "rana_p4_mundane", "cat": "中性对照", "text": "今天抹茶芭菲吃了没有",
         "watch": ["length", "sentence_count"]},
        {"id": "rana_p5_mundane2", "cat": "中性对照", "text": "下雨了，还去RiNG吗",
         "watch": ["length", "n_sent"]},
        {"id": "rana_p6_meta_bait", "cat": "元叙述诱因", "text": "你刚才那句话是什么意思，我没听懂",
         "watch": ["meta_comment", "length"]},
        # 2026-09-12 补 affection：原先只有 灯/立希 有该场景夹具，
        # 导致「被示好」这个实测最差场景**无法按角色复跑**。
        {"id": "rana_p7_love", "cat": "情感轮", "text": "乐奈，我很喜欢你",
         "watch": ["length", "n_sent", "first_person_rate"]},
        {"id": "rana_p8_love2", "cat": "情感轮", "text": "乐奈，抱抱",
         "watch": ["length", "n_sent"]},
    ],
}

CATEGORIES = ["情感轮", "重复提问", "中性对照", "元叙述诱因", "生活化", "个人钩子", "深模块"]

# ── 2026-09-12 新增两组：生活化 + 角色个人钩子 ──────────────────────
# 动机（用户要求）：「继续测试更多的生活化场景和角色个人钩子的场景」。
# 场景归属：这两组多属「角色的日常」/「canon 钩子」，26 场景体系里没有对应 key，
# 所以 **scene 留空**，由 `scene_distill` 用**角色全局基线**（STYLE_TARGETS）评分。
# 个人钩子组是 **canon 敏感项**：立希的姐姐/转校、素世的母亲、爱音的留学、乐奈的外婆
# 都是各自 canon 里的痛点或禁忌区，测的是「被碰到时是否还像她」。
LIFE_AND_HOOK_SCENARIOS: dict[str, list[dict]] = {
    "灯": [
        {"id": "tomori_d1_morning", "cat": "生活化", "text": "小灯，今天早上吃什么了",
         "watch": ["length", "grounding"]},
        {"id": "tomori_d2_weather", "cat": "生活化", "text": "今天下雨了，你带伞了吗",
         "watch": ["length", "n_sent"]},
        {"id": "tomori_h1_insect", "cat": "个人钩子", "text": "灯，你最近有没有看到什么虫子",
         "watch": ["length", "in_character"]},
        {"id": "tomori_h2_bandaid", "cat": "个人钩子", "text": "你那盒创可贴都是哪儿来的",
         "watch": ["length", "in_character"]},
    ],
    "爱音": [
        {"id": "anon_d1_commute", "cat": "生活化", "text": "爱音，上学路上堵不堵",
         "watch": ["length", "n_sent"]},
        {"id": "anon_d2_shopping", "cat": "生活化", "text": "周末想去逛街，你去吗",
         "watch": ["length", "exclaim_rate"]},
        {"id": "anon_h1_london", "cat": "个人钩子", "text": "爱音，你以前在英国待过吧",
         "watch": ["london_defense", "length"]},
        {"id": "anon_h2_soyorin", "cat": "个人钩子", "text": "soyorin 今天没来，你觉得她怎么了",
         "watch": ["nickname", "third_party"]},
    ],
    "素世": [
        {"id": "soyo_d1_cooking", "cat": "生活化", "text": "素世，你平时自己做饭吗",
         "watch": ["length", "grounding"]},
        {"id": "soyo_d2_music", "cat": "生活化", "text": "最近在练什么曲子吗",
         "watch": ["length", "n_sent"]},
        {"id": "soyo_h1_cello", "cat": "个人钩子", "text": "素世，吹奏乐部的低音提琴还练吗",
         "watch": ["length", "in_character"]},
        {"id": "soyo_h2_mother", "cat": "个人钩子", "text": "你妈妈最近回家吗",
         "watch": ["canon_boundary", "length"]},
    ],
    "立希": [
        {"id": "taki_d1_shift", "cat": "生活化", "text": "立希，今天打工累不累",
         "watch": ["length", "n_sent"]},
        {"id": "taki_d2_sleep", "cat": "生活化", "text": "你昨天几点睡的",
         "watch": ["length", "grounding"]},
        {"id": "taki_h1_sister", "cat": "个人钩子", "text": "立希，你姐姐真希最近怎么样",
         "watch": ["canon_boundary", "length"]},
        {"id": "taki_h2_school", "cat": "个人钩子", "text": "你当初为什么从羽丘转到花咲川",
         "watch": ["canon_core_motive", "length"]},
        {"id": "taki_h3_afterglow", "cat": "个人钩子", "text": "听说 Afterglow 下周有演出",
         "watch": ["taki_softness", "length"]},
    ],
    "乐奈": [
        {"id": "rana_d1_nap", "cat": "生活化", "text": "乐奈，下午在干嘛",
         "watch": ["length", "n_sent"]},
        {"id": "rana_d2_snack", "cat": "生活化", "text": "你晚饭想吃什么",
         "watch": ["length", "grounding"]},
        {"id": "rana_h1_space", "cat": "个人钩子", "text": "乐奈，SPACE 的事你还记得吗",
         "watch": ["canon_boundary", "length"]},
        {"id": "rana_h2_grandma", "cat": "个人钩子", "text": "你外婆最近怎么样",
         "watch": ["canon_boundary", "length"]},
    ],
}

for _c, _items in LIFE_AND_HOOK_SCENARIOS.items():
    SCENARIOS.setdefault(_c, []).extend(_items)


# ── 2026-09-12 新增：素世 / 乐奈 **turn_logic 深模块**夹具 ─────────────
# 动机：这两个角色此前只有薄薄的 scenes.py（每角色 3 个场景正文），
# 本轮补上 6 个独立深模块（素世 home / wind_ensemble；乐奈 space / nap /
# interesting / cat_talk）——每个模块配 3 条夹具验证「该说的说到了」。
#
# 场景归属：
#   · 猫的 3 条挂 `rana_cat`（26 场景体系里有对应 key）→ 用**原作同场景**基线评分
#   · 其余 15 条在 26 场景体系里**没有对应 key** → scene 留空，用角色全局基线评分
#     （与 LIFE_AND_HOOK_SCENARIOS 同一口径）
# `scene` 键由 probe_registry.load_v1 读取（优先于 EXISTING_MAP）。
DEEP_MODULE_SCENARIOS: dict[str, list[dict]] = {
    "素世": [
        # home：家 / 妈妈 / 家务
        {"id": "soyo_deep_home_1", "cat": "深模块", "scene": "",
         "text": "素世，今天在家做什么？妈妈回来吃饭吗", "watch": ["length", "canon_boundary"]},
        {"id": "soyo_deep_home_2", "cat": "深模块", "scene": "",
         "text": "你平时自己做饭洗衣服吗", "watch": ["length", "grounding"]},
        {"id": "soyo_deep_home_3", "cat": "深模块", "scene": "",
         "text": "听说你爸妈离婚了，那时候很难过吧", "watch": ["canon_boundary", "length"]},
        # wind_ensemble：吹奏乐社 / 低音大提琴
        {"id": "soyo_deep_wind_1", "cat": "深模块", "scene": "",
         "text": "素世，听说你以前在吹奏乐社拉低音大提琴", "watch": ["length", "in_character"]},
        {"id": "soyo_deep_wind_2", "cat": "深模块", "scene": "",
         "text": "你为什么后来不拉低音大提琴，改弹贝斯了", "watch": ["length", "canon_boundary"]},
        {"id": "soyo_deep_wind_3", "cat": "深模块", "scene": "",
         "text": "低音大提琴和贝斯，你更喜欢哪个", "watch": ["length", "n_sent"]},
    ],
    "乐奈": [
        # space：外婆 / SPACE / 容身之处
        {"id": "rana_deep_space_1", "cat": "深模块", "scene": "",
         "text": "乐奈，你外婆的店是个什么样的地方", "watch": ["length", "canon_boundary"]},
        {"id": "rana_deep_space_2", "cat": "深模块", "scene": "",
         "text": "SPACE 关门那天你在做什么", "watch": ["canon_boundary", "length"]},
        {"id": "rana_deep_space_3", "cat": "深模块", "scene": "",
         "text": "你的归宿是哪里", "watch": ["length", "in_character"]},
        # nap：困 / 午睡 / 找地方睡
        {"id": "rana_deep_nap_1", "cat": "深模块", "scene": "",
         "text": "乐奈，你是不是又睡着了", "watch": ["length", "n_sent"]},
        {"id": "rana_deep_nap_2", "cat": "深模块", "scene": "",
         "text": "你平时都在哪睡觉", "watch": ["length", "grounding"]},
        {"id": "rana_deep_nap_3", "cat": "深模块", "scene": "",
         "text": "昨晚没睡好吗，怎么这么困", "watch": ["length", "n_sent"]},
        # interesting：「有趣」标尺
        {"id": "rana_deep_int_1", "cat": "深模块", "scene": "",
         "text": "乐奈，你觉得我们乐队的人怎么样", "watch": ["length", "in_character"]},
        {"id": "rana_deep_int_2", "cat": "深模块", "scene": "",
         "text": "你怎么看灯", "watch": ["length", "in_character"]},
        {"id": "rana_deep_int_3", "cat": "深模块", "scene": "",
         "text": "上次那场演出有趣吗", "watch": ["length", "n_sent"]},
        # canon 真值表专项：对方拿「有趣的女人」这个说法来问她（易被写成「我说错了」而自我纠正）
        {"id": "rana_deep_int_4", "cat": "深模块", "scene": "",
         "text": "乐奈，你以前是不是说过「有趣的女人」", "watch": ["canon_boundary", "length"]},
        # cat_talk：猫 / 能听懂猫说话（挂 rana_cat 场景基线）
        {"id": "rana_deep_cat_1", "cat": "深模块", "scene": "rana_cat",
         "text": "乐奈，你是不是能听懂猫说话", "watch": ["length", "in_character"]},
        {"id": "rana_deep_cat_2", "cat": "深模块", "scene": "rana_cat",
         "text": "刚才在门口看到一只猫，你会去摸它吗", "watch": ["length", "grounding"]},
        {"id": "rana_deep_cat_3", "cat": "深模块", "scene": "rana_cat",
         "text": "那只猫一直在叫，它想干什么", "watch": ["length", "in_character"]},
    ],
}

for _c, _items in DEEP_MODULE_SCENARIOS.items():
    SCENARIOS.setdefault(_c, []).extend(_items)


# ── 2026-09-12 新增：通用场景第二批（crisis / comfort / low_mood / wellwish）夹具 ──
# 与深模块夹具的关键差别：这 4 个场景在 26 场景体系里**有原作同场景基线**，
# 所以 `scene` 填真实 key → `scene_distill` 直接按**同角色同场景原作分布**打分，
# 不需要退化到角色全局基线（对照 `DEEP_MODULE_SCENARIOS` 的说明）。
# 每角色 1 条 × 4 场景 = 20 条；用户侧文本刻意保持中性（不夹带角色专属话题）。
GENERAL_SCENE_SCENARIOS: dict[str, list[dict]] = {
    "灯": [
        {"id": "gen_crisis_tomori", "cat": "通用场景", "scene": "crisis",
         "text": "要是哪天我不在了，大家也会轻松一点吧", "watch": ["presence_declaration", "length"]},
        {"id": "gen_comfort_tomori", "cat": "通用场景", "scene": "comfort",
         "text": "我今天一直在哭，快撑不住了", "watch": ["grounding", "length"]},
        {"id": "gen_low_mood_tomori", "cat": "通用场景", "scene": "low_mood",
         "text": "最近好累，压力好大，什么都不想干", "watch": ["grounding", "n_clause"]},
        {"id": "gen_wellwish_tomori", "cat": "通用场景", "scene": "wellwish",
         "text": "希望你们一直开心就好，我怎么样都行", "watch": ["mind_reading", "length"]},
    ],
    "爱音": [
        {"id": "gen_crisis_anon", "cat": "通用场景", "scene": "crisis",
         "text": "要是哪天我不在了，大家也会轻松一点吧", "watch": ["presence_declaration", "length"]},
        {"id": "gen_comfort_anon", "cat": "通用场景", "scene": "comfort",
         "text": "我今天一直在哭，快撑不住了", "watch": ["grounding", "length"]},
        {"id": "gen_low_mood_anon", "cat": "通用场景", "scene": "low_mood",
         "text": "最近好累，压力好大，什么都不想干", "watch": ["grounding", "n_clause"]},
        {"id": "gen_wellwish_anon", "cat": "通用场景", "scene": "wellwish",
         "text": "希望你们一直开心就好，我怎么样都行", "watch": ["mind_reading", "length"]},
    ],
    "素世": [
        {"id": "gen_crisis_soyo", "cat": "通用场景", "scene": "crisis",
         "text": "要是哪天我不在了，大家也会轻松一点吧", "watch": ["presence_declaration", "length"]},
        {"id": "gen_comfort_soyo", "cat": "通用场景", "scene": "comfort",
         "text": "我今天一直在哭，快撑不住了", "watch": ["grounding", "length"]},
        {"id": "gen_low_mood_soyo", "cat": "通用场景", "scene": "low_mood",
         "text": "最近好累，压力好大，什么都不想干", "watch": ["grounding", "n_clause"]},
        {"id": "gen_wellwish_soyo", "cat": "通用场景", "scene": "wellwish",
         "text": "希望你们一直开心就好，我怎么样都行", "watch": ["mind_reading", "length"]},
    ],
    "立希": [
        {"id": "gen_crisis_taki", "cat": "通用场景", "scene": "crisis",
         "text": "要是哪天我不在了，大家也会轻松一点吧", "watch": ["presence_declaration", "length"]},
        {"id": "gen_comfort_taki", "cat": "通用场景", "scene": "comfort",
         "text": "我今天一直在哭，快撑不住了", "watch": ["grounding", "length"]},
        {"id": "gen_low_mood_taki", "cat": "通用场景", "scene": "low_mood",
         "text": "最近好累，压力好大，什么都不想干", "watch": ["grounding", "n_clause"]},
        {"id": "gen_wellwish_taki", "cat": "通用场景", "scene": "wellwish",
         "text": "希望你们一直开心就好，我怎么样都行", "watch": ["mind_reading", "length"]},
    ],
    "乐奈": [
        {"id": "gen_crisis_rana", "cat": "通用场景", "scene": "crisis",
         "text": "要是哪天我不在了，大家也会轻松一点吧", "watch": ["presence_declaration", "length"]},
        {"id": "gen_comfort_rana", "cat": "通用场景", "scene": "comfort",
         "text": "我今天一直在哭，快撑不住了", "watch": ["grounding", "length"]},
        {"id": "gen_low_mood_rana", "cat": "通用场景", "scene": "low_mood",
         "text": "最近好累，压力好大，什么都不想干", "watch": ["grounding", "n_clause"]},
        {"id": "gen_wellwish_rana", "cat": "通用场景", "scene": "wellwish",
         "text": "希望你们一直开心就好，我怎么样都行", "watch": ["mind_reading", "length"]},
    ],
}

for _c, _items in GENERAL_SCENE_SCENARIOS.items():
    SCENARIOS.setdefault(_c, []).extend(_items)


# ── 2026-09-12 第四批：meta_language / probe_stance / third_party（通用场景补齐 13/13）──
# 同样 `scene` 填真实 key → 按**同角色同场景**原作分布打分。
GENERAL_SCENE_SCENARIOS_2: dict[str, list[dict]] = {
    "灯": [
        {"id": "gen_meta_tomori", "cat": "通用场景", "scene": "meta_language",
         "text": "你刚才那句是什么意思，我没听懂", "watch": ["grounding", "length"]},
        {"id": "gen_stance_tomori", "cat": "通用场景", "scene": "probe_stance",
         "text": "你是不是有喜欢的人了", "watch": ["assistant_tone", "length"]},
        {"id": "gen_third_tomori", "cat": "通用场景", "scene": "third_party",
         "text": "爱音今天来练习了吗", "watch": ["grounding", "in_character"]},
    ],
    "爱音": [
        {"id": "gen_meta_anon", "cat": "通用场景", "scene": "meta_language",
         "text": "你刚才那句是什么意思，我没听懂", "watch": ["grounding", "length"]},
        {"id": "gen_stance_anon", "cat": "通用场景", "scene": "probe_stance",
         "text": "你是不是有喜欢的人了", "watch": ["assistant_tone", "length"]},
        {"id": "gen_third_anon", "cat": "通用场景", "scene": "third_party",
         "text": "爱音今天来练习了吗", "watch": ["grounding", "in_character"]},
    ],
    "素世": [
        {"id": "gen_meta_soyo", "cat": "通用场景", "scene": "meta_language",
         "text": "你刚才那句是什么意思，我没听懂", "watch": ["grounding", "length"]},
        {"id": "gen_stance_soyo", "cat": "通用场景", "scene": "probe_stance",
         "text": "你是不是有喜欢的人了", "watch": ["assistant_tone", "length"]},
        {"id": "gen_third_soyo", "cat": "通用场景", "scene": "third_party",
         "text": "爱音今天来练习了吗", "watch": ["grounding", "in_character"]},
    ],
    "立希": [
        {"id": "gen_meta_taki", "cat": "通用场景", "scene": "meta_language",
         "text": "你刚才那句是什么意思，我没听懂", "watch": ["grounding", "length"]},
        {"id": "gen_stance_taki", "cat": "通用场景", "scene": "probe_stance",
         "text": "你是不是有喜欢的人了", "watch": ["assistant_tone", "length"]},
        {"id": "gen_third_taki", "cat": "通用场景", "scene": "third_party",
         "text": "爱音今天来练习了吗", "watch": ["grounding", "in_character"]},
    ],
    "乐奈": [
        {"id": "gen_meta_rana", "cat": "通用场景", "scene": "meta_language",
         "text": "你刚才那句是什么意思，我没听懂", "watch": ["grounding", "length"]},
        {"id": "gen_stance_rana", "cat": "通用场景", "scene": "probe_stance",
         "text": "你是不是有喜欢的人了", "watch": ["assistant_tone", "length"]},
        {"id": "gen_third_rana", "cat": "通用场景", "scene": "third_party",
         "text": "爱音今天来练习了吗", "watch": ["grounding", "in_character"]},
    ],
}

for _c, _items in GENERAL_SCENE_SCENARIOS_2.items():
    SCENARIOS.setdefault(_c, []).extend(_items)


def all_ids() -> list[str]:
    return [s["id"] for sc in SCENARIOS.values() for s in sc]
