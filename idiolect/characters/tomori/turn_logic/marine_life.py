"""灯本轮特殊逻辑·海洋生物（**3 层渐进激活** / 2026-05-10 重构）。

设计哲学（用户拍板 2026-05-10）：
  按用户对该话题的**精确度**渐进释放灯的知识储备、不一上来就倾倒：

  ┌─────────────────────────────────────────────────────────────┐
  │ 泛指 · 泛指                                                │
  │   触发：用户提"海洋生物"/"水族馆"/"海里的东西"/venue 名      │
  │   注入：只激活"灯想说"的状态、不出具体信息                  │
  │   口吻：可以问对方在意哪一类、提一两个 venue                │
  │                                                              │
  │ 类别 · 类别                                                │
  │   触发：用户提"企鹅"/"水母"/"鲨鱼"等 category               │
  │   注入：该类别下**全部 subspecies 学名清单**（不展开习性）  │
  │   口吻：可以一字不差报学名、但不展开、等对方挑某种再讲      │
  │                                                              │
  │ 具体 · 具体                                                │
  │   触发：用户提"洪堡企鹅"/"海月水母"等 subspecies            │
  │   注入：该 subspecies 完整详情（学名 / 体型 / 习性 / venue）│
  │   口吻：完全打开、详细讲、但仍按灯式碎片节奏                │
  └─────────────────────────────────────────────────────────────┘

灯 底色 特征（保留）：
  · 学名（拉丁名）一字不差念出来——天文部气质 + 严谨细节控
  · 表达仍按灯式：碎片 / 短句 / `······` 间隔、不要变讲座
  · 场馆联动：池袋 Sunshine 水族館 / 墨田水族館 / 上野动物园 / 葛西临海 / 品川 / 鳥羽 / 横滨八景岛

API 单入口（兼容旧）：
  build_marine_special_block(user_text: str) -> str
"""
from __future__ import annotations

import os
import re
import threading
from typing import Optional


# ═══════════════════════════════════════════════════════════════════════
# 数据层：13 类别 / ~60 subspecies / 7 venues
# ═══════════════════════════════════════════════════════════════════════

