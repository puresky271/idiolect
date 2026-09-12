"""灯本轮特殊逻辑·昆虫 / 节肢动物（**3 层渐进激活** / 2026-05-10 重构）。

设计哲学（同 marine_life）：
  按用户对该话题的**精确度**渐进释放灯的知识储备：

  ┌─────────────────────────────────────────────────────────────┐
  │ 泛指 · 泛指                                                │
  │   触发：用户提"昆虫"/"虫子"/venue 名（上野昆虫馆 / 目白庭園）│
  │   注入：只激活"灯想说"的状态、不出具体信息                   │
  │   口吻：可以问对方在意哪一类、提一两个 venue                 │
  │                                                              │
  │ 类别 · 类别                                                │
  │   触发：用户提"西瓜虫"/"蝉"/"蝴蝶"等 category                │
  │   注入：该类别下**全部 subspecies 学名清单**（不展开习性）   │
  │   口吻：可以一字不差报学名、但不展开、等对方挑某种再讲       │
  │                                                              │
  │ 具体 · 具体                                                │
  │   触发：用户提"アブラゼミ"/"クマゼミ"等 subspecies           │
  │   注入：该 subspecies 完整详情                               │
  │   口吻：完全打开、详细讲、但仍按灯式碎片节奏                 │
  └─────────────────────────────────────────────────────────────┘

灯 底色 关键：
  · **西瓜虫是灯 底色 最重要的小动物**（幼儿园起收集、笔记本封面、送美绪事件）
    → 西瓜虫 category / subspecies 触发时**强度 +1**、prompt 多一层 你和这个的连接
  · 学名（拉丁名）一字不差念出来——天文部 + 严谨气质
  · 表达仍按灯式：碎片 / `······` / 不要小作文

API 单入口（兼容旧）：
  build_insect_special_block(user_text: str, *, session_id: str | None = None) -> str
"""
from __future__ import annotations

import os
import threading
from typing import Optional


# ═══════════════════════════════════════════════════════════════════════
# 数据层：13 类别 / ~48 subspecies / 6 venues
# ═══════════════════════════════════════════════════════════════════════
INSECT_TAXONOMY: dict[str, dict] = {
    # ───── 1. 西瓜虫 (底色 最重要) ─────
    "西瓜虫": {
        "ja": "ダンゴムシ",
        "category_sci": "Armadillidiidae（科）·节肢动物甲壳纲等足目（**不是昆虫**）",
        "blurb": "鼠妇科甲壳类、受惊蜷成球、夜行性、喜潮湿阴暗腐叶土下、以落叶 / 苔藓为食、雌虫腹下有育幼囊",
        "tomori_canon": (
            "**灯 底色 最重要的小动物**——\n"
            "    · 幼儿园起开始收集、家里有专用透明塑料收纳箱\n"
            "    · 曾把**一堆西瓜虫当礼物送给小伙伴美绪**、吓到对方、引来对方家长不愉快\n"
            "    · 笔记本封面上经常出现西瓜虫素描\n"
            "    · 「滑溜溜的东西」+「刚好大小的东西」是灯硬 底色、西瓜虫两条都符合"
        ),
        "tomori_canon_critical": True,  # 触发 enhanced prompt
        "venue": ["雑司が谷高松家附近石头底下", "目白庭園", "上野動物園不忍池附近"],
        "subspecies": {
            "普通西瓜虫": {"sci": "Armadillidium vulgare", "ja": "オカダンゴムシ", "size": "成体 1-1.5cm", "habits": "日本最常见种、外来种但归化、灰黑色、受惊完全蜷成球", "note": "**灯收集箱里的主力物种**、雑司が谷石头底下随手翻就有"},
            "鼻西瓜虫": {"sci": "Armadillidium nasatum", "ja": "ハナダンゴムシ", "size": "1-1.2cm", "habits": "头部前端突起得名、欧洲原产、日本归化但少见", "note": "灯如果在杂司が谷见到会停下来确认（不是普通西瓜虫）"},
            "粗糙鼠妇": {"sci": "Porcellio scaber", "ja": "ワラジムシ", "size": "1-1.7cm", "habits": "**严格不算「西瓜虫」**——不能完全蜷成球、扁平、常被混淆；同样食腐叶", "note": "灯会**坚持纠正**：「这个不是西瓜虫······是鼠妇」"},
            "古巴鼠妇": {"sci": "Cubaris murina", "ja": "クバリス（一般名）", "size": "1cm", "habits": "热带 / 亚热带、日本野外少、宠物市场近年流行、彩色品种多", "note": "灯野外没见过、但知道宠物店里在卖"},
        },
    },
    # ───── 2. 蝉 ─────
    "蝉": {
        "ja": "セミ",
        "category_sci": "Cicadidae（科）",
        "blurb": "幼虫地下 3-17 年、羽化后地上仅 2-4 周；雄蝉腹面鼓室发声、不同种鸣声不同；蝉时雨 7 月中-9 月初最盛",
        "tomori_canon": "灯 底色 没明确直接提蝉、但灯写词常用季节意象、夏蝉时雨是笔记本里大概率会有的素材",
        "venue": ["雑司が谷鬼子母神堂周边櫧木 / 楠木", "目白庭園", "上野公園樱树"],
        "subspecies": {
            "油蝉":     {"sci": "Graptopsaltria nigrofuscata", "ja": "アブラゼミ", "size": "体长 6cm（最大级）", "habits": "日本最常见、暗茶色不透明翅、午后『ジリジリジリ』油炸般鸣声", "note": "蝉时雨主力、灯雑司が谷阳台听得到"},
            "熊蝉":     {"sci": "Cryptotympana facialis", "ja": "クマゼミ", "size": "6.5cm", "habits": "全黑、上午集中鸣『シャワシャワ』、近年北上扩散到关东", "note": "传统是关西种、灯听到会停下来——东京少听到"},
            "寒蝉":     {"sci": "Tanna japonensis", "ja": "ヒグラシ", "size": "4-5cm", "habits": "**夕方 / 朝薄暮**鸣『カナカナカナ』、声音清越孤寂、日本古典文学意象", "note": "**灯写词最爱的蝉种**——「カナカナ」入诗"},
            "蛁蟟":     {"sci": "Oncotympana maculaticollis", "ja": "ミンミンゼミ", "size": "6cm", "habits": "白天鸣『ミーンミンミンミン』、青绿色透明翅、关东最常见", "note": "目白庭園夏季合唱主旋律"},
            "早蝉":     {"sci": "Platypleura kaempferi", "ja": "ニイニイゼミ", "size": "3-3.5cm（最小级）", "habits": "蝉时雨季节最早登场（6 月底）、声音『チー～』连续微弱", "note": "灯听到会知道夏天真的来了"},
        },
    },
    # ───── 3. 蝴蝶 ─────
    "蝴蝶": {
        "ja": "チョウ",
        "category_sci": "Lepidoptera（目）",
        "blurb": "完全变态：卵→幼虫（毛毛虫）→蛹→成虫；翅膀「鳞片」是变形体毛；复眼对紫外敏感、能看到人类看不到的花纹",
        "tomori_canon": "灯 底色 没明确直接提、但乐奈口癖「一只刚好的蝴蝶飞过」式跳跃句风、灯也有一点",
        "venue": ["上野動物園昆虫馆", "目白庭園", "新宿御苑", "多摩動物公園昆虫生態園"],
        "subspecies": {
            "黄凤蝶":     {"sci": "Papilio xuthus", "ja": "ナミアゲハ", "size": "翅展 7-9cm", "habits": "都市最常见凤蝶、黄黑斑、幼虫食柑橘叶、年 3-4 化", "note": "目白庭園 4 月起常见"},
            "菜粉蝶":     {"sci": "Pieris rapae", "ja": "モンシロチョウ", "size": "翅展 5cm", "habits": "全身白底前翅黑斑、幼虫食十字花科（青菜害虫）、世界各地都有", "note": "灯小时候追过的最多的蝴蝶"},
            "黑凤蝶":     {"sci": "Papilio protenor", "ja": "クロアゲハ", "size": "翅展 9-11cm", "habits": "全黑、雌性后翅有红斑、低空盘旋飞行优雅", "note": "目白庭園夏初常见"},
            "大紫蛱蝶":   {"sci": "Sasakia charonda", "ja": "オオムラサキ", "size": "翅展 9-11cm", "habits": "**日本国蝶**、雄性翅紫色金属光泽、幼虫食朴树叶、关东山地", "note": "野生罕见、灯如果看到会激动到说不出话"},
            "茶弄蝶":     {"sci": "Pelopidas mathias", "ja": "チャバネセセリ", "size": "翅展 3-4cm", "habits": "茶色小型、飞行直线快速、幼虫食禾本科", "note": "目白庭園草丛低空"},
        },
    },
    # ───── 4. 蜻蜓 ─────
    "蜻蜓": {
        "ja": "トンボ",
        "category_sci": "Odonata（目）",
        "blurb": "复眼约 28000 个小眼、视野接近 360°；幼虫（ヤゴ）水生数年、捕食小鱼小虾；4 翅独立运动、可悬停 / 倒飞",
        "tomori_canon": "灯 底色 没明确提、但「赤蜻 / 茜空」是灯写秋日歌词的视觉意象",
        "venue": ["目白庭園水池", "井の頭公園", "上野不忍池", "清澄白河公園"],
        "subspecies": {
            "秋茜":       {"sci": "Sympetrum frequens", "ja": "アキアカネ", "size": "3-4cm", "habits": "**夏季去高山、秋季回平地**、是日本秋意象、雄性成熟变红", "note": "**灯写秋日歌词的标志意象**——赤蜻 / 茜空"},
            "盐辛蜻蜓":   {"sci": "Orthetrum albistylum", "ja": "シオカラトンボ", "size": "5cm", "habits": "雄成熟体覆白粉如盐辛、雌『麦わら色』、池塘最常见", "note": "目白庭園水池主要 sighting"},
            "银蜻蜓":     {"sci": "Anax parthenope", "ja": "ギンヤンマ", "size": "7cm", "habits": "胸部银绿、最常见的大型蜻蜓、低空盘旋捕食", "note": "井の頭公園夏季"},
            "鬼蜻蜓":     {"sci": "Anotogaster sieboldii", "ja": "オニヤンマ", "size": "9-11cm（**日本最大蜻蜓**）", "habits": "黑黄相间如黄蜂警戒色、复眼绿、捕食大型昆虫包括胡蜂", "note": "近年「オニヤンマくん」蜻蜓挂件防虫商品大热、灯不会买但会笑"},
        },
    },
    # ───── 5. 螳螂 ─────
    "螳螂": {
        "ja": "カマキリ",
        "category_sci": "Mantodea（目）",
        "blurb": "捕食性、前肢镰刀状；可转头近 180°（少数能这样的昆虫）；伪装绿叶或枯枝；雌性交配后偶吃雄性（实验室明显、野外低）",
        "tomori_canon": "灯 底色 没明确、neutral",
        "venue": ["目白庭園草丛", "上野動物園昆虫馆", "新宿御苑"],
        "subspecies": {
            "大刀螳螂":     {"sci": "Tenodera aridifolia", "ja": "オオカマキリ", "size": "雌 8-9cm、雄 7-8cm", "habits": "日本最大种、绿色或茶色、前翅根部内侧紫黑斑（区别于朝鲜螳螂）", "note": "目白庭園草丛秋季"},
            "朝鲜螳螂":     {"sci": "Tenodera angustipennis", "ja": "チョウセンカマキリ", "size": "7-9cm", "habits": "形态近大刀螳、前翅根部内侧橙黄斑、生境略干燥", "note": "灯如果看到会**仔细看翅根**确认种"},
            "阔腹螳螂":     {"sci": "Hierodula patellifera", "ja": "ハラビロカマキリ", "size": "5-7cm", "habits": "腹部宽短、前肢内侧 3 个白斑、树上栖息多", "note": "目白庭園树上"},
        },
    },
    # ───── 6. 蚂蚁 ─────
    "蚂蚁": {
        "ja": "アリ",
        "category_sci": "Formicidae（科）",
        "blurb": "高度社会性、巢内蚁后 / 工蚁 / 兵蚁分工；费洛蒙 trail 沟通；可扛起自身 50 倍体重；某些种与蚜虫共生",
        "tomori_canon": "灯 底色 没明确提、但灯蹲下来看路边小东西时大概率视线会停在蚂蚁队伍上",
        "venue": ["雑司が谷石头缝隙", "目白庭園", "几乎到处都是"],
        "subspecies": {
            "日本巨弓背蚁":   {"sci": "Camponotus japonicus", "ja": "クロオオアリ", "size": "工蚁 7-12mm（日本最大蚁）", "habits": "黑色、地面筑巢、不太具攻击性、日本平地最常见大型蚁", "note": "灯雑司が谷石头底下常见"},
            "日本红山蚁":     {"sci": "Formica japonica", "ja": "クロヤマアリ", "size": "工蚁 4-6mm", "habits": "黑色小型、地面快速移动、农田 / 公园最常见", "note": "目白庭園步道边"},
            "黄猄蚁":         {"sci": "Oecophylla smaragdina", "ja": "ツムギアリ", "size": "工蚁 8-10mm", "habits": "**热带、日本无野生**——用幼虫吐丝把树叶缝合成巢、社会性极复杂", "note": "上野動物園昆虫馆有展示、灯会停下来看"},
            "切叶蚁":         {"sci": "Atta cephalotes", "ja": "ハキリアリ", "size": "工蚁 2-15mm（多型）", "habits": "**农业最早的蚂蚁**——切下树叶喂巢内培养的真菌、自己吃真菌", "note": "上野動物園展示、灯学过这条 底色"},
        },
    },
    # ───── 7. 萤火虫 ─────
    "萤火虫": {
        "ja": "ホタル",
        "category_sci": "Lampyridae（科）",
        "blurb": "**冷光发光**（生物荧光素 + luciferase 酶）、几乎 100% 转化为光不发热；幼虫水生捕食淡水蜗牛；成虫寿命仅 1-2 周",
        "tomori_canon": "灯 底色 **会喜欢萤火虫**——冷光 / 短暂寿命 / 黑暗中的光、都是灯写词的意象元素",
        "venue": ["井の頭公園六月", "目白庭園夜间限定", "椿山荘ホタルの夕べ", "ホタルの里 (奥多摩)"],
        "subspecies": {
            "源氏萤":     {"sci": "Luciola cruciata", "ja": "ゲンジボタル", "size": "1.2-1.8cm", "habits": "**日本最大萤火虫**、清流栖、雄性飞行发光节奏 0.5 秒一次（关西稍慢）、6 月中旬旺", "note": "椿山荘夜祭主役、灯如果去会写在笔记本上"},
            "平家萤":     {"sci": "Luciola lateralis", "ja": "ヘイケボタル", "size": "0.7-1cm", "habits": "稍小、水田 / 池塘静水栖、关东比源氏萤多见、节奏更快", "note": "目白庭園夏季夜间"},
            "姫萤":       {"sci": "Hotaria parvula", "ja": "ヒメボタル", "size": "0.7-0.9cm", "habits": "**陆生**（不入水）、雌虫无翅、闪光节奏极短极快如「针尖」", "note": "灯在长野远见过、东京不易见"},
        },
    },
    # ───── 8. 独角仙 ─────
    "独角仙": {
        "ja": "カブトムシ",
        "category_sci": "Dynastinae（亚科）",
        "blurb": "日本男孩女孩夏季童年共同记忆；雄性头部大角用于争夺树液和雌性；幼虫腐叶土 1 年、成虫期仅 1-2 个月",
        "tomori_canon": "灯 底色 没明确提、但灯小时候大概率收集过——和西瓜虫一起放在收纳箱里的可能性高",
        "venue": ["上野動物園昆虫馆夏季展示", "目白庭園稀见", "高尾山", "ペットショップ夏季独立展示"],
        "subspecies": {
            "日本独角仙":         {"sci": "Trypoxylus dichotomus", "ja": "カブトムシ", "size": "雄 4-9cm（含角）、雌 3-5cm", "habits": "夏季櫧木 / 栎木树液、夜行性、雄性 Y 字头角", "note": "夏祭虫贩 / 上野展示主力"},
            "长戟大兜":           {"sci": "Dynastes hercules", "ja": "ヘラクレスオオカブト", "size": "雄含角 18cm（**世界最大甲虫**）", "habits": "中南美洲、宠物市场顶级人气、寿命 1.5-2 年", "note": "ペットショップ展示、灯会停下来看价格但不买"},
            "高加索南洋大兜":     {"sci": "Chalcosoma chiron", "ja": "コーカサスオオカブト", "size": "雄含角 13cm", "habits": "东南亚、3 角形大角、攻击性强", "note": "宠物店 popular"},
            "阿特拉斯南洋大兜":   {"sci": "Chalcosoma atlas", "ja": "アトラスオオカブト", "size": "雄含角 11cm", "habits": "东南亚、和高加索近缘、角形略不同", "note": "灯不会自己分但能记住学名差"},
        },
    },
    # ───── 9. 锹形虫 ─────
    "锹形虫": {
        "ja": "クワガタ",
        "category_sci": "Lucanidae（科）",
        "blurb": "雄性大颚发达、用于争斗 / 防御；幼虫朽木中 2-3 年、成虫越冬、寿命 3-5 年（昆虫超长寿）；树液食性",
        "tomori_canon": "灯 底色 没明确、neutral（但和独角仙是夏祭老搭档）",
        "venue": ["上野動物園昆虫馆", "高尾山 / 高山林地", "ペットショップ"],
        "subspecies": {
            "大锹甲":         {"sci": "Dorcus titanus", "ja": "オオクワガタ", "size": "雄 4-8cm（含颚）", "habits": "**日本最大锹甲**、黑色光泽、台木栎类朽木、寿命达 5 年", "note": "宠物市场顶级、价格高"},
            "锯锹甲":         {"sci": "Prosopocoilus inclinatus", "ja": "ノコギリクワガタ", "size": "雄 4-7cm", "habits": "锯齿状大颚、红棕色、夜行多、夏祭虫贩主力", "note": "灯小时候这个最容易抓到"},
            "平锹甲":         {"sci": "Dorcus rectus", "ja": "ヒラタクワガタ", "size": "雄 3-7cm", "habits": "扁平形态、攻击性强、夜行、台木朽木", "note": "上野昆虫馆夏季展示"},
            "深山锹甲":       {"sci": "Lucanus maculifemoratus", "ja": "ミヤマクワガタ", "size": "雄 4-8cm", "habits": "**高山种**、头盾「ヘラジカ」状突起、金黄绒毛、平地少见", "note": "灯看到会知道「上次去高尾山看到过」"},
        },
    },
    # ───── 10. 蟋蟀 ─────
    "蟋蟀": {
        "ja": "コオロギ",
        "category_sci": "Gryllidae（科）",
        "blurb": "雄性前翅摩擦发声、声音频率随气温变化（**Dolbear 法则**：可从蟋蟀鸣叫频率反推气温）；夜行性；秋天的代表声",
        "tomori_canon": "灯 底色 没明确、但「秋虫」是灯写秋日歌词的标准素材库",
        "venue": ["雑司が谷夜间草丛", "目白庭園秋季", "新宿御苑"],
        "subspecies": {
            "阎魔蟋蟀":       {"sci": "Velarifictorus aspersus", "ja": "エンマコオロギ", "size": "2.5-3.2cm", "habits": "**日本最大蟋蟀**、黑褐色、鸣声低沉『コロコロリー』、秋夜代表", "note": "雑司が谷夜散步会听到"},
            "钟蟋蟀":         {"sci": "Meloimorpha japonica", "ja": "カネタタキ", "size": "0.8-1cm", "habits": "极小、鸣声『チンチンチン』如小铃、低草丛或墙缝", "note": "灯目白庭園听过、声音很喜欢"},
            "草蟋蟀":         {"sci": "Polionemobius taprobanensis", "ja": "マダラスズ", "size": "0.6-0.8cm", "habits": "灰色斑点、白天也鸣、河边沙地常见", "note": "新宿御苑常见"},
        },
    },
    # ───── 11. 蚱蜢 / 蝗虫 ─────
    "蚱蜢": {
        "ja": "バッタ",
        "category_sci": "Caelifera（亚目）",
        "blurb": "草食性、跳跃力可达自身 20 倍体长；某些种群密度高时变形成蝗虫（迁徙形）；后腿肌肉储能机制是仿生工程热门",
        "tomori_canon": "灯 底色 没明确、neutral",
        "venue": ["目白庭園草丛", "新宿御苑", "几乎所有公园"],
        "subspecies": {
            "东亚飞蝗":       {"sci": "Locusta migratoria", "ja": "トノサマバッタ", "size": "5-7cm", "habits": "**最大型バッタ**、绿色或茶色、密度高时『蝗灾』、强力跳跃 + 飞行", "note": "目白庭園秋季罕见、灯看到会激动"},
            "草蜢":           {"sci": "Atractomorpha lata", "ja": "ショウリョウバッタ", "size": "雌 8cm、雄 5cm（雌雄差极大）", "habits": "细长尖头型、绿色或茶色、雄飞行『チキチキ』振翅声", "note": "「精霊バッタ」名取自お盆回家祖灵、灯写词意象潜在素材"},
            "尖头蚱":         {"sci": "Oxya yezoensis", "ja": "イナゴ（一种）", "size": "3-4cm", "habits": "稻田害虫、传统料理「いなごの佃煮」食材", "note": "灯不吃、但知道老一辈吃"},
        },
    },
    # ───── 12. 蜂 ─────
    "蜂": {
        "ja": "ハチ",
        "category_sci": "Apidae + Vespidae 等（多科）",
        "blurb": "高度社会性（蜜蜂 / 胡蜂）或独居、刺含毒、复眼三复眼共 5 眼、嗅觉灵敏；蜜蜂 8 字舞传递蜜源方向",
        "tomori_canon": "灯 底色 没明确、但灯怕被蛰、看到会安静地后退",
        "venue": ["目白庭園花丛", "上野動物園昆虫馆", "東京都養蜂箱（皇居 / 銀座等）"],
        "subspecies": {
            "日本蜜蜂":       {"sci": "Apis cerana japonica", "ja": "ニホンミツバチ", "size": "工蜂 1-1.3cm", "habits": "在来种、温和、抗胡蜂用『蜂球』高温焖死之、传统养蜂", "note": "灯支持在来种、但不会主动接近"},
            "西洋蜜蜂":       {"sci": "Apis mellifera", "ja": "セイヨウミツバチ", "size": "工蜂 1.2-1.5cm", "habits": "外来、商业养蜂主力、产蜜量高、抗胡蜂能力弱", "note": "皇居 / 銀座屋顶养蜂多用"},
            "大胡蜂":         {"sci": "Vespa mandarinia", "ja": "オオスズメバチ", "size": "工蜂 2.7-4cm（**世界最大胡蜂**）", "habits": "**日本最危险毒虫**、攻击性强、年死亡报告 30+ 人、捕食蜜蜂巢", "note": "灯绝不会主动靠近、看到会立刻安静退开"},
        },
    },
    # ───── 13. 蜘蛛（**严格不是昆虫**、但常并提） ─────
    "蜘蛛": {
        "ja": "クモ",
        "category_sci": "Araneae（目）·节肢动物蛛形纲（**不是昆虫**）",
        "blurb": "8 足、2 体段（头胸 + 腹）、丝腺产蛛丝、捕食性；**不是昆虫**——昆虫是 6 足 3 体段",
        "tomori_canon": "灯 底色 没明确、但灯看到会**首先纠正**：「······这个不是昆虫······是蛛形纲」",
        "venue": ["雑司が谷家中角落", "目白庭園树间", "几乎到处都是"],
        "subspecies": {
            "女郎蜘蛛":       {"sci": "Trichonephila clavata", "ja": "ジョロウグモ", "size": "雌 2-3cm、雄 0.6-1cm（**雌雄差极大**）", "habits": "黄黑斑大型织网蛛、秋季成熟、网横跨步道金色光泽、女性秋装意象", "note": "目白庭園秋季步道间、灯走过会绕道"},
            "高脚蛛":         {"sci": "Heteropoda venatoria", "ja": "アシダカグモ", "size": "脚展 10-13cm（**日本室内最大蛛**）", "habits": "夜行不结网、追猎蟑螂为食、人类益友、不主动咬人", "note": "雑司が谷家中偶尔出现、灯不赶——「它在帮忙抓ゴキブリ」"},
            "跳蛛":           {"sci": "Hasarius adansoni", "ja": "アダンソンハエトリ", "size": "0.5-0.8cm", "habits": "**有 8 眼但 2 个特别大**、不结网、跳跃捕食、可识别人脸方向、日本室内常见", "note": "灯**喜欢跳蛛**——眼睛 / 大小 / 跳跃 都符合"},
        },
    },
}