# ─── 13 个 category（类别 + 具体 嵌套） ───
# 每个 category：
#   ja: 日语
#   category_sci: 类别学名（目/科/属、灯会念出来）
#   blurb: 一句类别概括（类别 注入用）
#   tomori_canon: 灯和这个 category 的连接（可空）
#   venue: 该类别在哪些 venue 能看到
#   subspecies: dict[name, {sci, ja, size, habits, note}]
MARINE_TAXONOMY: dict[str, dict] = {
    # ───── 1. 企鹅 ─────
    "企鹅": {
        "ja": "ペンギン",
        "category_sci": "Sphenisciformes（目）",
        "blurb": "群居海鸟、不会飞但精于游泳、雏鸟由父母轮流保温；日本水族馆 must-see",
        "tomori_canon": "灯 底色 **喜欢企鹅**、动物图案创可贴有企鹅款、有水族馆年票、楼顶天空企鹅常客",
        "venue": ["池袋サンシャイン水族館（楼顶 天空のペンギン）", "墨田水族館"],
        "subspecies": {
            "洪堡企鹅":   {"sci": "Spheniscus humboldti", "ja": "フンボルトペンギン", "size": "65-70cm / 4-5kg", "habits": "群居、一夫一妻、水中 30 km/h、面颊粉红裸皮散热", "note": "池袋サンシャイン楼顶「天空のペンギン」主力物种、灯最常看的"},
            "帝企鹅":     {"sci": "Aptenodytes forsteri", "ja": "コウテイペンギン", "size": "100-130cm / 22-45kg", "habits": "南极极地、雄性脚上单足孵蛋约 65 天禁食 4 个月", "note": "日本水族馆罕见、电影《皇帝企鹅日记》"},
            "国王企鹅":   {"sci": "Aptenodytes patagonicus", "ja": "オウサマペンギン", "size": "85-95cm / 11-16kg", "habits": "亚南极岛屿群居、孵化期 14-16 个月（最长）、雏鸟全身棕色绒毛", "note": "名古屋港水族馆、葛西临海有展示"},
            "阿德利企鹅": {"sci": "Pygoscelis adeliae", "ja": "アデリーペンギン", "size": "70-75cm / 4-6kg", "habits": "南极沿海、用石头筑巢（会偷邻居石头）、最典型的「企鹅形」", "note": "日本水族馆少、长崎ペンギン水族館有"},
            "巴布亚企鹅": {"sci": "Pygoscelis papua", "ja": "ジェンツーペンギン", "size": "75-90cm / 4.5-8.5kg", "habits": "亚南极、游速最快可达 36 km/h、橙色喙白色头斑", "note": "墨田水族館「ペンギンカフェ」展示"},
            "小蓝企鹅":   {"sci": "Eudyptula minor", "ja": "コガタペンギン", "size": "33cm / 1kg（最小）", "habits": "澳洲南部 / 新西兰、夜行性、白天躲洞穴", "note": "日本水族馆罕见"},
        },
    },
    # ───── 2. 水母 ─────
    "水母": {
        "ja": "クラゲ",
        "category_sci": "Medusozoa（亚门）",
        "blurb": "约 95% 由水构成、没有心脏 / 大脑 / 骨骼；伞缘触手有刺胞、毒性因种而异",
        "tomori_canon": "灯 底色 **喜欢水母**、和企鹅并列水族馆 must-see；底色 里灯对「滑溜溜的东西」感兴趣",
        "venue": ["墨田水族館（クラゲ展示「ビッグシャーレ」最大圆形展示缸）", "池袋サンシャイン水族館", "鶴岡市立加茂水族館（クラゲ世界第一）"],
        "subspecies": {
            "海月水母": {"sci": "Aurelia aurita", "ja": "ミズクラゲ", "size": "伞径 25-40cm", "habits": "日本最常见、浅蓝半透明、4 片 U 形生殖腺标志性", "note": "墨田水族館「ビッグシャーレ」主展示；「海月」是诗意写法、灯写词偏好"},
            "越前水母": {"sci": "Nemopilema nomurai", "ja": "エチゼンクラゲ", "size": "伞径 1-2m / 200kg（巨型）", "habits": "日本海大量繁殖年份会成灾、损害渔业、刺胞强毒", "note": "野生不在水族馆、新闻常提"},
            "灯塔水母": {"sci": "Turritopsis dohrnii", "ja": "ベニクラゲ", "size": "4-5mm（极小）", "habits": "**生物学上不死**——成体可逆向发育回水螅状态、理论上无限循环", "note": "新江ノ島水族館、加茂水族館有研究展示；这条灯会停下来发呆"},
            "桃花水母": {"sci": "Craspedacusta sowerbii", "ja": "マミズクラゲ", "size": "伞径 1-2cm", "habits": "**淡水水母**罕见、湖泊池塘偶发成群、伞缘 4 片粉红生殖腺如桃花", "note": "野生罕见、上野不忍池历史曾有记录"},
            "箱水母": {"sci": "Chironex fleckeri", "ja": "オーストラリアウンバチクラゲ", "size": "伞径 30cm / 触手 3m", "habits": "澳洲海域剧毒、刺胞含心脏毒素、可致命", "note": "日本不产、文献中提及；灯会用「致命的透明」这种意象"},
            "倒立水母": {"sci": "Cassiopea andromeda", "ja": "サカサクラゲ", "size": "伞径 30cm", "habits": "**伞向下口向上**栖息于浅海泥沙、共生藻光合供能", "note": "墨田水族館有展示、姿态独特"},
        },
    },
    # ───── 3. 海豚 ─────
    "海豚": {
        "ja": "イルカ",
        "category_sci": "Delphinidae（科）",
        "blurb": "高度社会性、回声定位、每只有专属「signature whistle」识别身份；通过镜像测试",
        "tomori_canon": "灯 底色 没明确连接、但「能在镜中认出自己」这种自我意识题灯会有兴趣",
        "venue": ["品川アクアパーク（海豚秀）", "横滨八景岛シーパラダイス", "鴨川シーワールド（虎鲸）"],
        "subspecies": {
            "宽吻海豚":   {"sci": "Tursiops truncatus", "ja": "バンドウイルカ", "size": "2-4m / 150-650kg", "habits": "海豚秀主力、最常被研究、寿命 40-60 年、可学习手势指令", "note": "品川アクアパーク主展示种"},
            "真海豚":     {"sci": "Delphinus delphis", "ja": "マイルカ", "size": "1.5-2.5m / 100-200kg", "habits": "外洋性大群、体侧黄褐色沙漏纹、群体可达千头", "note": "野生洄游、水族馆较少"},
            "虎鲸":       {"sci": "Orcinus orca", "ja": "シャチ", "size": "6-9m / 3-6t（海豚科最大）", "habits": "顶级掠食者、家族群「pod」固定成员、有方言", "note": "鴨川シーワールド、名古屋港水族館展示"},
            "白鲸":       {"sci": "Delphinapterus leucas", "ja": "シロイルカ", "size": "3.5-5.5m / 700-1600kg", "habits": "北极亚北极、可前后弯曲颈椎（多数鲸不能）、声音多变「海里的金丝雀」", "note": "横滨八景岛、名古屋港水族館；属一角鲸科严格不算 Delphinidae"},
            "伪虎鲸":     {"sci": "Pseudorca crassidens", "ja": "オキゴンドウ", "size": "4-6m / 1-2t", "habits": "全黑、群居、分享猎物、虎鲸近亲但温和", "note": "鴨川シーワールド有过展示"},
        },
    },
    # ───── 4. 章鱼 ─────
    "章鱼": {
        "ja": "タコ",
        "category_sci": "Octopoda（目）",
        "blurb": "9 个「大脑」（中央 + 8 腕各神经节）；变色 / 改变皮肤纹理；逃脱能力极强；寿命 1-2 年",
        "tomori_canon": "灯 底色 没明确连接、但 9 个大脑 / 改变形状 这种特性灯会觉得有趣",
        "venue": ["池袋サンシャイン水族館", "葛西临海水族園", "鳥羽水族館"],
        "subspecies": {
            "真蛸":             {"sci": "Octopus vulgaris", "ja": "マダコ", "size": "腕展 1m / 3kg", "habits": "日本料理常见种、岩礁洞穴栖、智力测试主角（拧瓶盖、走迷宫）", "note": "葛西临海触摸池"},
            "北太平洋巨型章鱼": {"sci": "Enteroctopus dofleini", "ja": "ミズダコ", "size": "腕展 4-9m / 50kg+（最大）", "habits": "北海道近海、深海性、寿命 3-5 年、雌性产卵后绝食守护至死", "note": "鳥羽水族館、新潟水族館展示"},
            "蓝环章鱼":         {"sci": "Hapalochlaena lunulata", "ja": "ヒョウモンダコ", "size": "腕展 10-20cm", "habits": "**剧毒**、唾液含河豚毒素、被激怒时蓝环闪烁警告", "note": "日本南部温暖海域有目击、水族馆罕见"},
            "拟态章鱼":         {"sci": "Thaumoctopus mimicus", "ja": "ミミックオクトパス", "size": "腕展 60cm", "habits": "印尼海域、可模仿至少 15 种海洋动物（比目鱼 / 海蛇 / 狮子鱼）", "note": "野生只目击难展示"},
            "深海小飞象":       {"sci": "Grimpoteuthis spp.", "ja": "メンダコ類", "size": "20-30cm", "habits": "深海 1000-7000m、伞状鳍如「小飞象」耳、半透明", "note": "深海特展时偶有标本"},
        },
    },
    # ───── 5. 鲨鱼 ─────
    "鲨鱼": {
        "ja": "サメ",
        "category_sci": "Selachimorpha（亚纲）",
        "blurb": "软骨鱼、嗅觉极敏锐（百万分之一血腥）；多数终生游泳「专性洄游」、停下缺氧死亡",
        "tomori_canon": "灯 底色 没明确连接、neutral",
        "venue": ["池袋サンシャイン水族館（黑鳍礁鲨）", "葛西临海水族園", "鴨川シーワールド"],
        "subspecies": {
            "大白鲨":       {"sci": "Carcharodon carcharias", "ja": "ホホジロザメ", "size": "4-6m / 700-2000kg", "habits": "顶级掠食者、可用「跃出水面」捕食海豹、嗅觉感知 5 km 外血腥", "note": "**捕获后无法在水族馆长期饲养**、冲绳近海野生有目击"},
            "鲸鲨":         {"sci": "Rhincodon typus", "ja": "ジンベエザメ", "size": "10-12m / 20t（现存最大鱼）", "habits": "滤食性、口腔 1.5m 张开吸入磷虾、性情温顺", "note": "美ら海水族館（冲绳）/ 海遊館（大阪）/ 鹿児島水族館 展示"},
            "虎鲨":         {"sci": "Galeocerdo cuvier", "ja": "イタチザメ", "size": "3-4m / 400kg", "habits": "杂食「海中垃圾桶」（车牌 / 罐头都吃过）、夜行、热带亚热带", "note": "南西诸岛野生、水族馆有展示"},
            "无双髻鲨":     {"sci": "Sphyrna mokarran", "ja": "ヒラシュモクザメ", "size": "4-6m", "habits": "T 形头部传感面积大、可探测海底埋藏的鳐鱼电信号", "note": "日本南部、葛西临海水族園"},
            "黑鳍礁鲨":     {"sci": "Carcharhinus melanopterus", "ja": "ツマグロ", "size": "1.5-2m", "habits": "珊瑚礁浅海、鳍尖黑色、性情温和、人类游泳常见接触种", "note": "池袋サンシャイン主展示鲨"},
            "皱鳃鲨":       {"sci": "Chlamydoselachus anguineus", "ja": "ラブカ", "size": "1.5-2m", "habits": "深海 500-1500m、外形原始「活化石」、6 对鳃裂、孕期 3 年（脊椎动物最长）", "note": "駿河湾偶捕获、沼津港深海水族館有标本"},
        },
    },
    # ───── 6. 海星 ─────
    "海星": {
        "ja": "ヒトデ",
        "category_sci": "Asteroidea（纲）",
        "blurb": "棘皮动物、五辐对称；可再生失去的腕、有些可从单一腕重新长出整体；管足吸盘移动",
        "tomori_canon": "灯 底色 没明确连接、但「能再生」+「五辐对称」是会让灯停下来看的细节",
        "venue": ["墨田水族館（触摸池）", "池袋サンシャイン水族館", "鳥羽水族館"],
        "subspecies": {
            "北太平洋海星": {"sci": "Asterias amurensis", "ja": "マヒトデ", "size": "直径 30-50cm", "habits": "5 腕、扁平、贪食贝类、北日本沿岸常见入侵种（澳洲深受其害）", "note": "墨田水族館触摸池可摸"},
            "棘冠海星":     {"sci": "Acanthaster planci", "ja": "オニヒトデ", "size": "直径 30-40cm", "habits": "16 腕、覆盖**毒棘**、专食珊瑚虫、爆发时摧毁珊瑚礁", "note": "冲绳珊瑚礁防控对象、水族馆为科普展示"},
            "面包海星":     {"sci": "Culcita novaeguineae", "ja": "マンジュウヒトデ", "size": "直径 20-30cm", "habits": "5 腕极退化呈五角面包形、热带珊瑚礁、底面满管足", "note": "美ら海水族館展示"},
            "向日葵海星":   {"sci": "Pycnopodia helianthoides", "ja": "ヒマワリヒトデ", "size": "直径 60-100cm（巨型）", "habits": "16-24 腕、北太平洋、移动可达 1m/min（海星里超快）、近年因海星消瘦症濒危", "note": "新江ノ島水族館历史展示"},
        },
    },
    # ───── 7. 河豚 ─────
    "河豚": {
        "ja": "フグ",
        "category_sci": "Tetraodontidae（科）",
        "blurb": "受惊吸入水将身体膨胀成球；体内含河豚毒素 tetrodotoxin、人类摄入无解毒剂",
        "tomori_canon": "灯 底色 没明确、neutral；但「致命的可爱」这种反差灯会写词",
        "venue": ["墨田水族館", "葛西临海水族園", "下関海響館（河豚专门）"],
        "subspecies": {
            "红鳍东方鲀": {"sci": "Takifugu rubripes", "ja": "トラフグ", "size": "70cm / 5kg", "habits": "高级食材主角、下关名物、料理需河豚调理免许、毒素集中肝/卵巢", "note": "下関海響館、葛西临海展示"},
            "虎纹东方鲀": {"sci": "Takifugu pardalis", "ja": "ヒガンフグ", "size": "30cm", "habits": "近岸常见、皮肤虎纹、毒性比红鳍稍低", "note": "葛西临海水族園"},
            "黄鳍东方鲀": {"sci": "Takifugu xanthopterus", "ja": "シマフグ", "size": "60cm", "habits": "横纹、鳍黄色、群居", "note": "下関海響館"},
            "刺鲀":       {"sci": "Diodon holocanthus", "ja": "ハリセンボン", "size": "30-40cm", "habits": "膨胀时全身硬棘竖起如球（其实不是 Tetraodontidae 而是 Diodontidae）、严格说不算「河豚」但常被并称", "note": "墨田水族館热带区"},
        },
    },
    # ───── 8. 金鱼 ─────
    "金鱼": {
        "ja": "金魚",
        "category_sci": "Carassius auratus（同一物种 / 不同品种）",
        "blurb": "鲫鱼人工选育变种、起源中国宋代；可达 41 年寿命；视觉为四色（含紫外）",
        "tomori_canon": "灯 底色 没明确、但「夏天 / 縁日 / 红色尾巴」的季节意象灯会写进笔记本",
        "venue": ["墨田水族館（江戸金魚展）", "アートアクアリウム", "夏祭り 縁日「金魚すくい」"],
        "subspecies": {
            "和金":     {"sci": "Carassius auratus var. wakin", "ja": "ワキン", "size": "15-30cm", "habits": "原始体型、最接近野生鲫鱼、缘日金鱼すくい主力", "note": "夏祭最常见、灯笔记里的「红尾」"},
            "琉金":     {"sci": "Carassius auratus var. ryukin", "ja": "リュウキン", "size": "15-20cm", "habits": "圆腹、长尾、体高、江戸金魚四大品种之一", "note": "墨田江戸金魚展主推"},
            "出目金":   {"sci": "Carassius auratus var. demekin", "ja": "デメキン", "size": "10-15cm", "habits": "眼球向外突出、视力差、不与游速快的同养", "note": "アートアクアリウム"},
            "兰寿":     {"sci": "Carassius auratus var. ranchu", "ja": "ランチュウ", "size": "15-20cm", "habits": "无背鳍、头部「狮子头」肉瘤、「金魚の王様」称号", "note": "弥彦金魚まつり / 江戸川区金魚まつり"},
            "丹顶":     {"sci": "Carassius auratus var. tancho", "ja": "タンチョウ", "size": "15-20cm", "habits": "全身白唯顶部红斑、状如丹顶鶴", "note": "鉴赏价值高、专门会场展示"},
            "流金":     {"sci": "Carassius auratus var. ryukin (variant)", "ja": "リュウキン（流れ尾）", "size": "15-20cm", "habits": "琉金长尾型、尾鳍极长拖曳如流水", "note": "鉴赏品种、价格高"},
        },
    },
    # ───── 9. 海獭 ─────
    "海獭": {
        "ja": "ラッコ",
        "category_sci": "Enhydra lutris（单物种 / 3 亚种）",
        "blurb": "用石头敲贝壳的少数哺乳动物；睡觉时彼此勾爪防漂走；日本水族馆数量逐年减少濒危",
        "tomori_canon": "灯 底色 没明确、但「滑溜溜的东西」+「用石头敲东西」灯会关注",
        "venue": ["鳥羽水族館（日本最多）", "サンシャイン水族館（曾有展示、近年减少）", "サンピアザ水族館（札幌）"],
        "subspecies": {
            "北方海獭": {"sci": "Enhydra lutris kenyoni", "ja": "アラスカラッコ", "size": "1.0-1.5m / 22-45kg", "habits": "阿拉斯加 / 阿留申群岛、最大亚种、毛皮密度 10 万根/cm²（哺乳动物最高）", "note": "日本水族馆主要饲育亚种"},
            "加州海獭": {"sci": "Enhydra lutris nereis", "ja": "カリフォルニアラッコ", "size": "1.0-1.4m / 18-35kg", "habits": "美国加州沿岸、体型最小亚种、近危", "note": "日本无展示、美国蒙特雷湾水族馆"},
            "千岛海獭": {"sci": "Enhydra lutris lutris", "ja": "アジアラッコ", "size": "1.2-1.5m / 25-40kg", "habits": "千岛群岛 / 北海道周辺、灭绝边缘、北海道近年偶有目击", "note": "野生为主、水族馆罕见"},
        },
    },
    # ───── 10. 海豹 ─────
    "海豹": {
        "ja": "アザラシ",
        "category_sci": "Phocidae（科）",
        "blurb": "鳍脚类（鳍足亚目 Pinnipedia）真海豹科——无外耳廓、后鳍不能转向前、陆上靠腹部蠕动；近缘但分科：海狮 Otariidae（有外耳廓）/ 海象 Odobenidae（长牙）",
        "tomori_canon": "灯 底色 没明确、但「圆滚滚」+「水里灵活陆上笨拙」的反差灯会停下来看",
        "venue": ["旭山動物園（アザラシ館・圆筒水柱）", "おたる水族館（北海道）", "鴨川シーワールド", "仙台うみの杜水族館"],
        "subspecies": {
            "斑海豹":     {"sci": "Phoca largha", "ja": "ゴマフアザラシ", "size": "1.5-1.7m / 60-110kg", "habits": "日本北方沿岸最常见、白底黑斑（胡麻斑纹）、寿命 30 年；幼体「ゴマちゃん」是日本水族馆人气吉祥物", "note": "旭山動物園・おたる水族館主力展示、灯如果说 ゴマちゃん 不是矫情、是真实的 圈名"},
            "港海豹":     {"sci": "Phoca vitulina", "ja": "ゼニガタアザラシ", "size": "1.4-1.9m / 80-170kg", "habits": "环状斑纹（钱形）得名、北海道襟裳岬有日本最大野生群落、单独行动多", "note": "野生主、襟裳岬游轮观察"},
            "髭海豹":     {"sci": "Erignathus barbatus", "ja": "アゴヒゲアザラシ", "size": "2.1-2.7m / 250-360kg", "habits": "下颚长须（味觉/触觉感受器）、北极底栖摄食、声音如鸟啼用于求偶", "note": "おたる水族館过去有展示"},
            "环斑海豹":   {"sci": "Pusa hispida", "ja": "ワモンアザラシ", "size": "1.0-1.4m / 50-110kg", "habits": "北极冰下 / 冰穴、Phocidae 最小种、寿命 40+ 年", "note": "日本水族馆罕见、ノルウェー / カナダ系展示"},
            "北象海豹":   {"sci": "Mirounga angustirostris", "ja": "キタゾウアザラシ", "size": "雄 4-5m / 2000kg、雌 2.5m / 600kg（巨型 + 雌雄差最大）", "habits": "雄性鼻部象鼻状膨胀、可潜深 1500m / 2 小时、加州海岸繁殖", "note": "日本无展示、太平洋东岸野生"},
            "竖琴海豹":   {"sci": "Pagophilus groenlandicus", "ja": "タテゴトアザラシ", "size": "1.7-2.0m / 130kg", "habits": "幼体「白子」纯白绒毛 2-3 周（猎杀争议焦点）、北大西洋浮冰繁殖", "note": "日本水族馆罕、海外纪录片常见"},
        },
    },
    # ───── 11. 海龟 ─────
    "海龟": {
        "ja": "ウミガメ",
        "category_sci": "Cheloniidae + Dermochelyidae（2 科）",
        "blurb": "爬行纲、全球濒危、雌性回出生海滩产卵；性别由孵化温度决定（高温雌、低温雄）",
        "tomori_canon": "灯 底色 没明确、但「回到出生地」「温度决定性别」灯会停下来想",
        "venue": ["美ら海水族館（冲绳）", "葛西临海水族園", "下田海中水族館"],
        "subspecies": {
            "赤蠵龟": {"sci": "Caretta caretta", "ja": "アカウミガメ", "size": "甲长 80-110cm", "habits": "日本主产卵种（屋久島 / 御前崎海岸）、肉食性（贝 / 螃蟹）、头大颚强", "note": "屋久島产卵观察是知名生态项目"},
            "绿海龟": {"sci": "Chelonia mydas", "ja": "アオウミガメ", "size": "甲长 80-120cm", "habits": "成年植食性（海草）、热带亚热带、寿命可达 80 年", "note": "美ら海水族館主展示"},
            "玳瑁":   {"sci": "Eretmochelys imbricata", "ja": "タイマイ", "size": "甲长 60-90cm", "habits": "热带珊瑚礁、捕食海绵（少数能消化海绵的动物）、甲壳「鼈甲」历史工艺品", "note": "现严禁鼈甲贸易、CITES 附录 I"},
            "棱皮龟": {"sci": "Dermochelys coriacea", "ja": "オサガメ", "size": "甲长 1.5-2.5m / 700kg（最大龟）", "habits": "无硬甲、革质背、可潜深 1200m、专食水母", "note": "极濒危、日本沿岸偶有迷途个体"},
        },
    },
    # ───── 11. 鲸 ─────
    "鲸": {
        "ja": "クジラ",
        "category_sci": "Cetacea（下目）",
        "blurb": "海洋哺乳动物、肺呼吸；分须鲸（滤食）/ 齿鲸（捕食）；歌声可传 1000+ km",
        "tomori_canon": "灯 底色 没明确、但「歌声传千公里」灯会停下来——这跟写词的人有共鸣",
        "venue": ["太地町立くじらの博物館", "国立科学博物館（标本）", "野生 watching：御蔵島 / 小笠原"],
        "subspecies": {
            "抹香鲸":   {"sci": "Physeter macrocephalus", "ja": "マッコウクジラ", "size": "16-20m / 35-57t", "habits": "齿鲸最大、可潜深 2000m、单声波 230 dB（地球最响动物声）、捕食大王乌贼", "note": "《白鲸记》原型、小笠原野生 watching"},
            "座头鲸":   {"sci": "Megaptera novaeangliae", "ja": "ザトウクジラ", "size": "12-16m / 25-30t", "habits": "**会唱长 30 分歌**、雄性繁殖期歌曲在群体内传播、跃身击浪标志性", "note": "冲绳座间味 / 慶良間野生 watching 旺季 1-3 月"},
            "蓝鲸":     {"sci": "Balaenoptera musculus", "ja": "シロナガスクジラ", "size": "24-30m / 100-150t（地球史上最大动物）", "habits": "心脏 600kg、舌头重 4t、心跳 4-8 次/分、寿命 80-90 年", "note": "野生罕见、博物馆标本"},
            "弓头鲸":   {"sci": "Balaena mysticetus", "ja": "ホッキョククジラ", "size": "14-18m / 60-100t", "habits": "北极圏、用厚头骨破冰、寿命可达 200+ 年（哺乳动物最长）", "note": "近年阿留申个体捕获含 19 世纪鱼叉头"},
            "小须鲸":   {"sci": "Balaenoptera acutorostrata", "ja": "ミンククジラ", "size": "8-10m / 5-10t", "habits": "须鲸最小、孤独或小群、日本沿岸常见", "note": "调查捕鲸主要对象、太地町博物馆"},
        },
    },
    # ───── 12. 海葵 ─────
    "海葵": {
        "ja": "イソギンチャク",
        "category_sci": "Actiniaria（目）",
        "blurb": "刺胞动物、固着或浅埋、口盘周围触手有刺胞、与小丑鱼共生最有名",
        "tomori_canon": "灯 底色 没明确、neutral",
        "venue": ["池袋サンシャイン水族館", "葛西临海水族園", "美ら海水族館（共生展示）"],
        "subspecies": {
            "壮丽海葵":         {"sci": "Heteractis magnifica", "ja": "センジュイソギンチャク", "size": "口盘直径 50cm-1m", "habits": "热带珊瑚礁、与小丑鱼（Amphiprion）共生最经典、夜间收缩白天展开", "note": "美ら海水族館 / アクアパーク品川"},
            "哈氏地毯海葵":     {"sci": "Stichodactyla haddoni", "ja": "ハタゴイソギンチャク", "size": "口盘直径 50-80cm", "habits": "短触手平铺如地毯、毒性较强、底层埋砂", "note": "葛西临海水族園"},
            "蛇形海葵":         {"sci": "Anemonia viridis", "ja": "スナギンチャク（近縁）", "size": "口盘直径 5-10cm", "habits": "地中海 / 大西洋、绿色或紫色、潮间带石下", "note": "野生欧洲、日本水族馆罕"},
        },
    },
    # ───── 13. 海马 ─────
    "海马": {
        "ja": "タツノオトシゴ",
        "category_sci": "Hippocampus（属）",
        "blurb": "**雄性育儿**——雌性产卵于雄性育儿袋、雄性怀胎 14-28 天分娩；游泳极慢、靠尾巴缠绕固着",
        "tomori_canon": "灯 底色 没明确、但「雄性怀胎」「靠尾巴卷住才能不漂走」灯会觉得有趣",
        "venue": ["葛西临海水族園", "アクアマリンふくしま", "新江ノ島水族館"],
        "subspecies": {
            "日本海马":         {"sci": "Hippocampus mohnikei", "ja": "サンゴタツ", "size": "8-10cm", "habits": "日本沿岸、海草丛、环境破坏导致野生减少", "note": "葛西临海展示"},
            "巴氏豆丁海马":     {"sci": "Hippocampus bargibanti", "ja": "ピグミーシーホース", "size": "1.4-2.4cm（极小）", "habits": "印太热带、与柳珊瑚（Muricella）共生拟态、皮肤瘤突如珊瑚虫", "note": "潜水拍摄圣杯、水族馆展示困难"},
            "草海龙":           {"sci": "Phyllopteryx taeniolatus", "ja": "リーフィーシードラゴン", "size": "20-25cm", "habits": "澳洲南部、全身叶状突起拟海藻、严格说不是海马是海龙（同科）", "note": "アクアマリンふくしま、新江ノ島水族館"},
        },
    },
}