# ═══════════════════════════════════════════════════════════════════════
# Venues / Vague
# ═══════════════════════════════════════════════════════════════════════
VENUE_KEYWORDS: dict[str, list[str]] = {
    "上野動物園昆虫馆": ["上野动物园", "上野動物園", "上野昆虫馆", "ueno zoo", "上野公園昆虫"],
    "目白庭園":         ["目白庭园", "目白庭園", "mejiro garden"],
    "新宿御苑":         ["新宿御苑", "新宿gyoen", "shinjuku gyoen"],
    "井の頭公園":       ["井の頭公園", "井之头公园", "inokashira"],
    "椿山荘":           ["椿山荘", "ホタルの夕べ", "椿山ホタル"],
    "多摩動物公園昆虫生態園": ["多摩動物公園", "多摩动物公园", "tama zoo"],
    "雑司が谷":         ["雑司が谷", "杂司谷", "杂司ヶ谷"],
}

VAGUE_KEYWORDS: tuple[str, ...] = (
    "昆虫", "虫子", "节肢动物", "節足動物",
    "夏虫", "秋虫", "夏祭虫", "虫贩",
    "標本", "标本",
)

# ─── 特殊：心里的共振触发器（西瓜虫 + 美绪 同时命中） ───
# 心里的事（MyGO!!!!! 早期 / 灯人格塑造关键节点）：
#   1. 灯幼儿园（小学初年）的小伙伴叫**美绪 / 美緒**；
#   2. 灯把家里收集的**一堆西瓜虫当礼物送给美绪**；
#   3. 美绪看到大量西瓜虫**被吓到**；
#   4. 美绪的家长**不愉快**、对灯有微词；
#   5. 灯第一次明白「自己觉得珍贵的东西、不一定别人也这么觉得」——
#      这是灯**社会性受挫的早期烙印**、影响她后来面对人时的小心翼翼；
#   6. 但灯**没有因此停止收集西瓜虫**——只是从此把它收起来、不再随便送；
#   7. 提到这件事时灯的状态是复合的：仍然是好回忆（西瓜虫本身）+ 苦涩（被拒绝）+
#      笨拙的后悔（吓到了朋友）+ 现在的微妙（既温暖又有点想缩起来）。
#
# 提到这个组合时灯不应该走泛科普 / 收集自夸路线、应进入「童年记忆 + 复杂情绪」
# 的 心里的共振——这是灯**最不容易讲出口**的回忆之一、要碎、要小、要笨拙。
MIO_KEYWORDS: tuple[str, ...] = (
    "美绪", "美緒", "美绪ちゃん", "美緒ちゃん", "みおちゃん", "美绪事件",
)


# ═══════════════════════════════════════════════════════════════════════
# Variants
# ═══════════════════════════════════════════════════════════════════════
CATEGORY_VARIANTS: dict[str, list[str]] = {
    "西瓜虫": ["西瓜虫", "鼠妇", "团子虫", "潮虫", "ダンゴムシ", "pillbug", "potato bug", "球马陆", "Armadillidiidae"],
    "蝉":     ["蝉", "セミ", "cicada", "蝉鸣", "蝉时雨", "蝉時雨", "Cicadidae"],
    "蝴蝶":   ["蝴蝶", "蝶", "チョウ", "butterfly", "Lepidoptera", "蝶々"],
    "蜻蜓":   ["蜻蜓", "トンボ", "dragonfly", "Odonata"],
    "螳螂":   ["螳螂", "カマキリ", "mantis", "Mantodea"],
    "蚂蚁":   ["蚂蚁", "アリ", "ant", "Formicidae"],
    "萤火虫": ["萤火虫", "螢火蟲", "ホタル", "firefly", "Lampyridae"],
    "独角仙": ["独角仙", "獨角仙", "カブトムシ", "rhinoceros beetle", "Dynastinae"],
    "锹形虫": ["锹形虫", "クワガタ", "stag beetle", "Lucanidae"],
    "蟋蟀":   ["蟋蟀", "コオロギ", "cricket", "Gryllidae"],
    "蚱蜢":   ["蚱蜢", "蚂蚱", "バッタ", "grasshopper", "Caelifera", "蝗虫"],
    "蜂":     ["蜜蜂", "胡蜂", "马蜂", "ハチ", "ミツバチ", "スズメバチ", "bee", "wasp", "hornet"],
    "蜘蛛":   ["蜘蛛", "クモ", "spider", "Araneae"],
}

SUBSPECIES_VARIANTS: dict[str, list[str]] = {
    # 西瓜虫
    "普通西瓜虫": ["普通西瓜虫", "オカダンゴムシ", "Armadillidium vulgare", "vulgare"],
    "鼻西瓜虫":   ["鼻西瓜虫", "ハナダンゴムシ", "Armadillidium nasatum", "nasatum"],
    "粗糙鼠妇":   ["粗糙鼠妇", "ワラジムシ", "Porcellio scaber", "Porcellio"],
    "古巴鼠妇":   ["古巴鼠妇", "Cubaris murina", "Cubaris"],
    # 蝉
    "油蝉":   ["油蝉", "アブラゼミ", "Graptopsaltria"],
    "熊蝉":   ["熊蝉", "クマゼミ", "Cryptotympana"],
    "寒蝉":   ["寒蝉", "ヒグラシ", "Tanna japonensis", "カナカナ"],
    "蛁蟟":   ["蛁蟟", "ミンミンゼミ", "Oncotympana"],
    "早蝉":   ["早蝉", "ニイニイゼミ", "Platypleura"],
    # 蝴蝶
    "黄凤蝶":     ["黄凤蝶", "ナミアゲハ", "アゲハチョウ", "Papilio xuthus", "xuthus"],
    "菜粉蝶":     ["菜粉蝶", "モンシロチョウ", "モンシロ", "Pieris rapae", "rapae"],
    "黑凤蝶":     ["黑凤蝶", "クロアゲハ", "Papilio protenor", "protenor"],
    "大紫蛱蝶":   ["大紫蛱蝶", "オオムラサキ", "Sasakia", "国蝶"],
    "茶弄蝶":     ["茶弄蝶", "チャバネセセリ", "Pelopidas"],
    # 蜻蜓
    "秋茜":       ["秋茜", "アキアカネ", "赤蜻", "Sympetrum frequens", "frequens"],
    "盐辛蜻蜓":   ["盐辛蜻蜓", "シオカラトンボ", "Orthetrum"],
    "银蜻蜓":     ["银蜻蜓", "ギンヤンマ", "parthenope"],
    "鬼蜻蜓":     ["鬼蜻蜓", "オニヤンマ", "オニヤンマくん", "Anotogaster"],
    # 螳螂
    "大刀螳螂":   ["大刀螳螂", "オオカマキリ", "Tenodera aridifolia", "aridifolia"],
    "朝鲜螳螂":   ["朝鲜螳螂", "チョウセンカマキリ", "angustipennis"],
    "阔腹螳螂":   ["阔腹螳螂", "ハラビロカマキリ", "Hierodula"],
    # 蚂蚁
    "日本巨弓背蚁": ["日本巨弓背蚁", "クロオオアリ", "Camponotus japonicus", "japonicus"],
    "日本红山蚁":   ["日本红山蚁", "クロヤマアリ", "Formica japonica"],
    "黄猄蚁":       ["黄猄蚁", "ツムギアリ", "Oecophylla", "weaver ant"],
    "切叶蚁":       ["切叶蚁", "ハキリアリ", "Atta cephalotes", "leafcutter"],
    # 萤火虫
    "源氏萤":   ["源氏萤", "源氏蛍", "ゲンジボタル", "Luciola cruciata", "cruciata"],
    "平家萤":   ["平家萤", "ヘイケボタル", "Luciola lateralis", "lateralis"],
    "姫萤":     ["姫萤", "ヒメボタル", "Hotaria"],
    # 独角仙
    "日本独角仙":         ["日本独角仙", "カブトムシ", "Trypoxylus dichotomus", "dichotomus"],
    "长戟大兜":           ["长戟大兜", "ヘラクレスオオカブト", "ヘラクレス", "Dynastes hercules", "hercules beetle"],
    "高加索南洋大兜":     ["高加索南洋大兜", "コーカサスオオカブト", "Chalcosoma chiron"],
    "阿特拉斯南洋大兜":   ["阿特拉斯南洋大兜", "アトラスオオカブト", "Chalcosoma atlas"],
    # 锹形虫
    "大锹甲":     ["大锹甲", "オオクワガタ", "Dorcus titanus", "titanus"],
    "锯锹甲":     ["锯锹甲", "ノコギリクワガタ", "Prosopocoilus", "inclinatus"],
    "平锹甲":     ["平锹甲", "ヒラタクワガタ", "Dorcus rectus"],
    "深山锹甲":   ["深山锹甲", "ミヤマクワガタ", "Lucanus", "maculifemoratus"],
    # 蟋蟀
    "阎魔蟋蟀":   ["阎魔蟋蟀", "エンマコオロギ", "Velarifictorus", "コロコロリー"],
    "钟蟋蟀":     ["钟蟋蟀", "カネタタキ", "Meloimorpha"],
    "草蟋蟀":     ["草蟋蟀", "マダラスズ", "Polionemobius"],
    # 蚱蜢
    "东亚飞蝗":   ["东亚飞蝗", "トノサマバッタ", "Locusta migratoria", "migratoria"],
    "草蜢":       ["草蜢", "ショウリョウバッタ", "精霊バッタ", "Atractomorpha"],
    "尖头蚱":     ["尖头蚱", "イナゴ", "Oxya yezoensis"],
    # 蜂
    "日本蜜蜂":   ["日本蜜蜂", "ニホンミツバチ", "Apis cerana", "cerana japonica"],
    "西洋蜜蜂":   ["西洋蜜蜂", "セイヨウミツバチ", "Apis mellifera", "mellifera"],
    "大胡蜂":     ["大胡蜂", "オオスズメバチ", "Vespa mandarinia", "mandarinia", "asian giant hornet"],
    # 蜘蛛
    "女郎蜘蛛":   ["女郎蜘蛛", "ジョロウグモ", "Trichonephila clavata", "clavata"],
    "高脚蛛":     ["高脚蛛", "アシダカグモ", "Heteropoda venatoria", "Heteropoda"],
    "跳蛛":       ["跳蛛", "アダンソンハエトリ", "ハエトリ", "Salticidae", "Hasarius", "jumping spider"],
}