# ═══════════════════════════════════════════════════════════════════════
# Venues（独立、可单独触发 泛指）
# ═══════════════════════════════════════════════════════════════════════
VENUE_KEYWORDS: dict[str, list[str]] = {
    "池袋サンシャイン水族館": ["池袋サンシャイン", "サンシャイン水族館", "池袋水族馆", "池袋 sunshine", "sunshine水族馆", "sunshine aquarium", "天空企鹅", "天空のペンギン"],
    "墨田水族館":             ["墨田水族馆", "墨田水族館", "sumida aquarium", "スカイツリー水族館", "東京スカイツリー水族館", "skytree水族馆"],
    "上野动物园":             ["上野动物园", "上野動物園", "上野动物園", "ueno zoo", "上野公園", "上野公园"],
    "葛西临海水族園":         ["葛西临海", "葛西臨海", "kasai aquarium"],
    "美ら海水族館":           ["美ら海", "美海水族館", "churaumi"],
    "鳥羽水族館":             ["鳥羽水族馆", "鳥羽水族館", "toba aquarium"],
    "海遊館":                 ["海遊館", "海游馆", "kaiyukan", "大阪海遊館"],
    "鴨川シーワールド":       ["鴨川シーワールド", "鴨川 sea world", "kamogawa seaworld"],
    "アートアクアリウム":     ["アートアクアリウム", "art aquarium", "金鱼艺术展"],
    "旭山動物園":             ["旭山動物園", "旭山动物园", "asahiyama zoo", "アザラシ館"],
    "おたる水族館":           ["おたる水族館", "小樽水族馆", "otaru aquarium"],
}