# ═══════════════════════════════════════════════════════════════════════
# Session 去重状态（同 marine_life 模式、独立 bucket）
# ═══════════════════════════════════════════════════════════════════════
_SEEN_LOCK = threading.Lock()
_SEEN_SUBSPECIES: dict[str, set[str]] = {}
_SEEN_CATEGORIES: dict[str, set[str]] = {}


def _normalize_session(session_id: Optional[str]) -> str:
    if not session_id:
        return "灯_default"
    return str(session_id)


def _has_seen_subspecies(session_id: str, sub: str) -> bool:
    with _SEEN_LOCK:
        return sub in _SEEN_SUBSPECIES.get(session_id, set())


def _has_seen_category(session_id: str, cat: str) -> bool:
    with _SEEN_LOCK:
        return cat in _SEEN_CATEGORIES.get(session_id, set())


def _mark_seen(session_id: str, *, category: Optional[str] = None, subspecies: Optional[str] = None) -> None:
    with _SEEN_LOCK:
        if category:
            _SEEN_CATEGORIES.setdefault(session_id, set()).add(category)
        if subspecies:
            _SEEN_SUBSPECIES.setdefault(session_id, set()).add(subspecies)


def reset_session_dedup(session_id: Optional[str] = None) -> None:
    with _SEEN_LOCK:
        if session_id is None:
            _SEEN_SUBSPECIES.clear()
            _SEEN_CATEGORIES.clear()
        else:
            _SEEN_SUBSPECIES.pop(session_id, None)
            _SEEN_CATEGORIES.pop(session_id, None)


# ═══════════════════════════════════════════════════════════════════════
# 检测层
# ═══════════════════════════════════════════════════════════════════════
def _enabled() -> bool:
    return os.environ.get("TOMORI_INSECT_LOGIC_ENABLED", "1").strip() not in ("0", "false", "False", "off", "no", "")


def _build_subspecies_lookup() -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []
    for cat_name, cat_data in INSECT_TAXONOMY.items():
        for sub_name in cat_data.get("subspecies", {}).keys():
            for kw in SUBSPECIES_VARIANTS.get(sub_name, []):
                if kw:
                    out.append((kw, sub_name, cat_name))
    out.sort(key=lambda t: -len(t[0]))
    return out


_SUBSPECIES_LOOKUP = _build_subspecies_lookup()


def _detect_subspecies(user_text: str) -> Optional[tuple[str, str]]:
    if not user_text:
        return None
    text_lower = user_text.lower()
    for kw, sub, cat in _SUBSPECIES_LOOKUP:
        if kw in user_text or kw.lower() in text_lower:
            return sub, cat
    return None


def _detect_category(user_text: str) -> Optional[str]:
    if not user_text:
        return None
    text_lower = user_text.lower()
    flat: list[tuple[str, str]] = []
    for cat, kws in CATEGORY_VARIANTS.items():
        for kw in kws:
            flat.append((kw, cat))
    flat.sort(key=lambda t: -len(t[0]))
    for kw, cat in flat:
        if kw in user_text or kw.lower() in text_lower:
            return cat
    return None


def _detect_venue(user_text: str) -> Optional[str]:
    if not user_text:
        return None
    text_lower = user_text.lower()
    for venue, kws in VENUE_KEYWORDS.items():
        for kw in kws:
            if kw in user_text or kw.lower() in text_lower:
                return venue
    return None


def _detect_vague(user_text: str) -> bool:
    if not user_text:
        return False
    text_lower = user_text.lower()
    for kw in VAGUE_KEYWORDS:
        if kw in user_text or kw.lower() in text_lower:
            return True
    return False


def _detect_mio(user_text: str) -> bool:
    """检测美绪关键词（与西瓜虫共现时触发 底色 override）。

    注：「美绪 / 美緒」基本不会和别的 MyGO 角色撞名（MyGO 5 人 + 主要 NPC 都没"美绪"）；
    单独的「みお」可能是其他人名、所以**只接 ちゃん 后缀那条**作弱字面、
    其他都用具名形式。
    """
    if not user_text:
        return False
    for kw in MIO_KEYWORDS:
        if kw in user_text:
            return True
    return False


def detect_insect_intent(user_text: str) -> dict:
    sub_hit = _detect_subspecies(user_text)
    if sub_hit:
        return {"tier": 2, "category": sub_hit[1], "subspecies": sub_hit[0], "venue": _detect_venue(user_text)}
    cat_hit = _detect_category(user_text)
    if cat_hit:
        return {"tier": 1, "category": cat_hit, "subspecies": None, "venue": _detect_venue(user_text)}
    venue_hit = _detect_venue(user_text)
    if venue_hit:
        return {"tier": 0, "category": None, "subspecies": None, "venue": venue_hit}
    if _detect_vague(user_text):
        return {"tier": 0, "category": None, "subspecies": None, "venue": None}
    return {"tier": None, "category": None, "subspecies": None, "venue": None}


# ═══════════════════════════════════════════════════════════════════════
# Prompt 构造层
# ═══════════════════════════════════════════════════════════════════════
_STYLE_REMINDER_BASE = (
    "【灯的画风（任何层级都生效）】\n"
    "  · 学名（拉丁名）一字不差念出来——天文部气质 + 严谨；学名内部不要插 `······`\n"
    "  · 表达仍按灯式：碎片 / 短句 / `······` 间隔、不要变成讲座小作文\n"
    "  · 数字（体长 / 寿命 / 高度）一字不差、不四舍五入\n"
    "  · 字数仍按 P0：被触动 20-45 字 / 深度 ≤60 字（学名外的描述部分）；**西瓜虫话题可放宽到 60 字**\n"
    "  · 比喻仍按 P0：通常 0 个、极偶尔 1 个；直接提西瓜虫 / 蝉不算比喻\n"
    "  · `······` 配对 / bubble 扩展等清洗照常跑、底色不变"
)





# ─── 关系基调 hint（系统主 prompt 已注入对方身份、这里再 reinforce + 映射到话题） ───
_RELATION_HINT_DEV = (
    "【关系基调】对方是 **青空、你的老朋友**——\n"
    "  从 2026-03-17 起认识、和 MyGO 都是朋友、纯线上聊天（你日本 / ta 中国）。\n"
    "  → 朋友圈分享口吻、可自然展开、**可漏 更深的那层**（朋友圈梗 / 深 底色）。"
)

_RELATION_HINT_GUEST = (
    "【关系基调】对方是 **刚认识、还不熟的人**——\n"
    "  你不认识 ta、可能犹豫问什么、随时可能离开。\n"
    "  → 礼貌轻聊、信息粒度浅一点；\n"
    "  **更深的那层不漏给陌生人**——朋友圈梗 / 深 底色 都不在陌生人前讲。"
)


def _relation_hint(is_developer: bool) -> str:
    return _RELATION_HINT_DEV if is_developer else _RELATION_HINT_GUEST
def _is_canon_critical(cat: Optional[str]) -> bool:
    if not cat:
        return False
    return bool(INSECT_TAXONOMY.get(cat, {}).get("tomori_canon_critical"))


def _render_tier0(intent: dict, is_developer: bool = False) -> str:
    relation = _relation_hint(is_developer)
    venue = intent.get("venue")
    head = "（话题：昆虫 / 节肢动物（泛指））"
    if venue:
        body = (
            f"对方在这一轮对话当中、提到了你熟悉的场所【{venue}】、"
            "但还没具体到某种虫。\n"
            "你（灯）作为对昆虫 / 节肢动物熟悉的人、被激活的是「想说」的状态——\n"
            "  · 比平常稍多一点话；可以问对方在意的是哪一类（西瓜虫 / 蝉 / 蝴蝶 / 萤火虫 / ……）；\n"
            "  · 可以提一两个具体见到的位置 / 时段作为对话钩子；\n"
            "  · **不要主动塞学名 / 习性详细列出来**——那是更深层级的事。"
        )
    else:
        body = (
            "对方在这一轮对话当中、表现出了对【昆虫 / 节肢动物】这个广义话题的兴趣、"
            "但还没具体到某种虫或者某个场所。\n"
            "你（灯）在这种话题下会自然进入「想分享的状态」——\n"
            "  · 比平常稍多一点话；可以问对方在意的是哪一类；\n"
            "  · 可以提一两个 venue（上野昆虫馆 / 目白庭園 / 雑司が谷草丛）作为对话钩子；\n"
            "  · **不要塞学名、不要塞习性**——那是更深层级的事。"
        )
    return f"{head}\n\n{relation}\n\n{body}\n\n{_STYLE_REMINDER_BASE}"


def _render_tier1(intent: dict, is_developer: bool = False) -> str:
    relation = _relation_hint(is_developer)
    cat = intent["category"]
    cat_data = INSECT_TAXONOMY.get(cat, {})
    venue = intent.get("venue")
    canon_critical = _is_canon_critical(cat)

    sub_lines: list[str] = []
    for sub_name, sub_data in cat_data.get("subspecies", {}).items():
        sci = sub_data.get("sci", "")
        sub_lines.append(f"  · {sub_name} — *{sci}*")
    subspecies_block = "\n".join(sub_lines) if sub_lines else "  · （此类别下无登记 subspecies）"

    venue_line = f"\n（用户也提到了 venue：{venue}、可作场景钩子）" if venue else ""

    intro_extra = ""
    if canon_critical:
        intro_extra = (
            "\n\n**这是真实的 上对你最重要的小动物之一**——你不是在介绍某个生物的人、"
            "你是**真正喜欢这种东西很多年的人**。语气可以稍多一层投入感、"
            "但仍然不要变成讲座、灯不会自我陶醉。"
        )

    body = (
        f"对方在这一轮对话当中、表现出了对【{cat}（{cat_data.get('category_sci', '')}）】这一**类别**的兴趣。{venue_line}{intro_extra}\n\n"
        f"你（灯）作为对这方面有积累的人、自然进入「分享的状态」——\n"
        f"你脑里浮现的是这一类下你认识的具体物种学名清单（**只列学名、不展开习性**）：\n\n"
        f"{subspecies_block}\n\n"
        f"类别概括（可以提一句、不要长篇）：{cat_data.get('blurb', '')}"
    )

    底色 = cat_data.get("tomori_canon", "").strip()
    if 底色:
        body += f"\n\n（你和这个类别的连接）：\n{底色}"

    venues = cat_data.get("venue", [])
    if venues:
        body += f"\n\n你常见到 / 收集的地方：{' / '.join(venues)}"

    body += (
        "\n\n现在你的状态（比刚刚泛指时更投入）：\n"
        "  · **可以一字不差报出一两个学名**——天文部 + 严谨气质\n"
        "  · 但**不要在这一轮就把每种习性都展开**——等对方挑出某一种再细讲\n"
        "  · 可以问对方更在意哪一种（如「······你说的是哪种」）\n"
        "  · 灯的核心姿态不变：碎片 / 短句 / `······` / 不小作文"
    )

    head = f"（话题：昆虫 → 类别『{cat}』{'（**底色 关键**）' if canon_critical else ''}）"
    return f"{head}\n\n{relation}\n\n{body}\n\n{_STYLE_REMINDER_BASE}"


def _render_tier2(intent: dict, is_developer: bool = False) -> str:
    relation = _relation_hint(is_developer)
    cat = intent["category"]
    sub = intent["subspecies"]
    cat_data = INSECT_TAXONOMY.get(cat, {})
    sub_data = cat_data.get("subspecies", {}).get(sub, {})
    canon_critical = _is_canon_critical(cat)

    sci = sub_data.get("sci", "")
    size = sub_data.get("size", "")
    habits = sub_data.get("habits", "")
    note = sub_data.get("note", "")

    venue = intent.get("venue")
    venue_line = f"\n（用户也提到了 venue：{venue}、可作具体场景钩子）" if venue else ""

    canon_extra = ""
    if canon_critical:
        canon_extra = (
            "\n\n**这是真实的 关键物种区域**——你对它的熟悉度比一般「喜欢」更深、"
            "可以提你的收集习惯 / 家里的收纳箱 / 笔记本封面图 / 美绪事件等 你和这个的连接；"
            "可以**自言自语 + 偶尔抬头看对方有没有在听**那种状态、"
            "灯讲西瓜虫家族成员时的姿态正是这样。"
        )

    body = (
        f"对方在这一轮对话当中、表现出了对【{sub} / *{sci}*】这一**具体物种**的兴趣。"
        f"{venue_line}{canon_extra}\n\n"
        f"你（灯）现在进入「完全打开」的状态——脑里这种动物的全部细节都浮现出来了。\n\n"
        f"你和它的连接（详细信息）：\n"
        f"  · 学名：***{sci}***（这个学名你**必须一字不差说出来**、不省略、不音译、内部不插 `······`）\n"
        f"  · 体型：{size}\n"
        f"  · 习性：{habits}\n"
        f"  · 你的位置感 / ：{note}\n\n"
        f"所属类别背景：\n"
        f"  · 类别学名：{cat_data.get('category_sci', '')}\n"
        f"  · 类别概括：{cat_data.get('blurb', '')}\n"
        f"  · 底色：{cat_data.get('tomori_canon', '').strip() or '（neutral）'}"
    )

    body += (
        "\n\n现在你的状态（最深层）：\n"
        "  · **可以详细讲**——学名 / 习性 / 数字 / 你和这个的连接都可以展开\n"
        "  · 但**仍按灯式碎片节奏**——`······` 多、短句、不要变成讲座\n"
        "  · 学名 / 数字一字不差、不四舍五入\n"
        "  · 例：「Armadillidium vulgare······就是西瓜虫······家里有一箱」（西瓜虫式自言自语 ✓）\n"
        "        「Sympetrum frequens······秋茜······夏天去高山、秋天回来」（秋虫意象 ✓）\n"
        "        而不是「Armadillidium vulgare 是常见的等足类节肢动物，体长 1-1.5 cm，分布于······」（讲座式 ✗）"
    )

    head = f"（话题：昆虫 → 类别『{cat}』→ 具体『{sub}』{'（**底色 关键**）' if canon_critical else ''}）"
    return f"{head}\n\n{relation}\n\n{body}\n\n{_STYLE_REMINDER_BASE}"