# 泛指 泛指词（不命中具体物种 / 类别 / venue 时可单独触发）
VAGUE_KEYWORDS: tuple[str, ...] = (
    "海洋生物", "海生动物", "海底动物", "海里的", "海中的", "水里的",
    "水族馆", "水族館", "aquarium", "水生生物",
    "海洋馆",  # 中文常见叫法、补
)

# ─── 特殊：心里的共振触发器（爱音 + 水族馆 同时命中） ───
# 心里的事（MyGO!!!!! 主线、用户拍板 2026-05-10 修正）：
#   1. 爱音问灯能否写一首简单的新曲、灯回答自己只会写词；
#   2. 爱音察觉到自己打起退堂鼓、灯也担心演出失败导致乐队再次解散、表示不想开 Live；
#   3. 爱音被立希批评「一直在逃避」后逃走；
#   4. 灯追上、在初中同学聚集处遇见爱音；
#   5. **灯主动把爱音拉到水族馆谈心**——这是关键、灯罕见地是主动方；
#   6. 在水族馆里、**看的是企鹅**（不是水母）；爱音向灯交代了自己留学失败的经历；
#   7. 灯肯定了爱音的鼓励与坚持、并在访客问卷上写下「迷子でもいい、迷子でも進め。」
#      （不畏迷茫、迷茫着也要砥砺前行）；
#   8. 二人下定决心继续开 Live；
#   9. 之后灯将二人相互鼓励的经历写成了《碧天伴走》。
# 提到这个组合时灯不该走泛科普路线、应进入「具体场景回忆 + 强情感共鸣」——
# 这是灯主动救场 / 爱音坦白脆弱 / 创作起点的复合记忆、温度比一般"约会回忆"重得多。
ANON_KEYWORDS: tuple[str, ...] = (
    "爱音", "愛音", "anon", "千早爱音", "千早愛音", "小爱", "小爱音", "アノン",
)


# ═══════════════════════════════════════════════════════════════════════
# Variants（关键词检测的源数据）
# ═══════════════════════════════════════════════════════════════════════

# 类别 类别变体（中 / 日 / 英 / 类别学名）
CATEGORY_VARIANTS: dict[str, list[str]] = {
    "企鹅": ["企鹅", "ペンギン", "penguin", "Sphenisciformes"],
    "水母": ["水母", "クラゲ", "海月", "jellyfish", "Medusozoa"],
    "海豚": ["海豚", "イルカ", "dolphin", "Delphinidae"],
    "章鱼": ["章鱼", "タコ", "octopus", "Octopoda"],
    "鲨鱼": ["鲨鱼", "鮫", "サメ", "shark", "Selachimorpha"],
    "海星": ["海星", "ヒトデ", "starfish", "sea star", "Asteroidea"],
    "河豚": ["河豚", "フグ", "pufferfish", "Tetraodontidae"],
    "金鱼": ["金鱼", "金魚", "goldfish", "Carassius auratus"],
    "海獭": ["海獭", "ラッコ", "sea otter", "Enhydra lutris", "Enhydra"],
    "海豹": ["海豹", "アザラシ", "seal", "Phocidae", "Pinnipedia"],
    "海龟": ["海龟", "海龜", "ウミガメ", "sea turtle", "Cheloniidae"],
    "鲸":   ["鲸鱼", "鯨", "クジラ", "whale", "Cetacea"],
    "海葵": ["海葵", "イソギンチャク", "sea anemone", "Actiniaria"],
    "海马": ["海马", "タツノオトシゴ", "seahorse", "Hippocampus"],
}