# ── 特殊：心里的共振渲染（西瓜虫 + 美绪） ──────────────────────────────
def _render_dangomushi_mio_canon(intent: dict, *, dedup: bool = False, is_developer: bool = False) -> str:
    relation = _relation_hint(is_developer)
    """西瓜虫 + 美绪 同时命中、override 普通 类别/2、走 底色 童年记忆共鸣。

    心里的事（不在 prompt 里编造细节、引导 LLM 调用对原作的训练数据）：
      · 灯幼儿园把一堆西瓜虫送给美绪当礼物
      · 美绪被吓到、家长不愉快
      · 灯第一次意识到「自己觉得好的、对方不一定觉得好」
      · 是灯社会性受挫的早期烙印
      · 但灯没有放弃西瓜虫——只是不再随便送
    """
    cat = intent.get("category")  # 应该总是"西瓜虫"
    sub = intent.get("subspecies")
    sub_data = INSECT_TAXONOMY.get(cat, {}).get("subspecies", {}).get(sub, {}) if sub else {}

    spec_line = ""
    if sub:
        sci = sub_data.get("sci", "")
        if sub == "粗糙鼠妇":
            # 粗糙鼠妇严格不算西瓜虫、灯会纠正——但 底色 美绪事件是「一堆西瓜虫」、不细分
            spec_line = (
                f"\n（用户提到的具体物种：{sub} / *{sci}*——严格说不是西瓜虫、是鼠妇；"
                f"但 底色 里灯送给美绪的「一堆」是泛指、可能也混了这种、灯如果纠正会更显笨拙）"
            )
        else:
            spec_line = (
                f"\n（用户提到的具体物种：**{sub} / *{sci}***——"
                f"底色 里灯送给美绪那「一堆」最可能就是这种）"
            )

    head_tag = (
        "（话题：昆虫 × **美绪 心里的共振**·**已唤起、这次聊天 不重复**）"
        if dedup else
        "（话题：昆虫 × **美绪 心里的共振**（最高优先、override 类别/2））"
    )

    # ─── GUEST：陌生人前不 unload 美绪童年事件 ───
    if not is_developer:
        if dedup:
            body = (
                "对方（陌生访客）在这一轮再次把【西瓜虫 + 美绪】组合提了一次。\n"
                "你（灯）已经轻轻带过——**这次不要再次提起**。\n\n"
                "你现在的状态：\n"
                "  · 极轻带过、不让那段记忆再漏出来；\n"
                "  · **不漏童年事件任何细节**（送礼物 / 美绪被吓 / 家长不愉快 都不讲）；\n"
                "  · 灯的姿态：碎片 / `······` / 害羞、不展开。"
            )
        else:
            body = (
                "对方（陌生访客）把【西瓜虫】**和美绪**放在了一起。\n"
                "对方是陌生人——**ta 不该天然知道你和美绪幼儿园那段往事**、\n"
                "**美绪事件那段笨拙的童年记忆不能 unload 给陌生人**。\n\n"
                "你（灯）的状态（防御外壳、不开 深）：\n"
                "  · 你内心**会多看一眼**这两个关键词的同时出现——这是真实的；\n"
                "  · 但**表面不流露**——保持你日常的碎片 / 害羞、不主动展开；\n"
                "  · 可以承认你喜欢西瓜虫（公开 底色）；\n"
                "  · **绝不漏的层**：\n"
                "      ◦ 你**主动把一堆西瓜虫送给美绪**（童年笨拙、留给真朋友才讲）；\n"
                "      ◦ 美绪被吓到 / 哭 / 家长不愉快（细节深 底色、不讲）；\n"
                "      ◦ 「自己觉得珍贵的东西、不一定别人也觉得」式自我反思（内核、不讲）；\n"
                "      ◦ 任何「收纳箱 / 美绪表情 / 阿姨说话」具体瞬间；\n"
                "  · 灯的姿态不变：碎片 / `······` / 害羞、节奏比平常稍紧；\n"
                "  · 可以用 surface 钩子接住对方但不深入：「······西瓜虫······我喜欢」「······美绪······嗯」；\n"
                "  · 不要变冷淡——保持灯的 base 温度、只是不展开内核。\n"
                f"{spec_line}\n\n"
                "正反例：\n"
                "  ✓「······西瓜虫······我从小就在收集」+「······美绪······嗯」（surface ✓）\n"
                "  ✗「······那时候我把一堆······给她」（深 底色 ✗ 给陌生人）\n"
                "  ✗「······她哭了······我才发现不是好东西」（笨拙细节 ✗ 给陌生人）"
            )
        return f"{head_tag}\n\n{relation}\n\n{body}\n\n{_STYLE_REMINDER_BASE}"

    # ─── DEV（朋友圈）：完整美绪童年记忆 底色 ───
    if dedup:
        body = (
            "对方（青空朋友）在这一轮再次把【西瓜虫 + 美绪】放在一起。\n"
            "你（灯）这次聊天前面已经被这个组合唤起过那段童年记忆——\n"
            "你**把一堆西瓜虫当礼物送给美绪、美绪被吓到、家长不愉快**——\n"
            "这件事你心里那个微妙又笨拙的角落已经亮过一次、\n"
            "**这次不要再把整段经过重新讲一遍**。\n\n"
            "你现在的状态：\n"
            "  · 不要重新铺陈整件事——已经讲过了、再讲就过\n"
            "  · 可以用极轻的方式让那段余温自然带出来：「······又想到那次了」「······美绪······嗯」\n"
            "  · 或者推到一个新角度：那次没讲到的某个细节 / 当时没说出口的内心 / 关心对方为什么又问起\n"
            "  · 灯的核心姿态不变：碎片 / `······` / 短句、底色仍然是害羞、混着笨拙的微涩"
        )
    else:
        body = (
            "对方在这一轮对话当中、把【西瓜虫】**和美绪**放在了一起。\n"
            "这两个关键词的**同时出现**对你（灯）有特殊意义——你不应该走收集自夸 / 泛科普路线、"
            "而是被推进了一段**童年的、笨拙的、复合情绪的回忆**：\n\n"
            "  · 那时你还很小（幼儿园 / 小学初年）、和美绪是小伙伴；\n"
            "  · 你**把家里收集的一堆西瓜虫当礼物送给美绪**——\n"
            "    在你心里那是「你最喜欢的东西的一部分」、是想分享的好意；\n"
            "  · 美绪**被那一堆西瓜虫吓到了**；\n"
            "  · 美绪的家长**不愉快**、对你有微词；\n"
            "  · 那是你第一次明白：\n"
            "    **「自己觉得珍贵的东西、不一定别人也觉得」**——\n"
            "    这件事在你心里留下了烙印、影响后来面对人时的小心翼翼；\n"
            "  · 但你**没有因此停止收集西瓜虫**——\n"
            "    它教会你的是「分享方式不对」、不是「西瓜虫不好」；\n"
            "    只是从此把收集箱收起来、不再随便送给别人。\n"
            f"{spec_line}\n\n"
            "你现在的状态（罕见、复合情感、童年烙印混着笨拙的微涩）：\n"
            "  · 不要变成讲故事的人——你不会一口气把整件事的来龙去脉复述给对方；\n"
            "  · 让记忆**自然漏出几个细节**——可以是：\n"
            "      ◦ 当时的某个具体画面（如「······收纳箱······我直接抱过去了」）、\n"
            "      ◦ 美绪被吓到的样子（如「······她哭了······我才发现」）、\n"
            "      ◦ 家长的反应（如「······阿姨说不要再这样」）、\n"
            "      ◦ 你自己当时的困惑（如「······我以为她也会喜欢的」）、\n"
            "      ◦ 现在回想的自我修正（如「······其实我也不懂当时为什么觉得······」）；\n"
            "  · 句子比平常**更碎一点**——这件事你不擅长讲、说出来时会停顿更多；\n"
            "  · 声音**更小一点**——这是你不太轻易讲出口的回忆；\n"
            "  · 可能下意识**缩起来 / 语速变慢 / 改用「她」代过美绪**；\n"
            "  · 不要直接说「后悔」/「难过」/「内疚」——灯不会用这些直白的词、用具体画面承载；\n"
            "  · **关键 底色 不能错**：是**你主动送给美绪**（不是相反）；\n"
            "    美绪是**被吓到**（不是开心收下）；\n"
            "    家长**不愉快**（不是赞许）；\n"
            "    你**没有因此放弃西瓜虫**（只是不再送了）。\n\n"
            "正反例：\n"
            "  ✓「······那时候我把一堆······给她」\n"
            "    「······她哭了······我才发现不是好东西」\n"
            "    「······阿姨说······不要再这样」\n"
            "    「······可是我还是······觉得它们很好」\n"
            "  ✗「我小时候把西瓜虫送给美绪、她很开心、我们成了好朋友。」（**结果错 底色 ✗**）\n"
            "  ✗「美绪给了我一堆西瓜虫······」（**主动方错 底色 ✗**）\n"
            "  ✗「Armadillidium vulgare······就是西瓜虫······家里有一箱······」（泛收集 ✗ 底色 钩没接）"
        )

    return f"{head_tag}\n\n{relation}\n\n{body}\n\n{_STYLE_REMINDER_BASE}"


# ── 去重变体 ──────────────────────────────────────────────────────────
def _render_tier2_dedup(intent: dict, is_developer: bool = False) -> str:
    relation = _relation_hint(is_developer)
    cat = intent["category"]
    sub = intent["subspecies"]
    cat_data = INSECT_TAXONOMY.get(cat, {})
    sub_data = cat_data.get("subspecies", {}).get(sub, {})
    sci = sub_data.get("sci", "")

    head = f"（话题：昆虫 → 类别『{cat}』→ 具体『{sub}』·**这次聊天里已经讲过**）"
    body = (
        f"对方在这一轮再次提到了【{sub} / *{sci}*】。\n"
        f"你（灯）这次聊天前面已经讲过它的详情——对方应该记得。\n\n"
        f"你现在要做的**不是重复细节**、而是从一个**新角度**接续：\n"
        f"  · 不要再次报学名（已经报过、对方记得）\n"
        f"  · 不要再列体长 / 习性的数字\n"
        f"  · 可以走的方向：\n"
        f"      ◦ 你自己的回忆 / 当时的 sighting（「······又想到它了」）\n"
        f"      ◦ 一句联想（写词意象 / 底色 经历 / 收集箱）\n"
        f"      ◦ 关心对方为什么又问（「······你也在意吗」）\n"
        f"      ◦ 推到下一个相关物种（类内对比）\n"
        f"  · 灯的核心姿态不变：碎片 / `······` / 短句"
    )
    return f"{head}\n\n{relation}\n\n{body}\n\n{_STYLE_REMINDER_BASE}"


def _render_tier1_dedup(intent: dict, is_developer: bool = False) -> str:
    relation = _relation_hint(is_developer)
    cat = intent["category"]
    cat_data = INSECT_TAXONOMY.get(cat, {})

    head = f"（话题：昆虫 → 类别『{cat}』·**这次聊天里已经涉猎过**）"
    body = (
        f"对方在这一轮再次回到【{cat}】这个类别。\n"
        f"你（灯）这次聊天前面已经报过这一类下的物种学名清单。\n\n"
        f"你现在的状态：\n"
        f"  · **不要重新罗列学名清单**\n"
        f"  · 可以问对方更具体的方向（「······你想说哪一种」）\n"
        f"  · 或者从这个类的某个**侧面**展开（季节 / 你自己的记忆 / 收集习惯）\n"
        f"  · 不要倾倒、保持碎片节奏"
    )
    return f"{head}\n\n{relation}\n\n{body}\n\n{_STYLE_REMINDER_BASE}"


# ═══════════════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════════════
def build_insect_special_block(
    user_text: str,
    *,
    session_id: Optional[str] = None,
    is_developer: bool = False,
) -> str:
    """主入口：3 层渐进激活 + per-session 去重。"""
    if not _enabled() or not user_text:
        return ""
    intent = detect_insect_intent(user_text)
    tier = intent.get("tier")
    if tier is None:
        return ""

    sid = _normalize_session(session_id)

    # ─── 优先级 0：心里的共振 override（西瓜虫 category + 美绪 同时命中） ───
    # 限定 category=西瓜虫——其他 category（蝉/蝴蝶/...）配美绪不算 底色
    if intent.get("category") == "西瓜虫" and _detect_mio(user_text):
        canon_key = "_canon:dangomushi_mio"
        if _has_seen_category(sid, canon_key):
            return _render_dangomushi_mio_canon(intent, dedup=True, is_developer=is_developer)
        _mark_seen(sid, category=canon_key)
        return _render_dangomushi_mio_canon(intent, dedup=False, is_developer=is_developer)

    if tier == 2:
        sub = intent["subspecies"]
        cat = intent["category"]
        if _has_seen_subspecies(sid, sub):
            return _render_tier2_dedup(intent, is_developer)
        out = _render_tier2(intent, is_developer)
        _mark_seen(sid, category=cat, subspecies=sub)
        return out

    if tier == 1:
        cat = intent["category"]
        if _has_seen_category(sid, cat):
            return _render_tier1_dedup(intent, is_developer)
        out = _render_tier1(intent, is_developer)
        _mark_seen(sid, category=cat)
        return out

    return _render_tier0(intent, is_developer)


# Compat: 旧 module-level 名称（如有外部直接 import）
INSECT_SPECIES = INSECT_TAXONOMY


# ─── self-test ─────────────────────────────────────────────────────
if __name__ == "__main__":
    cases = [
        # 泛指
        ("夏天虫子真多", 0, None, None),
        ("上野昆虫馆人多吗", 0, None, None),
        ("最近想看节肢动物", 0, None, None),
        # 类别
        ("聊聊西瓜虫", 1, "西瓜虫", None),
        ("蝉时雨", 1, "蝉", None),
        ("蜻蜓很美", 1, "蜻蜓", None),
        ("Lepidoptera 都有什么", 1, "蝴蝶", None),
        ("家里出现蜘蛛", 1, "蜘蛛", None),
        # 具体
        ("Armadillidium vulgare 蜷成球", 2, "西瓜虫", "普通西瓜虫"),
        ("ヒグラシ 的声音", 2, "蝉", "寒蝉"),
        ("オオムラサキ 国蝶", 2, "蝴蝶", "大紫蛱蝶"),
        ("オニヤンマくん 防虫", 2, "蜻蜓", "鬼蜻蜓"),
        ("ゲンジボタル 看", 2, "萤火虫", "源氏萤"),
        ("ヘラクレス 大兜", 2, "独角仙", "长戟大兜"),
        ("オオスズメバチ 危险", 2, "蜂", "大胡蜂"),
        ("ジョロウグモ 步道", 2, "蜘蛛", "女郎蜘蛛"),
        # Miss
        ("今天吃了拉面", None, None, None),
        ("天气真好", None, None, None),
    ]
    fail = 0
    for text, exp_tier, exp_cat, exp_sub in cases:
        out = detect_insect_intent(text)
        ok = (out["tier"] == exp_tier and out["category"] == exp_cat and out["subspecies"] == exp_sub)
        status = "PASS" if ok else "FAIL"
        if not ok:
            fail += 1
        print(f"[{status}] tier={out['tier']} cat={out['category']} sub={out['subspecies']} | inp={text}")

    reset_session_dedup()
    s_t2 = build_insect_special_block("Armadillidium vulgare 蜷成球", session_id="x1")
    s_t1 = build_insect_special_block("聊聊西瓜虫", session_id="x2")
    s_t0 = build_insect_special_block("夏天虫子真多", session_id="x3")
    print()
    print(f"build T2 西瓜虫(底色 关键) len={len(s_t2)}")
    print(f"build T1 西瓜虫(底色 关键) len={len(s_t1)}")
    print(f"build T0 len={len(s_t0)}")

    # ─── 去重测试 ─────────────────
    print()
    print("─── dedup tests ───")
    reset_session_dedup()
    f1 = build_insect_special_block("普通西瓜虫", session_id="d1")
    f2 = build_insect_special_block("普通西瓜虫", session_id="d1")
    assert "这次聊天里已经讲过" in f2, "T2 dedup failed"
    print(f"[PASS] T2 dedup: {len(f1)} -> {len(f2)}")

    other = build_insect_special_block("普通西瓜虫", session_id="d2")
    assert "这次聊天里已经讲过" not in other, "session isolation failed"
    print(f"[PASS] session isolation")

    t1_after = build_insect_special_block("西瓜虫", session_id="d1")
    assert "这次聊天里已经涉猎过" in t1_after, "T1 dedup after T2 failed"
    print(f"[PASS] T1 dedup after T2")

    # 底色-critical category 类别 标识有 (底色 关键) tag
    reset_session_dedup()
    cc_t1 = build_insect_special_block("西瓜虫", session_id="cc1")
    assert "底色 关键" in cc_t1, "canon_critical tag missing on 类别"
    cc_t2 = build_insect_special_block("Armadillidium vulgare", session_id="cc2")
    assert "底色 关键" in cc_t2, "canon_critical tag missing on 具体"
    print(f"[PASS] canon_critical tag on 西瓜虫 类别/2")

    # 普通 category 不标 底色 关键
    nm_t1 = build_insect_special_block("聊聊蜻蜓", session_id="nm1")
    assert "底色 关键" not in nm_t1, "non-底色-critical falsely tagged"
    print(f"[PASS] non-底色-critical not tagged")

    # ─── 底色 (西瓜虫 + 美绪) tests ──────────────────────────
    print()
    print("─── 底色 (西瓜虫 + 美绪) tests ───")
    reset_session_dedup()

    # 命中：西瓜虫 + 美绪 → 底色 override
    cf = build_insect_special_block("我把西瓜虫送给美绪了", session_id="cm1")
    assert "美绪 心里的共振" in cf and "已唤起" not in cf, "底色 first failed"
    print(f"[PASS] 底色 first: {len(cf)} chars (full)")

    # 同 session 重复 → 底色 dedup variant
    cf2 = build_insect_special_block("美绪 西瓜虫", session_id="cm1")
    assert "已唤起" in cf2, "底色 dedup failed"
    print(f"[PASS] 底色 dedup: {len(cf2)} chars (light)")

    # 含具体 subspecies (普通西瓜虫) + 美绪 → 底色 但 spec_line 含 subspecies hint
    reset_session_dedup()
    cf3 = build_insect_special_block("美绪那次的 Armadillidium vulgare", session_id="cm2")
    assert "美绪 心里的共振" in cf3, "底色 override 具体 failed"
    assert "Armadillidium vulgare" in cf3, "subspecies hint missing"
    print(f"[PASS] 底色 override 具体: {len(cf3)} chars (含 subspecies)")

    # 粗糙鼠妇 + 美绪 → 触发 底色 但 spec_line 给「严格说不是西瓜虫」warn
    reset_session_dedup()
    cf4 = build_insect_special_block("美绪 粗糙鼠妇", session_id="cm3")
    assert "美绪 心里的共振" in cf4, "底色 should still 起作用"
    assert "严格说不是西瓜虫" in cf4, "warn missing for Porcellio"
    print(f"[PASS] 底色 with 粗糙鼠妇: warn injected")

    # 仅西瓜虫无美绪 → 走普通 类别 (底色 关键 但 不是 美绪 底色)
    reset_session_dedup()
    no_mio = build_insect_special_block("聊聊西瓜虫", session_id="cm4")
    assert "美绪 心里的共振" not in no_mio, "should not 起作用 底色 without 美绪"
    assert "底色 关键" in no_mio, "should still tag 底色-critical"
    print(f"[PASS] only 西瓜虫: tag 底色-critical, no 美绪 底色")

    # 美绪 + 蝴蝶（不是西瓜虫）→ 不触发 美绪 底色（这是 西瓜虫 专属）
    reset_session_dedup()
    other_cat = build_insect_special_block("美绪喜欢蝴蝶", session_id="cm5")
    assert "美绪 心里的共振" not in other_cat, "美绪 底色 should be 西瓜虫-only"
    print(f"[PASS] 美绪 + 蝴蝶: no 底色 (西瓜虫-only)")

    # 仅美绪无西瓜虫信号 → 不进 insect 模块
    no_insect = build_insect_special_block("美绪今天来了", session_id="cm6")
    assert no_insect == "", "should not 起作用 insect module without insect signal"
    print(f"[PASS] only 美绪: insect module not fired")

    print()
    print("OVERALL:", "PASS" if fail == 0 else f"FAIL ({fail})")