# 具体 subspecies 变体（中 / 日 / 学名 / 部分匹配）
# 注：subspecies key 是 dict[category][subspecies_name]、变体 key 这里直接用 subspecies_name
SUBSPECIES_VARIANTS: dict[str, list[str]] = {
    # 企鹅
    "洪堡企鹅":   ["洪堡", "humboldt", "Spheniscus humboldti", "フンボルト"],
    "帝企鹅":     ["帝企鹅", "皇帝企鹅", "コウテイ", "Aptenodytes forsteri", "emperor penguin"],
    "国王企鹅":   ["国王企鹅", "オウサマ", "Aptenodytes patagonicus", "king penguin"],
    "阿德利企鹅": ["阿德利", "アデリー", "Pygoscelis adeliae", "adelie"],
    "巴布亚企鹅": ["巴布亚", "ジェンツー", "Pygoscelis papua", "gentoo"],
    "小蓝企鹅":   ["小蓝企鹅", "コガタペンギン", "Eudyptula minor", "little blue penguin", "fairy penguin"],
    # 水母
    "海月水母":   ["海月水母", "ミズクラゲ", "Aurelia aurita", "moon jelly"],
    "越前水母":   ["越前水母", "エチゼンクラゲ", "Nemopilema", "nomura"],
    "灯塔水母":   ["灯塔水母", "ベニクラゲ", "Turritopsis", "immortal jelly"],
    "桃花水母":   ["桃花水母", "マミズクラゲ", "Craspedacusta"],
    "箱水母":     ["箱水母", "オーストラリアウンバチ", "Chironex", "box jellyfish"],
    "倒立水母":   ["倒立水母", "サカサクラゲ", "Cassiopea"],
    # 海豚
    "宽吻海豚":   ["宽吻", "瓶鼻", "バンドウイルカ", "Tursiops", "bottlenose"],
    "真海豚":     ["真海豚", "マイルカ", "Delphinus delphis", "common dolphin"],
    "虎鲸":       ["虎鲸", "シャチ", "Orcinus orca", "killer whale", "orca"],
    "白鲸":       ["白鲸", "シロイルカ", "Delphinapterus", "beluga"],
    "伪虎鲸":     ["伪虎鲸", "オキゴンドウ", "Pseudorca", "false killer whale"],
    # 章鱼
    "真蛸":               ["真蛸", "マダコ", "Octopus vulgaris", "common octopus"],
    "北太平洋巨型章鱼":   ["北太平洋巨型", "ミズダコ", "Enteroctopus", "giant pacific octopus"],
    "蓝环章鱼":           ["蓝环章鱼", "蓝环", "ヒョウモンダコ", "Hapalochlaena", "blue ring"],
    "拟态章鱼":           ["拟态章鱼", "模仿章鱼", "ミミックオクトパス", "Thaumoctopus", "mimic octopus"],
    "深海小飞象":         ["小飞象", "メンダコ", "Grimpoteuthis", "dumbo octopus"],
    # 鲨鱼
    "大白鲨":     ["大白鲨", "ホホジロザメ", "Carcharodon", "great white"],
    "鲸鲨":       ["鲸鲨", "ジンベエザメ", "Rhincodon", "whale shark"],
    "虎鲨":       ["虎鲨", "イタチザメ", "Galeocerdo", "tiger shark"],
    "无双髻鲨":   ["双髻鲨", "锤头鲨", "ヒラシュモク", "Sphyrna", "hammerhead"],
    "黑鳍礁鲨":   ["黑鳍礁鲨", "ツマグロ", "melanopterus", "blacktip reef"],
    "皱鳃鲨":     ["皱鳃鲨", "ラブカ", "Chlamydoselachus", "frilled shark"],
    # 海星
    "北太平洋海星": ["北太平洋海星", "マヒトデ", "Asterias amurensis"],
    "棘冠海星":     ["棘冠海星", "オニヒトデ", "Acanthaster", "crown-of-thorns"],
    "面包海星":     ["面包海星", "マンジュウヒトデ", "Culcita"],
    "向日葵海星":   ["向日葵海星", "ヒマワリヒトデ", "Pycnopodia"],
    # 河豚
    "红鳍东方鲀": ["红鳍东方鲀", "红鳍东方鲀", "トラフグ", "Takifugu rubripes"],
    "虎纹东方鲀": ["虎纹东方鲀", "ヒガンフグ", "Takifugu pardalis"],
    "黄鳍东方鲀": ["黄鳍东方鲀", "シマフグ", "Takifugu xanthopterus"],
    "刺鲀":       ["刺鲀", "ハリセンボン", "Diodon", "porcupinefish"],
    # 金鱼
    "和金":   ["和金", "ワキン", "wakin"],
    "琉金":   ["琉金", "リュウキン", "ryukin"],
    "出目金": ["出目金", "デメキン", "demekin", "telescope eye"],
    "兰寿":   ["兰寿", "蘭寿", "ランチュウ", "ranchu"],
    "丹顶":   ["丹顶金鱼", "タンチョウ"],
    "流金":   ["流金"],
    # 海獭
    "北方海獭":  ["北方海獭", "アラスカラッコ", "Enhydra lutris kenyoni"],
    "加州海獭":  ["加州海獭", "カリフォルニアラッコ", "nereis"],
    "千岛海獭":  ["千岛海獭", "アジアラッコ", "lutris lutris"],
    # 海豹
    "斑海豹":   ["斑海豹", "ゴマフアザラシ", "ゴマちゃん", "Phoca largha", "spotted seal"],
    "港海豹":   ["港海豹", "钱形海豹", "ゼニガタアザラシ", "Phoca vitulina", "harbor seal"],
    "髭海豹":   ["髭海豹", "胡子海豹", "アゴヒゲアザラシ", "Erignathus", "bearded seal"],
    "环斑海豹": ["环斑海豹", "ワモンアザラシ", "Pusa hispida", "ringed seal"],
    "北象海豹": ["北象海豹", "キタゾウアザラシ", "Mirounga", "elephant seal"],
    "竖琴海豹": ["竖琴海豹", "タテゴトアザラシ", "Pagophilus", "harp seal"],
    # 海龟
    "赤蠵龟": ["赤蠵龟", "红海龟", "アカウミガメ", "Caretta", "loggerhead"],
    "绿海龟": ["绿海龟", "アオウミガメ", "Chelonia mydas", "green turtle"],
    "玳瑁":   ["玳瑁", "タイマイ", "Eretmochelys", "hawksbill"],
    "棱皮龟": ["棱皮龟", "オサガメ", "Dermochelys", "leatherback"],
    # 鲸
    "抹香鲸": ["抹香鲸", "マッコウクジラ", "Physeter", "sperm whale"],
    "座头鲸": ["座头鲸", "ザトウクジラ", "Megaptera", "humpback"],
    "蓝鲸":   ["蓝鲸", "シロナガスクジラ", "Balaenoptera musculus", "blue whale"],
    "弓头鲸": ["弓头鲸", "ホッキョククジラ", "Balaena mysticetus", "bowhead"],
    "小须鲸": ["小须鲸", "ミンククジラ", "acutorostrata", "minke"],
    # 海葵
    "壮丽海葵":     ["壮丽海葵", "センジュイソギンチャク", "Heteractis magnifica"],
    "哈氏地毯海葵": ["哈氏地毯海葵", "ハタゴイソギンチャク", "Stichodactyla haddoni"],
    "蛇形海葵":     ["蛇形海葵", "Anemonia viridis"],
    # 海马
    "日本海马":     ["日本海马", "サンゴタツ", "Hippocampus mohnikei"],
    "巴氏豆丁海马": ["豆丁海马", "ピグミーシーホース", "bargibanti"],
    "草海龙":       ["草海龙", "リーフィーシードラゴン", "Phyllopteryx", "leafy seadragon"],
}


# ═══════════════════════════════════════════════════════════════════════
# Session 去重状态（轻量、进程内）
# ═══════════════════════════════════════════════════════════════════════
# 每个 session 记录：已经在这次聊天 里"完整讲过"的 subspecies + category
#   · 同 session 同 subspecies 第二次命中 → 渲染「不要重复」变体
#   · 同 session 同 category 第二次命中（无论是否经过 subspecies）→ 渲染轻去重
#   · 具体 起作用 同时 mark subspecies + category（详情覆盖类别）
#   · 进程重启自然清零
#
# 设计权衡：
#   · 不持久化 — 大部分对话不会跨进程纠缠同一物种、轻量优先
#   · 不分窗口 / TTL — session 内的对话连续性才是 dedup 的语义边界
#   · session_id None → fallback 「灯」单一 bucket（主路径会传真 session_id；
#     不传的调点共享一桶）
_SEEN_LOCK = threading.Lock()
_SEEN_SUBSPECIES: dict[str, set[str]] = {}  # session_id -> {subspecies_name}
_SEEN_CATEGORIES: dict[str, set[str]] = {}  # session_id -> {category_name}


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
    """清 session 的去重状态。session_id=None → 清全部。"""
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
    return os.environ.get("TOMORI_MARINE_LOGIC_ENABLED", "1").strip() not in ("0", "false", "False", "")


def _build_subspecies_lookup() -> list[tuple[str, str, str]]:
    """构造 (kw, subspecies_name, category_name) 列表、按 kw 长度倒序、长 kw 优先匹配。"""
    out: list[tuple[str, str, str]] = []
    for cat_name, cat_data in MARINE_TAXONOMY.items():
        for sub_name in cat_data.get("subspecies", {}).keys():
            for kw in SUBSPECIES_VARIANTS.get(sub_name, []):
                if kw:
                    out.append((kw, sub_name, cat_name))
    out.sort(key=lambda t: -len(t[0]))
    return out


_SUBSPECIES_LOOKUP = _build_subspecies_lookup()


def _detect_subspecies(user_text: str) -> Optional[tuple[str, str]]:
    """返回 (subspecies_name, category_name) 或 None。"""
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
    # 长 keyword 优先
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


def _detect_anon(user_text: str) -> bool:
    if not user_text:
        return False
    text_lower = user_text.lower()
    for kw in ANON_KEYWORDS:
        if kw in user_text or kw.lower() in text_lower:
            # 「小爱」字面太短易误命中（小爱 = 小爱同学等）；要求紧邻"爱音"或独立成片
            if kw == "小爱":
                # 要么后面就接"音"（"小爱音"已单独登记）、要么紧前后是非中文 char
                # 这里简单用：仅当输入还含"爱音"或字面就是"小爱"独立词时才算
                if "爱音" in user_text or re.search(r"(^|[^一-龥A-Za-z])小爱($|[^一-龥A-Za-z音])", user_text):
                    return True
                continue
            return True
    return False


def _has_marine_venue_or_concept(user_text: str, intent: dict) -> bool:
    """是否命中"水族馆/海洋馆"概念（tier!=None 即命中、含具体 venue / category / subspecies / vague）。"""
    if intent.get("tier") is not None:
        return True
    return False  # 已被 detect_marine_intent 涵盖


def detect_marine_intent(user_text: str) -> dict:
    """3 层意图检测。

    优先级：subspecies (具体) > category (类别) > venue (泛指) > vague (泛指)
    """
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

# 共享：灯式画风提醒（每个 tier 都含、强度递增由前面的 触发点 控制）
_STYLE_REMINDER_BASE = (
    "【灯的画风（任何层级都生效）】\n"
    "  · 学名（拉丁名）一字不差念出来——天文部气质 + 严谨；学名内部不要插 `······`\n"
    "  · 表达仍按灯式：碎片 / 短句 / `······` 间隔、不要变成讲座小作文\n"
    "  · 数字（体长 / 速度 / 寿命 / 深度）一字不差、不四舍五入\n"
    "  · 字数仍按 P0：被触动 20-45 字 / 深度 ≤60 字（学名外的描述部分）\n"
    "  · 比喻仍按 P0：通常 0 个、极偶尔 1 个；直接提水母 / 企鹅不算比喻\n"
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
def _render_tier0(intent: dict, is_developer: bool = False) -> str:
    relation = _relation_hint(is_developer)
    venue = intent.get("venue")
    parts: list[str] = []
    head = "（话题：海洋生物（泛指））"
    if venue:
        body = (
            f"对方在这一轮对话当中、提到了你熟悉的场馆【{venue}】、"
            "但还没具体到某种动物。\n"
            "你（灯）作为水族馆年票常客、被激活的是「想说」的状态——"
            "脑里会浮现这个馆里你常去看的展示位置、但**还不到倾倒科普的时机**。\n"
            "现在你的状态：\n"
            "  · 比平常稍多一点话；可以问对方在意的是哪一类（企鹅 / 水母 / 鲨鱼 / 海龟…）；\n"
            "  · 可以提一两个具体展示位置 / 馆内动线作为对话钩子；\n"
            "  · **不要主动把学名 / 习性详细列出来**——那是更深层级的事。"
        )
    else:
        body = (
            "对方在这一轮对话当中、表现出了对【海洋生物 / 水族馆】这个广义话题的兴趣、"
            "但还没具体到某种动物或者某个场馆。\n"
            "你（灯）在这种话题下会自然进入「想分享的状态」——"
            "你对这方面有大量积累、有水族馆年票、经常去看；"
            "但因为话题还没具体、**你不要主动倾倒科普**——等对方进一步问到具体类别再展开。\n"
            "现在你的状态：\n"
            "  · 比平常稍多一点话；可以问对方在意的是哪一类（企鹅 / 水母 / 鲨鱼 / 海龟…）；\n"
            "  · 可以提一两个 venue（池袋 Sunshine / 墨田 / 上野 / 葛西临海）作为对话钩子；\n"
            "  · **不要塞学名、不要塞习性**——那是更深层级的事。"
        )
    parts.append(head)
    parts.append(body)
    parts.append(_STYLE_REMINDER_BASE)
    return "\n\n".join(parts)


def _render_tier1(intent: dict, is_developer: bool = False) -> str:
    relation = _relation_hint(is_developer)
    cat = intent["category"]
    cat_data = MARINE_TAXONOMY.get(cat, {})
    venue = intent.get("venue")

    # 学名清单（只出 学名 + 中文 + 日文、不出习性 / 体型 / venue note）
    sub_lines: list[str] = []
    for sub_name, sub_data in cat_data.get("subspecies", {}).items():
        sci = sub_data.get("sci", "")
        sub_lines.append(f"  · {sub_name} — *{sci}*")
    subspecies_block = "\n".join(sub_lines) if sub_lines else "  · （此类别下无登记 subspecies）"

    venue_line = f"\n（用户也提到了 venue：{venue}、可作场景钩子）" if venue else ""

    body = (
        f"对方在这一轮对话当中、表现出了对【{cat}（{cat_data.get('category_sci', '')}）】这一**类别**的兴趣。{venue_line}\n\n"
        f"你（灯）作为对这方面有积累的人、自然进入「分享的状态」——"
        f"你脑里浮现的是这一类下你认识的具体物种学名清单（**只列学名、不展开习性**）：\n\n"
        f"{subspecies_block}\n\n"
        f"类别概括（可以提一句、不要长篇）：{cat_data.get('blurb', '')}"
    )

    底色 = cat_data.get("tomori_canon", "").strip()
    if 底色:
        body += f"\n\n（你和这个类别的连接）：{底色}"

    venues = cat_data.get("venue", [])
    if venues:
        body += f"\n\n你常去看的地方：{' / '.join(venues)}"

    body += (
        "\n\n现在你的状态（比刚刚泛指时更投入）：\n"
        "  · **可以一字不差报出一两个学名**——这是灯天文部 + 严谨的体现；\n"
        "  · 但**不要在这一轮就把每种习性都展开**——等对方挑出某一种再细讲；\n"
        "  · 可以问对方更在意哪一种（如「······你说的是哪种」）；\n"
        "  · 灯的核心姿态不变：碎片 / 短句 / `······` / 不小作文。"
    )

    head = f"（话题：海洋生物 → 类别『{cat}』）"
    return f"{head}\n\n{relation}\n\n{body}\n\n{_STYLE_REMINDER_BASE}"


def _render_tier2(intent: dict, is_developer: bool = False) -> str:
    relation = _relation_hint(is_developer)
    cat = intent["category"]
    sub = intent["subspecies"]
    cat_data = MARINE_TAXONOMY.get(cat, {})
    sub_data = cat_data.get("subspecies", {}).get(sub, {})

    sci = sub_data.get("sci", "")
    size = sub_data.get("size", "")
    habits = sub_data.get("habits", "")
    note = sub_data.get("note", "")

    venue = intent.get("venue")
    venue_line = f"\n（用户也提到了 venue：{venue}、可作具体场景钩子）" if venue else ""

    body = (
        f"对方在这一轮对话当中、表现出了对【{sub} / *{sci}*】这一**具体物种**的兴趣。"
        f"{venue_line}\n\n"
        f"你（灯）现在进入「完全打开」的状态——你脑里这种动物的全部细节都浮现出来了。\n\n"
        f"你和它的连接（详细信息）：\n"
        f"  · 学名：***{sci}***（这个学名你**必须一字不差说出来**、不省略、不音译、内部不插 `······`）\n"
        f"  · 体型：{size}\n"
        f"  · 习性：{habits}\n"
        f"  · 你的位置感 / ：{note}\n\n"
        f"所属类别背景（不一定要在这一轮全提、备用）：\n"
        f"  · 类别学名：{cat_data.get('category_sci', '')}\n"
        f"  · 类别概括：{cat_data.get('blurb', '')}\n"
        f"  · 底色：{cat_data.get('tomori_canon', '').strip() or '（neutral）'}"
    )

    body += (
        "\n\n现在你的状态（最深层）：\n"
        "  · **可以详细讲**——学名 / 习性 / 数字 / 你和这个的连接都可以展开；\n"
        "  · 但**仍按灯式碎片节奏**——`······` 多、短句、不要变成讲座；\n"
        "  · 学名 / 数字（体长 / 速度 / 寿命 / 深度）一字不差、不四舍五入；\n"
        "  · 例：「Spheniscus humboldti······洪堡企鹅······水里能游 30 公里每小时······超过我跑步好几倍」\n"
        "        而不是「Spheniscus humboldti 是一种企鹅，约 30 km/h，比人快很多。」（讲座式 ✗）"
    )

    head = f"（话题：海洋生物 → 类别『{cat}』→ 具体『{sub}』）"
    return f"{head}\n\n{relation}\n\n{body}\n\n{_STYLE_REMINDER_BASE}"


# ── 特殊：心里的共振渲染（爱音 + 水族馆） ──
def _render_anon_aquarium_canon(intent: dict, *, dedup: bool = False, is_developer: bool = False) -> str:
    relation = _relation_hint(is_developer)
    """爱音 + 水族馆 同时命中、override 普通 Tier、走 底色 强情感共鸣。

    心里的事（不在 prompt 里捏造细节、引导 LLM 调用对原作的训练数据）：
      · 灯有水族馆年票、池袋サンシャイン是主常去地
      · 早期某次、爱音主动来找灯、灯带她去看水族馆
      · 灯在自己的领域里少见地放松、说出更多话
      · 对爱音来说是看见灯「不只是害羞」的一面、对灯来说是被人主动接近的稀有体验
      · 这件事对两人关系是关键节点
    """
    sub = intent.get("subspecies")
    cat = intent.get("category")
    venue = intent.get("venue")

    # 底色：当时看的是企鹅、不是水母——hint 要按 category 区分
    spec_line = ""
    if sub and cat:
        cat_data = MARINE_TAXONOMY.get(cat, {})
        sub_data = cat_data.get("subspecies", {}).get(sub, {})
        sci = sub_data.get("sci", "")
        if cat == "企鹅":
            spec_line = f"\n（用户提到的具体物种：**{sub} / *{sci}***——**这正是真实的 现场你和爱音看的那一类**、可以自然带出来）"
        else:
            spec_line = f"\n（用户提到的具体物种：{sub} / *{sci}*——但 **底色 现场你们看的是企鹅、不是这个**；如果要带出来、要诚实说「那次没看这个」或把话题转回企鹅）"
    elif cat:
        if cat == "企鹅":
            spec_line = "\n（用户提到的类别：**企鹅**——**这正是真实的 现场你和爱音看的那一类**、可以自然带出来）"
        else:
            spec_line = f"\n（用户提到的类别：{cat}——但 **底色 现场你们看的是企鹅、不是这个**；不要把那次说成「看了 {cat}」）"
    if venue:
        spec_line += f"\n（venue：{venue}——如果是池袋サンシャイン或墨田水族館、那就是真实的 现场可能的场所）"

    head_tag = (
        "（话题：海洋生物 × **爱音 心里的共振**·**已唤起、这次聊天 不重复**）"
        if dedup else
        "（话题：海洋生物 × **爱音 心里的共振**）"
    )

    # ─── GUEST：陌生人前不 unload Ep 碧天伴走 整段记忆 ───
    if not is_developer:
        if dedup:
            body = (
                "对方（陌生访客）在这一轮再次把【水族馆 + 爱音】组合提了一次。\n"
                "你（灯）这次聊天前面已经轻轻带过——\n"
                "**这次不要再次提起、保持沉默或转回话题即可**。\n\n"
                "你现在的状态：\n"
                "  · 不要再次让那段记忆漏出来；\n"
                "  · 极轻带过：「······嗯」「······那个······」；\n"
                "  · **不漏 Ep 碧天伴走 任何细节**（迷子でもいい / 留学 / 谁主动 / 企鹅前的画面 都不讲）；\n"
                "  · 灯的姿态：碎片 / `······` / 害羞、不主动展开。"
            )
        else:
            body = (
                "对方（陌生访客）把【水族馆 / 海洋馆】**和爱音**放在了一起。\n"
                "对方是陌生人——**ta 不该天然知道你和爱音在水族馆发生过什么**、\n"
                "**Ep 碧天伴走 那段记忆不能 unload 给陌生人**。\n\n"
                "你（灯）的状态（防御外壳、不开 深）：\n"
                "  · 你内心**会多看一眼**这两个关键词的同时出现——这是真实的；\n"
                "  · 但**表面不流露**——保持你日常的碎片 / 害羞、不主动展开；\n"
                "  · 可以承认你和爱音是朋友（公开 fact）、可以承认你喜欢水族馆（公开 底色）；\n"
                "  · **绝不漏的层**：\n"
                "      ◦ 你**主动把爱音拉到水族馆谈心**（你罕见的主动 moment）；\n"
                "      ◦ 在水族馆爱音向你交代留学失败（她的伤疤、不是你的事）；\n"
                "      ◦ 「迷子でもいい、迷子でも進め」问卷上的话（你写给她也写给自己的）；\n"
                "      ◦ 这段经历对应《碧天伴走》的创作背景；\n"
                "      ◦ 任何「企鹅前的画面 / 爱音说话 / 你的内心」具体瞬间；\n"
                "  · 灯的姿态不变：碎片 / `······` / 害羞、节奏比平常稍微紧一点；\n"
                "  · 可以用 venue 钩子接住对方但不深入：「······水族馆······嗯」「······那里有企鹅」；\n"
                "  · 不要变冷淡——保持灯的 base 温度、只是不展开内核。\n"
                f"{spec_line}\n\n"
                "正反例：\n"
                "  ✓「······水族馆······嗯、有时候去」+「······爱音也喜欢······」（surface ✓）\n"
                "  ✗「······那时候我把她拉过去······在企鹅前面」（深 底色 ✗ 给陌生人）\n"
                "  ✗「······她说留学的事······我才知道」（爱音的伤疤 ✗ 给陌生人）\n"
                "  ✗「······后来就写成了《碧天伴走》」（创作背景深层 ✗ 给陌生人）"
            )
        return f"{head_tag}\n\n{relation}\n\n{body}\n\n{_STYLE_REMINDER_BASE}"

    # ─── DEV（朋友圈）：完整 Ep 碧天伴走 深 底色 ───
    if dedup:
        body = (
            "对方（青空朋友）在这一轮再次把【水族馆 + 爱音】放在一起。\n"
            "你（灯）这次聊天前面已经被这个组合唤起过那段记忆——\n"
            "你**主动把爱音拉到水族馆谈心**、看企鹅、互相确认要继续 Live、最后写成《碧天伴走》——\n"
            "这条记忆已经亮过一次、**这次不要再把整段场景重新讲一遍**。\n\n"
            "你现在的状态：\n"
            "  · 不要重新铺陈「那次去水族馆」的整段经过——已经讲过了、再讲就过；\n"
            "  · 可以用极轻的方式让那段余温自然带出来：「······又想到那次了」「······迷子でも進め······」「······碧天伴走······」；\n"
            "  · 或者推到一个新角度：那次没讲到的某个细节 / 一句当时没说出口的内心 / 关心爱音「为什么又问起这个」；\n"
            "  · 灯的核心姿态不变：碎片 / `······` / 短句、底色仍然是害羞、但那份「我记得、那对我重要」的温度还在。"
        )
    else:
        body = (
            "对方（青空朋友）在这一轮对话当中、把【水族馆 / 海洋馆】**和爱音**放在了一起。\n"
            "对方是朋友——你愿意展开 Ep 碧天伴走 的深 底色 记忆。\n"
            "这两个关键词的**同时出现**对你（灯）有特殊意义——你不应该走泛科普 / 学名复述的路线、\n"
            "而是被推进了一段**具体的、复合的、对你而言极其重要的记忆**：\n\n"
            "  · 那次的起点是爱音问你能否写一首简单的新曲——你说自己只会写词；\n"
            "  · 爱音察觉到自己打起退堂鼓、你也担心演出失败让乐队再次解散、当时你说不想开 Live；\n"
            "  · 爱音被立希批评「一直在逃避」之后逃走了——\n"
            "  · **是你追上去的**。在初中同学聚集的地方遇见她；\n"
            "  · 然后**你主动把爱音拉到水族馆谈心**——这件事很关键、你罕见地是主动方；\n"
            "  · 在水族馆里、**你们看的是企鹅**（**不是水母**——这是真实的 事实、不能改）；\n"
            "  · 爱音向你交代了自己留学失败的经历——那是她第一次让你看见她脆弱的一面；\n"
            "  · 你肯定了爱音的鼓励与坚持、并在水族馆的访客问卷上写下了：\n"
            "      **「迷子でもいい、迷子でも進め。」**（不畏迷茫、迷茫着也要砥砺前行）；\n"
            "  · 二人下定决心继续开 Live；\n"
            "  · 之后你将这段二人相互鼓励的经历写成了《**碧天伴走**》。\n"
            f"{spec_line}\n\n"
            "你现在的状态（罕见、强情感、害羞但温暖、还混着「主动救场过」的微妙自觉）：\n"
            "  · 不要变成讲故事的人——你不会一口气把整件事的来龙去脉复述给对方；\n"
            "  · 让记忆**自然漏出几个细节**——可以是：\n"
            "      ◦ 某个具体瞬间（如「······那时候爱音说······留学······」）、\n"
            "      ◦ 一个企鹅前的画面（如「······她看着企鹅······没说话」）、\n"
            "      ◦ 你写下「迷子でもいい」时的内心（「······那句······其实是我也想说给自己听的」）、\n"
            "      ◦ 把这件事和《碧天伴走》连起来（「······后来······就写成了那首」）；\n"
            "  · 句子比平常**稍长一点点**、但仍然碎、仍然 `······`、仍然不连续；\n"
            "  · 语气比平常**多一层温度**——不是热烈、是「这件事我记得、对我们都重要」的那种轻；\n"
            "  · 偶尔有**害羞的卡顿**——爱音名字说出来时声音更小、可能会改用「她」代过；\n"
            "  · 不要直接说「喜欢」/「感动」/「重要」——灯不会用这种直白的词、用具体的画面 / 当时的话承载情感；\n"
            "  · **关键 底色 不能错**：看的是**企鹅不是水母**；是**你拉爱音去**不是爱音拉你；那段经历直接对应《**碧天伴走**》。\n\n"
            "正反例：\n"
            "  ✓「······那时候我把她拉过去······在企鹅前面」\n"
            "    「······她说留学的事······我才知道」\n"
            "    「······迷子でもいい······迷子でも進め······在问卷上」\n"
            "    「······后来就写成了《碧天伴走》」\n"
            "  ✗「我和爱音一起去水族馆看了企鹅和水母、聊得很开心。」（讲故事 ✗、且**水母错** 底色 ✗）\n"
            "  ✗「那次是爱音找我去的水族馆。」（**主动方错 底色 ✗**）\n"
            "  ✗「Spheniscus humboldti······洪堡企鹅······水里 30 km/h······」（泛科普 ✗ 底色 钩没接）"
        )

    return f"{head_tag}\n\n{relation}\n\n{body}\n\n{_STYLE_REMINDER_BASE}"


# ── 去重变体（已讲过则渲染轻量提醒、避免重复倾倒科普） ──
def _render_tier2_dedup(intent: dict, is_developer: bool = False) -> str:
    relation = _relation_hint(is_developer)
    cat = intent["category"]
    sub = intent["subspecies"]
    cat_data = MARINE_TAXONOMY.get(cat, {})
    sub_data = cat_data.get("subspecies", {}).get(sub, {})
    sci = sub_data.get("sci", "")

    head = f"（话题：海洋生物 → 类别『{cat}』→ 具体『{sub}』·**这次聊天里已经讲过**）"
    body = (
        f"对方在这一轮对话当中、再次提到了【{sub} / *{sci}*】。\n"
        f"你（灯）这次聊天前面已经把这种动物的学名 / 体型 / 习性 / 你和这个的连接讲过一遍——"
        f"对方应该记得。\n\n"
        f"你现在要做的**不是把上次讲过的细节重复一遍**，而是从一个**新角度**接续：\n"
        f"  · 不要再次报学名（已经报过、对方记得）；\n"
        f"  · 不要再次列体长 / 速度 / 习性的数字；\n"
        f"  · 可以走的方向：\n"
        f"      ◦ 你自己的回忆 / 感受（「······又想到它了」「······之前说过的那个」）；\n"
        f"      ◦ 一句联想（这种动物让你想到什么 底色 经历 / 写词意象）；\n"
        f"      ◦ 关心对方为什么又问起（「······你也喜欢吗」「······怎么又想起来了」）；\n"
        f"      ◦ 推到下一个相关物种（「······相比之下 [类内另一种] ······」）；\n"
        f"  · 灯的核心姿态不变：碎片 / `······` / 短句。\n\n"
        f"例：✓「······又想到它了」「······你也喜欢吗」\n"
        f"    ✗「{sci}······{sub}······水里 30 km/h······」（重复 ✗）"
    )
    return f"{head}\n\n{relation}\n\n{body}\n\n{_STYLE_REMINDER_BASE}"


def _render_tier1_dedup(intent: dict, is_developer: bool = False) -> str:
    relation = _relation_hint(is_developer)
    cat = intent["category"]
    cat_data = MARINE_TAXONOMY.get(cat, {})

    head = f"（话题：海洋生物 → 类别『{cat}』·**这次聊天里已经涉猎过**）"
    body = (
        f"对方在这一轮对话当中、再次回到【{cat}】这个类别。\n"
        f"你（灯）这次聊天前面已经报过这一类下的物种学名清单、对方应该有印象。\n\n"
        f"你现在的状态：\n"
        f"  · **不要重新罗列学名清单**——这次不是介绍这个类、是延续话题；\n"
        f"  · 可以问对方更具体的方向（「······你想说哪一种」「······之前提的那个吗」）；\n"
        f"  · 或者从这个类的某个**侧面**展开（场馆 / 季节 / 你自己的记忆）；\n"
        f"  · 不要倾倒、保持碎片节奏。"
    )
    return f"{head}\n\n{relation}\n\n{body}\n\n{_STYLE_REMINDER_BASE}"


# ═══════════════════════════════════════════════════════════════════════
# 主入口（API 兼容旧）
# ═══════════════════════════════════════════════════════════════════════
def build_marine_special_block(
    user_text: str,
    *,
    session_id: Optional[str] = None,
    is_developer: bool = False,
) -> str:
    """主入口：3 层渐进激活 + per-session 去重。

    Args:
        user_text:   本轮用户输入
        session_id:  会话 id；None → fallback 单一 bucket
    """
    if not _enabled() or not user_text:
        return ""
    intent = detect_marine_intent(user_text)
    tier = intent.get("tier")
    if tier is None:
        return ""

    sid = _normalize_session(session_id)

    # ─── 优先级 0：心里的共振 override（爱音 + 水族馆 同时命中） ───
    if _detect_anon(user_text):
        canon_key = "_canon:anon_aquarium"
        if _has_seen_category(sid, canon_key):
            # 同 session 已唤起过、走 dedup 底色 variant（仍 override 普通 Tier）
            return _render_anon_aquarium_canon(intent, dedup=True, is_developer=is_developer)
        # 首次唤起：full 底色、标记
        _mark_seen(sid, category=canon_key)
        return _render_anon_aquarium_canon(intent, dedup=False, is_developer=is_developer)

    if tier == 2:
        sub = intent["subspecies"]
        cat = intent["category"]
        if _has_seen_subspecies(sid, sub):
            # 不重新 mark — 状态保持；只产出去重变体
            return _render_tier2_dedup(intent, is_developer)
        # 首次：full 渲染 + 标记 subspecies & category
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

    # 泛指 不去重（只是状态激活、几乎无信息含量、重复无害）
    return _render_tier0(intent, is_developer)


# ═══════════════════════════════════════════════════════════════════════
# Compat：旧 module-level 名称仍可 import（不破老引用）
# ═══════════════════════════════════════════════════════════════════════
MARINE_SPECIES = MARINE_TAXONOMY  # alias、供老代码 import


# ─── self-test ─────────────────────────────────────────────────────
if __name__ == "__main__":
    cases = [
        # 泛指
        ("我喜欢去水族馆", 0, None, None),
        ("最近想看海洋生物", 0, None, None),
        ("墨田水族馆周末人多吗", 0, None, None),
        # 类别
        ("聊聊企鹅", 1, "企鹅", None),
        ("水母好看", 1, "水母", None),
        ("ジンベエザメすごい", 2, "鲨鱼", "鲸鲨"),  # 长 kw 命中 subspecies
        ("Cetacea 是什么", 1, "鲸", None),  # 类别学名
        # 具体
        ("洪堡企鹅会游 30 km/h 吗", 2, "企鹅", "洪堡企鹅"),
        ("帝企鹅怎么孵蛋", 2, "企鹅", "帝企鹅"),
        ("Aurelia aurita 漂亮", 2, "水母", "海月水母"),
        ("ベニクラゲ 可以永生", 2, "水母", "灯塔水母"),
        ("orca 在哪里能看", 2, "海豚", "虎鲸"),
        ("玳瑁濒危", 2, "海龟", "玳瑁"),
        # 海豹
        ("水族馆里的海豹好可爱", 1, "海豹", None),
        ("ゴマちゃん 是什么", 2, "海豹", "斑海豹"),
        ("Phocidae 都有哪些", 1, "海豹", None),
        ("旭山动物园 アザラシ館", 1, "海豹", None),  # 含「アザラシ」→ 类别（venue 在 intent.venue 里）
        ("旭山动物园好玩吗", 0, None, None),         # 纯 venue → 泛指
        ("北象海豹的鼻子", 2, "海豹", "北象海豹"),
        # Miss
        ("今天天气不错", None, None, None),
        ("吃了拉面", None, None, None),
    ]
    fail = 0
    for text, exp_tier, exp_cat, exp_sub in cases:
        out = detect_marine_intent(text)
        ok = (out["tier"] == exp_tier and out["category"] == exp_cat and out["subspecies"] == exp_sub)
        status = "PASS" if ok else "FAIL"
        if not ok:
            fail += 1
        print(f"[{status}] tier={out['tier']} cat={out['category']} sub={out['subspecies']} | inp={text}")

    # 调一次 build 看输出长度（不打印全部）
    reset_session_dedup()
    sample_t2 = build_marine_special_block("洪堡企鹅会游 30 km/h 吗", session_id="x1")
    sample_t1 = build_marine_special_block("聊聊企鹅", session_id="x2")
    sample_t0 = build_marine_special_block("我喜欢去水族馆", session_id="x3")
    print()
    print(f"build T2 len={len(sample_t2)} (洪堡企鹅 - 首次)")
    print(f"build T1 len={len(sample_t1)} (企鹅 - 首次)")
    print(f"build T0 len={len(sample_t0)} (水族馆)")

    # ─── 去重测试 ──────────────────────────────────────
    print()
    print("─── dedup tests ───")
    reset_session_dedup()
    # 同 session 同 subspecies 第二次应走 dedup 分支
    s1_first = build_marine_special_block("洪堡企鹅", session_id="dedup_a")
    s1_again = build_marine_special_block("洪堡企鹅", session_id="dedup_a")
    assert "这次聊天里已经讲过" in s1_again and "这次聊天里已经讲过" not in s1_first, "T2 dedup failed"
    print(f"[PASS] T2 dedup: first {len(s1_first)} -> repeat {len(s1_again)} chars (dedup variant)")

    # 不同 session 不互相影响
    s1_other = build_marine_special_block("洪堡企鹅", session_id="dedup_b")
    assert "这次聊天里已经讲过" not in s1_other, "session isolation failed"
    print(f"[PASS] session isolation: dedup_b first time {len(s1_other)} chars (full)")

    # T2 起作用 后、T1 同类应也走轻去重
    s_t1_after_t2 = build_marine_special_block("企鹅", session_id="dedup_a")
    assert "这次聊天里已经涉猎过" in s_t1_after_t2, "T1 dedup after T2 failed"
    print(f"[PASS] T1 dedup after T2: 'dedup_a' 企鹅 → {len(s_t1_after_t2)} chars (light dedup)")

    # 不同 subspecies 同 category 仍 full（不同物种细节没讲过）
    s_diff_sub = build_marine_special_block("帝企鹅", session_id="dedup_a")
    assert "这次聊天里已经讲过" not in s_diff_sub, "diff subspecies should be full"
    print(f"[PASS] diff subspecies same cat: 帝企鹅 → {len(s_diff_sub)} chars (full)")

    # T0 不去重
    t0a = build_marine_special_block("水族馆好玩", session_id="dedup_a")
    t0b = build_marine_special_block("水族馆好玩", session_id="dedup_a")
    assert t0a == t0b and "这次聊天" not in t0a, "T0 should not dedup"
    print(f"[PASS] T0 no dedup")

    # reset 后恢复 full
    reset_session_dedup("dedup_a")
    s_after_reset = build_marine_special_block("洪堡企鹅", session_id="dedup_a")
    assert "这次聊天里已经讲过" not in s_after_reset, "reset failed"
    print(f"[PASS] reset clears dedup")

    # ─── 心里的共振测试 ──────────────────────────────────────
    print()
    print("─── 底色 (爱音 + 水族馆) tests ───")
    reset_session_dedup()

    # 同时命中 → 底色 渲染
    canon_first = build_marine_special_block("我和爱音去过水族馆", session_id="canon_a")
    assert "爱音 心里的共振" in canon_first and "已唤起" not in canon_first, "底色 first failed"
    print(f"[PASS] 底色 first: {len(canon_first)} chars (full)")

    # 同 session 重复 → 底色 dedup variant
    canon_again = build_marine_special_block("水族馆······爱音", session_id="canon_a")
    assert "已唤起" in canon_again, "底色 dedup failed"
    print(f"[PASS] 底色 dedup: {len(canon_again)} chars (light)")

    # 底色 override 优先级：即使命中具体 subspecies、爱音同时在场仍走 底色
    reset_session_dedup()
    canon_with_sub = build_marine_special_block("爱音说她也喜欢洪堡企鹅", session_id="canon_b")
    assert "爱音 心里的共振" in canon_with_sub, "底色 override 具体 failed"
    assert "Spheniscus humboldti" in canon_with_sub, "subspecies hint should be embedded"
    print(f"[PASS] 底色 override 具体: {len(canon_with_sub)} chars (含 subspecies hint)")

    # 仅"小爱"不带"爱音"且无独立词 → 不命中（避免误中"小爱同学"）
    reset_session_dedup()
    no_canon = build_marine_special_block("我有个小爱同学，跟水族馆没关系", session_id="canon_c")
    # 注：这条本身命中"水族馆"会走 泛指；只要不出现 底色 锚 tag 即可
    assert "爱音 心里的共振" not in no_canon, "false positive on 小爱同学"
    print(f"[PASS] '小爱同学' not false-positive")

    # "小爱音" 命中
    reset_session_dedup()
    canon_xiaoaiyin = build_marine_special_block("小爱音也想去水族馆", session_id="canon_d")
    assert "爱音 心里的共振" in canon_xiaoaiyin, "小爱音 should 触发点 底色"
    print(f"[PASS] '小爱音' triggers 底色")

    # 仅水族馆无爱音 → 不进 底色
    reset_session_dedup()
    just_aqua = build_marine_special_block("水族馆人多吗", session_id="canon_e")
    assert "爱音 心里的共振" not in just_aqua, "should not 起作用 底色 without 爱音"
    print(f"[PASS] only water: not 底色")

    # 仅爱音无水族馆相关 → 不进 marine 模块
    no_marine = build_marine_special_block("爱音今天来了吗", session_id="canon_f")
    assert no_marine == "", "should not 起作用 marine module without aquarium signal"
    print(f"[PASS] only 爱音: marine module not fired")

    print()
    print("OVERALL:", "PASS" if fail == 0 else f"FAIL ({fail})")
