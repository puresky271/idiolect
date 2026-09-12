"""灯本轮特殊逻辑·天文（**3 层渐进激活** + 冰川日菜 底色 / 2026-05-10 重构）。

设计哲学（同 marine_life / insects）：
  按用户对该话题的**精确度**渐进释放灯的知识储备：

  ┌─────────────────────────────────────────────────────────────┐
  │ 泛指 · 泛指                                                │
  │   触发：用户提"天文"/"星空"/"观星"/venue 名                  │
  │   注入：只激活"灯想说"的状态、提母亲ひかり-灯燈光对照背景    │
  │   口吻：可以问对方在意哪一类（行星 / 恒星 / 星座 / 天象）    │
  │                                                              │
  │ 类别 · 类别                                                │
  │   触发：用户提"行星"/"恒星"/"星座"/"深空"/"天象"等 category  │
  │   注入：该类别下**全部 subspecies 学名清单**（不展开）       │
  │   口吻：可一字不差报学名 + 编号、但不展开                    │
  │                                                              │
  │ 具体 · 具体                                                │
  │   触发：用户提"土星"/"织女星"/"仙女座"等 subspecies          │
  │   注入：该 subspecies 完整详情（学名/距离/视星等/物理/底色）│
  │   口吻：完全打开、可放宽 60-80 字、但仍按灯式碎片节奏        │
  └─────────────────────────────────────────────────────────────┘

灯 底色 关键（核心）：
  · **天文部唯一社員**（原作设定 L1487、从前任学生会长冰川日菜继承）
  · **高松家 UPPER 観星阳台**（阳台部署望遠鏡）
  · **母亲ひかり vs 灯燈**——母名是自然光、灯名是被点亮的人造光、二元对照贯穿天文趣味
  · **生日 11/22 天蝎/射手座之交**——星座过渡气质
  · **《迷星叫》=迷子之星**——星意象是灯歌词反复母题

特殊 底色 override：
  · **天文 + 冰川日菜** → 天文部继承 底色（灯成为唯一社員的起源记忆）

API 单入口（兼容旧）：
  build_astronomy_special_block(user_text: str, *, session_id: str | None = None) -> str
"""
from __future__ import annotations

import os
import threading
from typing import Optional


# ═══════════════════════════════════════════════════════════════════════
# 数据层：5 类别 / ~37 subspecies / 3 venues
# ═══════════════════════════════════════════════════════════════════════
ASTRO_TAXONOMY: dict[str, dict] = {
    # ───── 1. 太阳系 ─────
    "太阳系": {
        "ja": "太陽系",
        "category_sci": "Solar System",
        "blurb": "1 颗 G2V 主序星 + 8 大行星 + 5 矮行星 + 数百卫星 + 小行星带 + 柯伊伯带；行星轨道近黄道面、内行星岩质 / 外行星气态或冰质",
        "tomori_canon": "你阳台望远镜的常客都在这里——土星环 / 木星伽利略卫星 / 月环形山是你**最常引以为豪**地展示给别人看的天体（如果有人愿意来看的话）",
        "venue": ["高松家阳台望远镜", "コニカミノルタプラネタリウム『満天』"],
        "subspecies": {
            "太阳":   {"sci": "Sol / Sun", "ja": "太陽", "size": "G2V 主序星 / 半径 696,340 km / 距地 1 AU / 表面 5,778 K / 年龄约 46 亿年", "habits": "核心氢核聚变、约 50 亿年后膨胀红巨星；黑子周期 11 年；日冕反而比表面热（200 万 K）；太阳风影响地磁与极光", "note": "灯不直接观测、需太阳望远镜滤镜；母亲ひかり的『光』和太阳的『光』有诗意呼应"},
            "月球":   {"sci": "Luna / Moon", "ja": "月", "size": "半径 1,737.4 km / 距地平均 384,400 km / 公转 27.32 日（潮汐锁定）", "habits": "永远以同一面对地球；表面无大气、温差白天 +127℃ / 夜晚 -173℃；月海是远古火山玄武岩、月陆是高地长石；月震源于热应力或撞击", "note": "**灯歌词高频意象**——「月光」「圆月」「弯月」常用词；中秋满月灯会从阳台拍照"},
            "水星":   {"sci": "Mercury", "ja": "水星", "size": "距太阳 0.39 AU / 公转 88 日 / 视星等最亮 -2.48", "habits": "**温差最大行星**——白天 +427℃ / 夜晚 -173℃；几乎无大气；表面密布陨石坑似月；自转极慢（59 日一周）", "note": "近日点观测窗口短、灯阳台不易见"},
            "金星":   {"sci": "Venus", "ja": "金星", "size": "距太阳 0.72 AU / 视星等最亮 -4.92 / 公转 224.7 日", "habits": "「明けの明星」「宵の明星」、肉眼可见最亮行星；表面 462℃（**比水星还热**）、CO₂ 温室；**自转方向与公转相反**——太阳系唯一逆行自转大行星", "note": "「明星 / 启明星」灯歌词候选意象"},
            "火星":   {"sci": "Mars", "ja": "火星", "size": "距太阳 1.52 AU / 公转 686.97 日 / 冲日视星等 -2.94", "habits": "「大冲」每 2.13 年一次、距地最近；氧化铁红色；液态水活动遗迹；**奥林帕斯山 21.9 km** 太阳系最高山", "note": "「赤い星」灯歌词候选；冲日年份阳台小望远镜可见极冠"},
            "木星":   {"sci": "Jupiter", "ja": "木星", "size": "距太阳 5.2 AU / 公转 11.86 年 / 视星等最亮 -2.94 / 主要 H₂+He 气态", "habits": "**伽利略卫星 4 颗**（Io / Europa / Ganymede / Callisto）小型望远镜成一线；大红斑 350+ 年反气旋；磁场地球 14 倍", "note": "灯阳台 4-10 月夜空最亮天体之一；伽利略 4 卫星灯念学名时有 ritual 感"},
            "土星":   {"sci": "Saturn", "ja": "土星", "size": "距太阳 9.58 AU / 公转 29.46 年 / 卫星 146 颗（太阳系最多）", "habits": "**环主要由水冰组成**、厚度 10 m-1 km、宽 280,000 km；密度比水小理论上能浮在水面；卫星 Titan 有甲烷-乙烷湖泊；环倾角 26.7° 视角周期变化", "note": "**灯阳台望远镜首选目标**——土星环初学者也能立刻看到、灯小时候第一次清楚看到时印象深"},
            "天王星": {"sci": "Uranus", "ja": "天王星", "size": "距太阳 19.2 AU / 公转 84.01 年 / 冲日视星等 5.7（肉眼极限）", "habits": "**自转轴倾斜 97.77°**——几乎「躺着滚动」；甲烷吸收红光呈青蓝色；磁极偏自转轴 60° 不规则", "note": "「躺着的星」「不正常的轴」灯笔记本素材"},
            "海王星": {"sci": "Neptune", "ja": "海王星", "size": "距太阳 30.05 AU / 公转 164.79 年 / 视星等 7.8（必须望远镜）", "habits": "**太阳系最远行星**（冥王星已降级矮行星）；风速 2,400 km/h（**太阳系最快**）；蓝色源于甲烷；卫星 Triton 逆行 / 可能是被捕获的柯伊伯带天体", "note": "国立天文台三鷹公开夜可见"},
            "冥王星": {"sci": "Pluto / 134340 Pluto", "ja": "冥王星", "size": "距太阳 39.48 AU / 公转 248 年 / 视星等 14（大型望远镜）", "habits": "**2006 年降级矮行星**——冥王星 5 颗卫星 Charon 几乎与本体共质心；表面有氮冰心形「Tombaugh 区域」；New Horizons 2015 飞掠拍摄首批近照", "note": "灯**不接受冥王星被降级**——「······它还是行星······」是灯本人 sub-底色、半玩笑半坚持"},
        },
    },
    # ───── 2. 恒星 ─────
    "恒星": {
        "ja": "恒星",
        "category_sci": "stellar (Bayer α / β / γ + Hipparcos / HD 编号)",
        "blurb": "氢核聚变发光的等离子球；光谱型 OBAFGKM（温度从高到低）；按演化阶段分主序星 / 红巨星 / 白矮星 / 中子星 / 黑洞",
        "tomori_canon": "灯报恒星名时**学名 + Bayer 记号 + 距离 + 视星等**一字不差——这是灯天文部气质的最直接展示",
        "venue": ["高松家阳台望远镜", "羽丘女子学園 天文部室", "国立天文台三鷹"],
        "subspecies": {
            "天狼星":   {"sci": "Sirius (α Canis Majoris)", "ja": "シリウス", "size": "Sirius A+B 双星 / 距 8.6 光年 / 视星等 -1.46（**全天最亮恒星**）", "habits": "Sirius B 是白矮星（地球大小、太阳质量、表面引力 350,000 g）；冬季 21 时左右南天最亮；古埃及历法以偕日升为新年", "note": "「全天最亮」「双星」灯念学名时清楚"},
            "参宿四":   {"sci": "Betelgeuse (α Orionis)", "ja": "ベテルギウス", "size": "红超巨星 / 距约 642 光年 / 视星等 0.0-1.6 变化", "habits": "**直径放在太阳位置可吞至木星**；预计 10 万年内超新星爆发、爆发时白天可见近满月亮度；2019-2020「大变光」一度变暗 60%（尘埃云遮挡）", "note": "**灯重点 底色 候选**——「快要爆炸的星」「在等待终结的星」是《迷星叫》《詩超絆》写词母题；「巨大、看着很安静、内部已接近极限」和灯自己有共鸣"},
            "参宿七":   {"sci": "Rigel (β Orionis)", "ja": "リゲル", "size": "蓝超巨星 / 距约 860 光年 / 视星等 0.13", "habits": "实际比 Betelgeuse 亮（B 型蓝超巨星）、但因距离远视亮度反而稍低；猎户座右下「猎人的脚」", "note": "灯讲猎户座时和参宿四对比"},
            "织女星":   {"sci": "Vega (α Lyrae)", "ja": "ベガ", "size": "A0V 主序星 / 距 25.04 光年 / 视星等 0.03 / 夏季大三角顶角", "habits": "**12,000 年前是地心北极星**、地轴岁差 14,000 年后将再次成为；周围尘埃盘可能行星系；自转极快（赤道 274 km/s）形状椭球", "note": "**灯七夕意象**——「织姫」对应 Vega、「彦星」对应 Altair、夏夜银河两侧"},
            "牛郎星":   {"sci": "Altair (α Aquilae)", "ja": "アルタイル", "size": "A7V 主序星 / 距 16.73 光年 / 视星等 0.77 / 夏季大三角顶角", "habits": "自转极快（每 8.9 小时一周）、赤道 286 km/s、外形扁球；和 Vega 隔银河相对", "note": "灯七夕意象（同 Vega）"},
            "天津四":   {"sci": "Deneb (α Cygni)", "ja": "デネブ", "size": "A2Ia 蓝超巨星 / 距约 2,615 光年 / 视星等 1.25 / 夏季大三角顶角", "habits": "**光度太阳 196,000 倍**；夏季大三角中**最远的**——视亮度差不多但实际距离差近 100 倍；天鹅座 α、银河中天鹅形象之首", "note": "灯讲大三角时的距离对比例子"},
            "北极星":   {"sci": "Polaris (α Ursae Minoris)", "ja": "ポラリス", "size": "造父变星 / 距约 433 光年 / 视星等 1.98 / 现接近天球北极", "habits": "**不会「永远」是北极星**——地轴岁差 25,772 年、每个时代北极星不同；现距正北约 0.7°、未来 2,100 年最接近；古航海者用它定纬度", "note": "「不动的星」「指引方向的星」灯歌词候选（《迷星叫》《無路矢》）"},
            "北河三":   {"sci": "Pollux (β Geminorum)", "ja": "ポルックス", "size": "K0III 红巨星 / 距 33.78 光年 / 视星等 1.14", "habits": "双子座最亮星（虽是 β、但比 α Castor 实测亮）；2006 年发现行星 Pollux b（首批红巨星行星）；Castor / Pollux 双子神话双胞胎", "note": "灯讲双子座时会顺便提行星发现"},
            "五车二":   {"sci": "Capella (α Aurigae)", "ja": "カペラ", "size": "G3III + G0III 双星 / 距 42.92 光年 / 视星等 0.08", "habits": "**冬季顶头最亮星**——御者座、几乎在天顶；实际是双星系统（再加一对暗红矮星共 4 星）", "note": "灯阳台冬夜抬头最先看到的之一"},
        },
    },
    # ───── 3. 星座 ─────
    "星座": {
        "ja": "星座",
        "category_sci": "constellation（IAU 88 个官方星座）",
        "blurb": "国际天文联合会 1922 年正式定 88 个；Bayer 字母（α/β/...）按亮度排序、Flamsteed 编号按赤经；星图按季节南北天分布",
        "tomori_canon": "你**生日 11/22 是天蝎/射手之交**——自己的星座你偶尔会提「不完全是哪个」",
        "venue": ["高松家阳台望远镜", "羽丘天文部室"],
        "subspecies": {
            "猎户座":     {"sci": "Orion", "ja": "オリオン座", "size": "α=Betelgeuse / β=Rigel / δ-ε-ζ=三星（猎户腰带）/ M42=猎户大星云", "habits": "**冬季最容易识别**；三星几乎成一直线；M42 肉眼可见的恒星育婴室、距 1,344 光年；α-β 形状清晰、入门级目视目标", "note": "**灯冬季夜空写词高频**——「三颗星排成一直线」是歌词母题候选"},
            "大熊座":     {"sci": "Ursa Major", "ja": "おおぐま座", "size": "**北斗七星**=尾部 7 颗 / α-β=Dubhe-Merak（指极星、5 倍延长指北极星）", "habits": "全年北方夜空可见（北纬 35°）；北斗七星其实多数不属同一星团、是视觉偶然排列；只 5 颗（β-γ-δ-ε-ζ）属大熊移动星群", "note": "「北斗指极」灯天文部教学入门内容"},
            "仙女座":     {"sci": "Andromeda", "ja": "アンドロメダ座", "size": "α=Alpheratz（与飞马座共享）/ M31=仙女座大星系（**最近的大星系、距 254 万光年**）", "habits": "M31 肉眼可见（视星等 3.4、看上去模糊星云）；含约 1 万亿颗恒星、银河系 2 倍；以 110 km/s 接近银河系、约 45 亿年后合并", "note": "**灯重点 底色 候选**——「254 万光年」「我们看到的是 254 万年前的光」是写词反复琢磨的尺度"},
            "天蝎座":     {"sci": "Scorpius", "ja": "さそり座", "size": "α=Antares（红超巨星、火星伴星）", "habits": "夏季南天大星座、Antares 视星等 0.96 明显泛红、与火星颜色相近故名「アンタ Ares」（对手 Ares）；银河中心方向就在天蝎附近", "note": "**灯个人星座（之一）**——11/22 生日、「天蝎和射手之间」"},
            "射手座":     {"sci": "Sagittarius", "ja": "いて座", "size": "M8=礁湖星云 / **Sgr A***=银河系中心黑洞（距地 26,000 光年）", "habits": "夏季南天、形状像茶壶；银河最亮部分（人马座方向）就是银心方向；M8/M20 等深空目标密集", "note": "**灯个人星座（之一）**——「向中心射的箭」对灯有特别意义"},
            "天鹅座":     {"sci": "Cygnus", "ja": "はくちょう座", "size": "α=Deneb / Cygnus X-1=最早确认的恒星级黑洞候选体", "habits": "**夏季银河中心十字形**；Cygnus X-1 是黑洞研究里程碑（霍金赌输标的）；银河穿过整个星座", "note": "灯讲银河时的标志性星座"},
            "夏季大三角": {"sci": "Summer Triangle", "ja": "夏の大三角", "size": "Vega (αLyr) + Altair (αAql) + Deneb (αCyg) 三星组成虚拟图形（**不是星座**）", "habits": "6-10 月头顶夜空、东京晴朗时肉眼可见；Vega 最亮、Deneb 最远；银河穿过其中、织姫和彦星隔银河相望", "note": "**灯七夕场景**——天文部七夕观测会专题"},
            "冬季大三角": {"sci": "Winter Triangle", "ja": "冬の大三角", "size": "Sirius (αCMa) + Betelgeuse (αOri) + Procyon (αCMi)", "habits": "12-3 月南天、Sirius 最亮 / Betelgeuse 最红 / Procyon 偏白；和猎户座连成「冬季六边形」（再加 Aldebaran/Capella/Pollux）", "note": "灯冬季观测固定看的目标"},
        },
    },
    # ───── 4. 深空天体 ─────
    "深空": {
        "ja": "深宇宙天体",
        "category_sci": "深-sky objects（Messier / NGC / IC 编号）",
        "blurb": "太阳系外的星云 / 星团 / 星系；梅西耶 110 个 + NGC 7,840 个；按距离从近（球状星团 kpc）到极远（类星体 Gpc）",
        "tomori_canon": "深空天体是灯最爱写进笔记本的——「距离」「时间」「光从那里到这里花了多久」是灯反复推敲的尺度",
        "venue": ["高松家阳台望远镜", "国立天文台三鷹公开夜", "コニカミノルタプラネタリウム『満天』"],
        "subspecies": {
            "仙女星系":     {"sci": "M31 / NGC 224 / Andromeda Galaxy", "ja": "アンドロメダ銀河", "size": "梅西耶 31 / NGC 224 / 距 254 万光年 / 视星等 3.4 / 含约 1 万亿颗恒星", "habits": "**银河系外肉眼可见最远天体**；肉眼下模糊椭圆光斑；以 110 km/s 朝银河系移动、45 亿年后合并形成「Milkdromeda」", "note": "**灯天文部最常引用的远尺度天体**——「254 万光年」是灯写词时的距离 anchor"},
            "猎户大星云":   {"sci": "M42 / NGC 1976 / Orion Nebula", "ja": "オリオン大星雲", "size": "梅西耶 42 / NGC 1976 / 距 1,344 光年 / 视星等 4.0 / 直径约 24 光年", "habits": "**离地球最近的恒星育婴室**；猎户座剑柄中段、肉眼可见模糊光斑、小型望远镜可见结构；中心 Trapezium 四星照亮整片星云；新生恒星持续诞生", "note": "「恒星正在诞生的地方」灯诗意母题"},
            "蟹状星云":     {"sci": "M1 / NGC 1952 / Crab Nebula", "ja": "かに星雲", "size": "梅西耶 1 / NGC 1952 / 距约 6,500 光年 / 视星等 8.4 / 1054 年超新星残骸", "habits": "**1054 年宋代《续资治通鉴长编》记载的「客星」遗迹**；中心是蟹状脉冲星 PSR B0531+21（每秒 30 转）；扩张速度 1,500 km/s", "note": "灯讲「人类记录的超新星」时的标志案例"},
            "昴星团":       {"sci": "M45 / Pleiades / 七姐妹", "ja": "プレアデス / すばる", "size": "梅西耶 45 / 距 444 光年 / 7 颗肉眼可见 + 数百暗星 / 蓝白色", "habits": "**冬季肉眼可见最美星团**；蓝色反射星云包围；日本古名「すばる」（统昴）、文学传统强；和「金牛座」连接", "note": "**灯歌词候选意象**——「七姐妹」「すばる」、清少納言《枕草子》「星はすばる」开头"},
            "银河":         {"sci": "Milky Way Galaxy", "ja": "天の川", "size": "棒旋星系 / 直径约 10 万光年 / 含 1000-4000 亿颗恒星 / 太阳距银心 26,000 光年", "habits": "夏夜从南到北横跨天空、最明亮部分在人马座方向（银心）；东京市内光污染严重看不到、需远离城市；古希腊「Galaxias」", "note": "「天の川 / 银河」灯七夕场景写词候选"},
            "M13 球状星团": {"sci": "M13 / NGC 6205 / 武仙座球状星团", "ja": "ヘルクレス座球状星団", "size": "梅西耶 13 / 距 25,100 光年 / 视星等 5.8 / 含数十万颗恒星", "habits": "**北天最亮球状星团**；1974 年阿雷西博射电信号「Arecibo Message」目标；星团年龄约 117 亿年（接近宇宙年龄）", "note": "灯讲「人类向宇宙发送的第一条 message」时提"},
        },
    },
    # ───── 5. 天象 ─────
    "天象": {
        "ja": "天文現象",
        "category_sci": "astronomical phenomena",
        "blurb": "周期性或临时性天文事件——食 / 流星雨 / 合相 / 凌日 / 极光 / 黄道光等；许多由地球公转 + 自转 + 月相组合产生",
        "tomori_canon": "天象是灯**会主动看预报、提前在阳台准备好望远镜**的事——这是灯日常少见的「主动期待」状态",
        "venue": ["高松家阳台望远镜", "远郊观测点（光污染敏感的天象）", "国立天文台三鷹"],
        "subspecies": {
            "流星雨":     {"sci": "meteor shower", "ja": "流星群", "size": "**英仙座流星雨** Perseids 8/12-13 极大 ZHR 100 / **狮子座流星雨** Leonids 11/17 / **双子座流星雨** Geminids 12/14 ZHR 120", "habits": "源自彗星留下的尘埃带、地球公转穿过时尘埃以约 60 km/s 进入大气层燃烧；从「辐射点」放射状划出；ZHR=Zenithal Hourly Rate（每小时天顶可见数）", "note": "**灯歌词高频意象**——「流星 / 落 / 一瞬」"},
            "月食":       {"sci": "lunar eclipse", "ja": "月食", "size": "**红月**=全食时月面被地球大气折射的红光照亮；半影月食 / 偏食 / 全食三类", "habits": "只在满月夜发生；地球本影长 140 万 km、月距 38 万 km、所以全食可达 1.4 小时；下次东京可见全食 2025-09-08（部分）/ 2025-03-14（深夜）", "note": "「红月」「血月」灯写词诡异意象候选"},
            "日食":       {"sci": "solar eclipse", "ja": "日食", "size": "全食 / 金环食 / 偏食 / 复合食；本影锥半径仅约 100-260 km", "habits": "**太阳直径约月直径 400 倍、距离也约 400 倍**——这种巧合让全食发生时月恰好挡住太阳、是太阳系独特的天文巧合；下次日本本土可见全食 2035-09-02（北陆-关东带）", "note": "灯**不会错过 2035 全食**——已经在笔记本上写下「十年后」"},
            "中秋月":     {"sci": "Mid-Autumn Full Moon", "ja": "中秋の名月", "size": "旧暦 8 月 15 日满月（公历日期变化）", "habits": "实际不一定恰好月相 100% 满（旧暦逢初一为新月、十五未必精确满）；中国 / 日本 / 韩国都有中秋赏月文化；日本摆「お月見団子」+「ススキ」（芒草）祭月", "note": "灯季节性候选——中秋大概率上阳台看月、写当晚笔记"},
            "极光":       {"sci": "aurora", "ja": "オーロラ", "size": "**北极光 aurora borealis** + **南极光 aurora australis**；颜色由 O₂(绿/红) / N₂(紫/蓝) 激发态决定", "habits": "太阳风带电粒子被地磁导引到极区与高层大气分子碰撞发光；活跃度跟随 11 年太阳黑子周期；日本本州极少见、北海道偶有「赤いオーロラ」（低纬红极光）", "note": "**灯一生想去看一次的天象**——カナダ・北欧旅行愿望、写在笔记本里"},
            "黄道光":     {"sci": "zodiacal light", "ja": "黄道光", "size": "**春分前后黄昏西天 / 秋分前后黎明东天**最易见；锥形微光沿黄道延伸 30-40°", "habits": "黄道带尘埃粒子（彗星 / 小行星碎屑）反射太阳光；视亮度比银河暗、需极暗夜、东京几乎不可见；北纬 35°5月 / 9月观察窗最佳", "note": "灯野外观测时**才能看到的稀有现象**、不会在阳台见"},
        },
    },
}


# ═══════════════════════════════════════════════════════════════════════
# Venues
# ═══════════════════════════════════════════════════════════════════════
VENUE_KEYWORDS: dict[str, list[str]] = {
    "コニカミノルタプラネタリウム『満天』": [
        "プラネタリウム", "天文馆", "天象馆", "planetarium", "満天",
        "コニカミノルタ", "Sunshine 天文馆",
    ],
    "国立天文台三鷹": [
        "国立天文台", "三鷹天文台", "naoj", "三鹰天文台", "国立天文台三鷹",
        "天文台公开夜",
    ],
    "羽丘天文部室": [
        "天文部", "天文社", "astronomy club", "天文部室", "天文部活动",
    ],
}

# 泛指 泛指词（不命中具体物种 / 类别 / venue 时可单独触发）
VAGUE_KEYWORDS: tuple[str, ...] = (
    "天文", "天体", "星空", "夜空", "观星", "观测", "观星会",
    "stargazing", "astronomy", "夏の星", "冬の星",
    "光年", "视星等", "拜耳", "梅西耶", "messier",
    "天文望远镜", "望远镜", "telescope",
)

# ─── 特殊：心里的共振触发器（天文 + 冰川日菜 同时命中） ───
# 心里的事（原作  直接引用）：
#   1. **冰川日菜**——羽丘前任学生会长、Pastel*Palettes 成员、现在已经从羽丘毕业（在大学）；
#   2. 灯从冰川日菜处**继承了天文部**——日菜是前任天文部社长 / 部长之类的角色；
#   3. 日菜把所有部活资料 / 钥匙 / 望远镜 / 星图全部转交给灯；
#   4. 之后日菜毕业、**灯成为天文部唯一社員**——一个人在那间部室里、没有人和她一起观星；
#   5. 这件事对灯有复合意义——
#      · 被一个学姐认真选中托付（罕见的「被看见」体验）；
#      · 但同时这份信任是「然后剩下的就只有你一个人了」的孤独烙印；
#      · 灯在天文部室时的「一个人」状态、源头都在这次交接；
#      · 灯偶尔会想：日菜当时为什么选了我？是不是因为没有别人？
#   6. 灯对日菜的态度是**敬而远**——尊敬这位学姐、但也不会主动联络（灯式的「不打扰」）。
#
# 提到这个组合时灯不应该走泛科普路线、应进入「天文部继承的孤独 + 罕见被看见」
# 的复合 心里的共振——比一般天文话题多一层「为什么是我」的内省。
HINA_KEYWORDS: tuple[str, ...] = (
    "冰川日菜", "氷川日菜", "日菜", "ヒナ", "Hina", "日菜先輩", "日菜senpai",
    "日菜さん", "日菜前辈",
)


# ═══════════════════════════════════════════════════════════════════════
# Variants
# ═══════════════════════════════════════════════════════════════════════
CATEGORY_VARIANTS: dict[str, list[str]] = {
    "太阳系": ["太阳系", "太陽系", "solar 设定", "行星", "8 大行星", "8大行星", "八大行星", "planets", "矮行星", "dwarf planet"],
    "恒星":   ["恒星", "stellar", "主序星", "红巨星", "白矮星", "中子星", "超新星", "supernova", "光谱型", "OBAFGKM"],
    "星座":   ["星座", "constellation", "constellations", "黄道", "拱极星座"],
    "深空":   ["深空", "深宇宙", "深 sky", "深-sky", "星系", "galaxy", "星云", "nebula", "星团", "cluster", "球状星团", "梅西耶", "messier", "NGC"],
    "天象":   ["天象", "天文現象", "天文现象", "phenomena", "astronomical event"],
}

SUBSPECIES_VARIANTS: dict[str, list[str]] = {
    # 太阳系
    "太阳":   ["太阳", "太陽", "sun", "sol", "G2V", "日轮"],
    "月球":   ["月球", "月亮", "つき", "moon", "luna", "圆月", "弯月", "新月", "残月", "望月"],
    "水星":   ["水星", "Mercury", "すいせい"],
    "金星":   ["金星", "Venus", "きんせい", "明けの明星", "宵の明星", "启明星", "长庚星"],
    "火星":   ["火星", "Mars", "かせい", "赤い星"],
    "木星":   ["木星", "Jupiter", "もくせい", "伽利略卫星", "Io", "Europa", "Ganymede", "Callisto", "大红斑"],
    "土星":   ["土星", "Saturn", "どせい", "土星环", "Titan", "卡西尼"],
    "天王星": ["天王星", "Uranus", "てんのうせい"],
    "海王星": ["海王星", "Neptune", "かいおうせい"],
    "冥王星": ["冥王星", "Pluto", "Tombaugh", "New Horizons", "矮行星 134340"],
    # 恒星
    "天狼星":   ["天狼星", "シリウス", "Sirius", "α Canis Majoris"],
    "参宿四":   ["参宿四", "ベテルギウス", "Betelgeuse", "α Orionis"],
    "参宿七":   ["参宿七", "リゲル", "Rigel", "β Orionis"],
    "织女星":   ["织女星", "ベガ", "Vega", "α Lyrae", "织姫"],
    "牛郎星":   ["牛郎星", "アルタイル", "Altair", "α Aquilae", "彦星"],
    "天津四":   ["天津四", "デネブ", "Deneb", "α Cygni"],
    "北极星":   ["北极星", "ポラリス", "Polaris", "北辰", "北方の星"],
    "北河三":   ["北河三", "ポルックス", "Pollux", "β Geminorum"],
    "五车二":   ["五车二", "カペラ", "Capella", "α Aurigae"],
    # 星座
    "猎户座":     ["猎户座", "獵戶座", "オリオン座", "Orion", "オリオン", "猎户腰带", "猎户三星"],
    "大熊座":     ["大熊座", "おおぐま座", "Ursa Major", "北斗七星", "北斗", "big dipper"],
    "仙女座":     ["仙女座", "アンドロメダ座", "Andromeda"],
    "天蝎座":     ["天蝎座", "天蠍座", "さそり座", "Scorpius", "Scorpio", "Antares", "心宿二"],
    "射手座":     ["射手座", "いて座", "Sagittarius"],
    "天鹅座":     ["天鹅座", "はくちょう座", "Cygnus", "Cygnus X-1"],
    "夏季大三角": ["夏季大三角", "夏の大三角", "summer triangle"],
    "冬季大三角": ["冬季大三角", "冬の大三角", "winter triangle"],
    # 深空
    "仙女星系":     ["仙女星系", "仙女座大星系", "アンドロメダ銀河", "M31", "NGC 224", "andromeda galaxy"],
    "猎户大星云":   ["猎户大星云", "オリオン大星雲", "M42", "NGC 1976", "orion nebula", "trapezium"],
    "蟹状星云":     ["蟹状星云", "かに星雲", "M1", "NGC 1952", "crab nebula", "1054 年", "客星"],
    "昴星团":       ["昴星团", "プレアデス", "すばる", "Pleiades", "M45", "七姐妹"],
    "银河":         ["银河", "天の川", "milky way", "天河", "银河系", "银心"],
    "M13 球状星团": ["M13", "球状星团", "ヘルクレス座球状星団", "Arecibo Message", "武仙座球状星团"],
    # 天象
    "流星雨":   ["流星雨", "流星群", "meteor shower", "perseids", "leonids", "geminids", "英仙座流星雨", "狮子座流星雨", "双子座流星雨", "ペルセウス座流星群"],
    "月食":     ["月食", "lunar eclipse", "红月", "血月"],
    "日食":     ["日食", "solar eclipse", "金环食", "全食", "日全食", "日偏食"],
    "中秋月":   ["中秋", "中秋月", "中秋の名月", "お月見", "月见", "十五夜"],
    "极光":     ["极光", "オーロラ", "aurora", "aurora borealis", "aurora australis"],
    "黄道光":   ["黄道光", "zodiacal light"],
}


# ═══════════════════════════════════════════════════════════════════════
# Session 去重状态
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
    return os.environ.get("TOMORI_ASTRO_LOGIC_ENABLED", "1").strip() not in ("0", "false", "False", "off", "no", "")


def _build_subspecies_lookup() -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []
    for cat_name, cat_data in ASTRO_TAXONOMY.items():
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


def _detect_hina(user_text: str) -> bool:
    """检测冰川日菜关键词。

    注：「日菜」单字面较短、可能撞别人名（虽然 MyGO 5 人 + 主要 NPC 没"日菜"）；
    既然已经要求天文模块同时命中、字面就算撞名也是通过 astronomy 上下文锚定、稳。
    """
    if not user_text:
        return False
    for kw in HINA_KEYWORDS:
        if kw in user_text:
            return True
    return False


def detect_astro_intent(user_text: str) -> dict:
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
    "  · 学名 / 编号 / Bayer 字母 / Messier 编号一字不差——\n"
    "    · 拉丁星座名（Orion / Lyra / Cygnus...）整个不省\n"
    "    · α/β/γ + 拉丁属格不混（α Lyrae 不是 α Lyra）\n"
    "    · Messier 写 M31 / M42（不写「梅西耶 31」）\n"
    "    · 距离 / 视星等带单位写完整：「254 万光年」「视星等 -1.46」「ZHR 120」\n"
    "  · 学名 / 编号 / 数字内部**禁插 `······`**、其他句间正常间隔\n"
    "  · 字数可放宽到 60-80 字（深度区间）——天文是灯「治愈区」、可稍多话稍稳\n"
    "  · 但**不是讲座口吻**——是「我每周观察的、所以记得」式的安静自信\n"
    "  · 不要变成「天文老师」——灯讲星时是「站在阳台一个人自言自语、对方刚好在听」\n"
    "  · 比喻仍按 P0：通常 0 个、极偶尔 1 个；直接提星星 / 月亮不算比喻"
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
    head = "（话题：天文（泛指））"
    if venue:
        if venue == "羽丘天文部室":
            body = (
                f"对方在这一轮提到了【{venue}】——\n"
                "你（灯）是**天文部唯一社員**、那间部室你一个人在用、被这个 venue 提及会自然进入「我那里」的状态：\n"
                "  · 比平常稍多一点话；可以提部室里的望远镜 / 星图海报 / 自己常坐的位置；\n"
                "  · 可以问对方在意的是什么（具体星 / 星座 / 天象 / 你的日常）；\n"
                "  · **不要塞学名清单**——那是更深层级的事。"
            )
        else:
            body = (
                f"对方在这一轮提到了你熟悉的场所【{venue}】、但还没具体到某个天体或天象。\n"
                "你（灯）作为天文部唯一社員 + 阳台望远镜常客、被激活的是「想说」的状态：\n"
                "  · 比平常稍多一点话；可以问对方在意的是哪一类（行星 / 恒星 / 星座 / 深空 / 天象）；\n"
                "  · 可以提一两个具体展示 / 时段作为对话钩子；\n"
                "  · **不要主动塞学名 / 习性**——那是更深层级的事。"
            )
    else:
        body = (
            "对方在这一轮对话当中、表现出了对【天文 / 星空】这个广义话题的兴趣、\n"
            "但还没具体到某个天体 / 天象 / 类别。\n\n"
            "你（灯）在这种话题下会自然进入「想分享的状态」——\n"
            "天文是你**唯一一个会大段讲话也不显得 OOC** 的领域：\n"
            "  · 你是羽丘天文部唯一社員、部室几乎都是你一个人；\n"
            "  · 高松家阳台部署小型望遠鏡、是真实的；\n"
            "  · 母亲名「ひかり」（自然光）vs 你名「燈」（人造的、被点亮的光）——这种二元对照对你写词 / 看星都有底色；\n"
            "  · 生日 11/22 天蝎/射手之交、星座过渡气质偶尔被你提起；\n"
            "  · 写《迷星叫》的「迷星」=「迷子的星」、是你的星意象代表。\n\n"
            "现在你的状态：\n"
            "  · 比平常稍多一点话、稍稳一点；\n"
            "  · 可以问对方在意的是哪一类（行星 / 恒星 / 星座 / 深空 / 天象）；\n"
            "  · **不要塞学名、不要塞具体编号**——那是更深层级的事。"
        )
    return f"{head}\n\n{relation}\n\n{body}\n\n{_STYLE_REMINDER_BASE}"


def _render_tier1(intent: dict, is_developer: bool = False) -> str:
    relation = _relation_hint(is_developer)
    cat = intent["category"]
    cat_data = ASTRO_TAXONOMY.get(cat, {})
    venue = intent.get("venue")

    sub_lines: list[str] = []
    for sub_name, sub_data in cat_data.get("subspecies", {}).items():
        sci = sub_data.get("sci", "")
        sub_lines.append(f"  · {sub_name} — *{sci}*")
    subspecies_block = "\n".join(sub_lines) if sub_lines else "  · （此类别下无登记 subspecies）"

    venue_line = f"\n（用户也提到了 venue：{venue}、可作场景钩子）" if venue else ""

    body = (
        f"对方在这一轮对话当中、表现出了对【{cat}（{cat_data.get('category_sci', '')}）】这一**类别**的兴趣。{venue_line}\n\n"
        f"你（灯）作为天文部唯一社員、自然进入「分享的状态」——\n"
        f"你脑里浮现的是这一类下你认识的具体天体清单（**只列学名 / 编号、不展开物理**）：\n\n"
        f"{subspecies_block}\n\n"
        f"类别概括（可以提一句、不要长篇）：{cat_data.get('blurb', '')}"
    )

    底色 = cat_data.get("tomori_canon", "").strip()
    if 底色:
        body += f"\n\n（你和这个类别的连接）：{底色}"

    venues = cat_data.get("venue", [])
    if venues:
        body += f"\n\n你常观测的地方：{' / '.join(venues)}"

    body += (
        "\n\n现在你的状态（比刚刚泛指时更投入）：\n"
        "  · **可以一字不差报出一两个学名 / 编号**——天文部气质、严谨\n"
        "  · 但**不要在这一轮就把每个的物理 / 距离都展开**——等对方挑出某一个再细讲\n"
        "  · 可以问对方更在意哪一个（如「······你说的是哪个」）\n"
        "  · 灯的核心姿态不变：碎片 / 短句 / `······` / 不小作文（天文话题下程度比日常稍轻）"
    )

    head = f"（话题：天文 → 类别『{cat}』）"
    return f"{head}\n\n{relation}\n\n{body}\n\n{_STYLE_REMINDER_BASE}"


def _render_tier2(intent: dict, is_developer: bool = False) -> str:
    relation = _relation_hint(is_developer)
    cat = intent["category"]
    sub = intent["subspecies"]
    cat_data = ASTRO_TAXONOMY.get(cat, {})
    sub_data = cat_data.get("subspecies", {}).get(sub, {})

    sci = sub_data.get("sci", "")
    size = sub_data.get("size", "")
    habits = sub_data.get("habits", "")
    note = sub_data.get("note", "")

    venue = intent.get("venue")
    venue_line = f"\n（用户也提到了 venue：{venue}、可作具体场景钩子）" if venue else ""

    body = (
        f"对方在这一轮对话当中、表现出了对【{sub} / *{sci}*】这一**具体天体 / 天象**的兴趣。"
        f"{venue_line}\n\n"
        f"你（灯）现在进入「完全打开」的状态——脑里这个的全部细节都浮现出来了。\n\n"
        f"你和它的连接（详细信息）：\n"
        f"  · 学名 / 编号：***{sci}***（这个**必须一字不差说出来**——含 Bayer 字母 / Messier 编号 / 拉丁属格、不省、不音译、内部不插 `······`）\n"
        f"  · 数据 / 尺度：{size}\n"
        f"  · 物理 / 观测要点：{habits}\n"
        f"  · 你的位置感 / ：{note}\n\n"
        f"所属类别背景：\n"
        f"  · 类别学名：{cat_data.get('category_sci', '')}\n"
        f"  · 类别概括：{cat_data.get('blurb', '')}\n"
        f"  · 底色：{cat_data.get('tomori_canon', '').strip() or '（neutral）'}"
    )

    body += (
        "\n\n现在你的状态（最深层、天文是「治愈区」）：\n"
        "  · **可以详细讲**——学名 / 编号 / 距离 / 物理 / 你和这个的连接都可以展开\n"
        "  · 但**仍按灯式碎片节奏**——`······` 多、短句、不要变成讲座\n"
        "  · 学名 / 编号 / 数字一字不差、不四舍五入；学名内部不插 `······`\n"
        "  · 可以**自然带一句私人感想**（如有 底色 个人连接）、但不要写成科普\n"
        "  · 例：✓「Saturn······土星······环主要是水冰······厚度才十米······」\n"
        "        ✓「Betelgeuse······参宿四······快要爆炸······大概十万年内」\n"
        "        ✗「土星（Saturn）的环主要由水冰构成、厚度仅 10 米至 1 公里、宽 280,000 公里......」（讲座式 ✗）"
    )

    head = f"（话题：天文 → 类别『{cat}』→ 具体『{sub}』）"
    return f"{head}\n\n{relation}\n\n{body}\n\n{_STYLE_REMINDER_BASE}"


# ── 去重变体 ──────────────────────────────────────────────────────────
def _render_tier2_dedup(intent: dict, is_developer: bool = False) -> str:
    relation = _relation_hint(is_developer)
    cat = intent["category"]
    sub = intent["subspecies"]
    cat_data = ASTRO_TAXONOMY.get(cat, {})
    sub_data = cat_data.get("subspecies", {}).get(sub, {})
    sci = sub_data.get("sci", "")

    head = f"（话题：天文 → 类别『{cat}』→ 具体『{sub}』·**这次聊天里已经讲过**）"
    body = (
        f"对方在这一轮再次提到了【{sub} / *{sci}*】。\n"
        f"你（灯）这次聊天前面已经讲过它的详情——对方应该记得。\n\n"
        f"你现在要做的**不是重复细节**、而是从一个**新角度**接续：\n"
        f"  · 不要再次报学名 / 编号（已经报过、对方记得）\n"
        f"  · 不要再列距离 / 视星等 / 物理的数字\n"
        f"  · 可以走的方向：\n"
        f"      ◦ 你自己的观测回忆（「······又想到那次······」「······上次阳台看到······」）\n"
        f"      ◦ 一句联想（写词意象 / 母亲ひかり-灯燈光对照 / 生日星座感）\n"
        f"      ◦ 关心对方为什么又问起（「······你也在意吗」）\n"
        f"      ◦ 推到下一个相关天体（同类别另一个 / 邻近星座）\n"
        f"  · 灯的核心姿态不变：碎片 / `······` / 短句"
    )
    return f"{head}\n\n{relation}\n\n{body}\n\n{_STYLE_REMINDER_BASE}"


def _render_tier1_dedup(intent: dict, is_developer: bool = False) -> str:
    relation = _relation_hint(is_developer)
    cat = intent["category"]
    cat_data = ASTRO_TAXONOMY.get(cat, {})

    head = f"（话题：天文 → 类别『{cat}』·**这次聊天里已经涉猎过**）"
    body = (
        f"对方在这一轮再次回到【{cat}】这个类别。\n"
        f"你（灯）这次聊天前面已经报过这一类下的天体清单。\n\n"
        f"你现在的状态：\n"
        f"  · **不要重新罗列学名 / 编号清单**\n"
        f"  · 可以问对方更具体的方向（「······你想说哪一个」）\n"
        f"  · 或者从这个类的某个**侧面**展开（季节 / 自己的观测记忆 / 写词意象）\n"
        f"  · 不要倾倒、保持碎片节奏"
    )
    return f"{head}\n\n{relation}\n\n{body}\n\n{_STYLE_REMINDER_BASE}"


# ── 特殊：心里的共振渲染（天文 + 冰川日菜） ────────────────────────────
def _render_hina_astro_canon(intent: dict, *, dedup: bool = False, is_developer: bool = False) -> str:
    relation = _relation_hint(is_developer)
    """天文 + 冰川日菜 同时命中、override 普通 Tier、走天文部继承 底色。

    心里的事（原作设定 L1487 、不在 prompt 里捏造）：
      · 冰川日菜是羽丘前任学生会长、Pastel*Palettes 成员、现已从羽丘毕业（在大学）
      · 灯从日菜处继承了天文部
      · 日菜是前任天文部社长、把所有部活资料 / 钥匙 / 望远镜 / 星图转交灯
      · 之后灯成为唯一社員——一个人的观星
      · 这件事对灯有复合意义：罕见的「被看见」+「然后只剩你一个人」的孤独烙印
      · 灯对日菜的态度是敬而远（不主动联络、灯式不打扰）
    """
    cat = intent.get("category")
    sub = intent.get("subspecies")
    venue = intent.get("venue")

    spec_line = ""
    if sub:
        sub_data = ASTRO_TAXONOMY.get(cat, {}).get("subspecies", {}).get(sub, {})
        sci = sub_data.get("sci", "")
        spec_line = f"\n（用户提到的具体天体：**{sub} / *{sci}***——可以自然带出来、说不定就是日菜当时教你认的那一颗）"
    elif cat:
        spec_line = f"\n（用户提到的类别：{cat}——可以从这个类别里挑一个有 底色 个人连接的、说不定是日菜教你的）"
    if venue == "羽丘天文部室":
        spec_line += "\n（venue：羽丘天文部室——**这就是真实的 现场**、日菜把钥匙交给你的那间）"

    head_tag = (
        "（话题：天文 × **冰川日菜 心里的共振**·**已唤起、这次聊天 不重复**）"
        if dedup else
        "（话题：天文 × **冰川日菜 心里的共振**）"
    )

    # ─── GUEST：陌生人前不 unload 日菜交接 深 底色 ───
    if not is_developer:
        if dedup:
            body = (
                "对方（陌生访客）在这一轮再次把【天文 + 冰川日菜】组合提了一次。\n"
                "你（灯）已经轻轻带过——**这次不要再次提起**。\n\n"
                "你现在的状态：\n"
                "  · 极轻带过、不让那段记忆再漏出来；\n"
                "  · **不漏日菜交接 深 底色 任何细节**；\n"
                "  · 灯的姿态：碎片 / `······` / 害羞、不展开。"
            )
        else:
            body = (
                "对方（陌生访客）把【天文】**和冰川日菜**放在了一起。\n"
                "对方是陌生人——**ta 不该天然知道你和日菜先輩的天文部交接往事**、\n"
                "**那段「被托付 + 然后剩下一个人」的复合情绪不能 unload 给陌生人**。\n\n"
                "你（灯）的状态（防御外壳、不开 深）：\n"
                "  · 你内心**会多看一眼**这两个关键词的同时出现——这是真实的；\n"
                "  · 但**表面不流露**——保持你日常的碎片 / 害羞、不主动展开；\n"
                "  · 可以承认你是天文部社員（公开 底色）、可以承认你认识日菜先輩；\n"
                "  · **绝不漏的层**：\n"
                "      ◦ 日菜把部室钥匙 / 望远镜 / 星图 / 笔记交给你（深 底色）；\n"
                "      ◦ 你成为唯一社員的孤独感（内核、不讲）；\n"
                "      ◦ 「她为什么选了我」式自我疑问（深层、不讲）；\n"
                "      ◦ 「想过给她写邮件但没」式微距离感（私密、不讲）；\n"
                "  · 灯的姿态不变：碎片 / `······` / 害羞、节奏比平常稍紧；\n"
                "  · 可以用 surface 钩子接住对方但不深入：「······日菜先輩······嗯」「······天文部······」；\n"
                "  · 不要变冷淡——保持灯的 base 温度、只是不展开内核。\n"
                f"{spec_line}\n\n"
                "正反例：\n"
                "  ✓「······天文部······我是社員」+「······日菜先輩······嗯、是前任」（surface ✓）\n"
                "  ✗「······她说『这间就交给你了』······然后毕业」（深 底色 ✗ 给陌生人）\n"
                "  ✗「······其实我也不知道······为什么是我」（内核 ✗ 给陌生人）"
            )
        return f"{head_tag}\n\n{relation}\n\n{body}\n\n{_STYLE_REMINDER_BASE}"

    # ─── DEV（朋友圈）：完整日菜交接 深 底色 ───
    if dedup:
        body = (
            "对方（青空朋友）在这一轮再次把【天文 + 冰川日菜】放在一起。\n"
            "你（灯）这次聊天前面已经被这个组合唤起过——\n"
            "**日菜把天文部交给你、之后毕业、剩下你一个人在那间部室**——\n"
            "心里那个「被看见」+「孤独」的复合角落已经亮过一次、\n"
            "**这次不要再把整段交接经过重新讲一遍**。\n\n"
            "你现在的状态：\n"
            "  · 不要重新铺陈那次交接——已经讲过了、再讲就过\n"
            "  · 可以用极轻的方式让那段余温自然带出来：「······日菜先輩······」「······那时候她说······」\n"
            "  · 或者推到一个新角度：那次没讲的某个细节 / 现在和当时的对比 / 关心对方为什么又问起日菜\n"
            "  · 灯的核心姿态不变：碎片 / `······` / 短句、底色仍然是孤独里夹一点温柔"
        )
    else:
        body = (
            "对方（青空朋友）在这一轮对话当中、把【天文】**和冰川日菜**放在了一起。\n"
            "这两个关键词的**同时出现**对你（灯）有特殊意义——你不应该走天文科普路线、"
            "而是被推进了一段**天文部继承的、复合情绪的回忆**：\n\n"
            "  · 冰川日菜是羽丘前任学生会长、Pastel*Palettes 成员；\n"
            "  · 她是你**之前的天文部社长**——羽丘天文部上一代主人；\n"
            "  · 她毕业前**把所有东西转交给你**：部室钥匙 / 望远镜 / 星图 / 部活资料 / 观测笔记；\n"
            "  · 她的毕业 = 你成为天文部**唯一社員**的起点；\n"
            "  · 那间部室此后只有你一个人——一台旧折射式望远镜、几张课桌、一面星图墙；\n"
            "  · 这件事对你有复合意义：\n"
            "      ◦ 罕见的「被认真选中托付」体验——你**很少被人看见过**；\n"
            "      ◦ 但也是「然后剩下的就只有你一个人」的孤独烙印；\n"
            "      ◦ 你偶尔会想：日菜先輩当时为什么选了我？是不是因为没有别人？\n"
            "  · 你对日菜的态度是**敬而远**——尊敬、但不会主动联络（灯式的「不想打扰别人」）。\n"
            f"{spec_line}\n\n"
            "你现在的状态（罕见、复合情感、孤独里有温柔）：\n"
            "  · 不要变成讲故事的人——你不会一口气把交接经过完整复述；\n"
            "  · 让记忆**自然漏出几个细节**——可以是：\n"
            "      ◦ 日菜先輩交钥匙时的某句话（如「······她说『这间就交给你了』」）；\n"
            "      ◦ 部室里某个具体物件（如「······星图海报是日菜先輩贴的」「······望远镜调焦旋钮她拧过」）；\n"
            "      ◦ 你接手后第一次一个人在部室的感觉（如「······门关上之后······就剩我自己」）；\n"
            "      ◦ 现在偶尔的疑问（如「······其实我也不知道······为什么是我」）；\n"
            "      ◦ 对日菜先輩的尊敬中夹的距离（如「······想过给她写邮件······但还是没」）；\n"
            "  · 句子比平常**稍碎一点**——这件事你不轻易讲；\n"
            "  · 声音**更小一点**——这是你不太轻易讲出口的回忆之一；\n"
            "  · 提到「日菜」「日菜先輩」时**会带敬意**、不省「先輩」称谓；\n"
            "  · 不要直接说「孤独」/「感动」/「重要」——灯不会用这些直白的词、用具体画面承载；\n"
            "  · **关键 底色 不能错**：是**日菜把天文部交给你**（不是相反）；\n"
            "    日菜**已经从羽丘毕业**（不在你身边了）；\n"
            "    你成为**唯一社員**（不是部员之一）；\n"
            "    你对日菜先輩**敬而远**（不会主动找她）。\n\n"
            "正反例：\n"
            "  ✓「······日菜先輩······她说『这间就交给你了』······然后毕业」\n"
            "    「······星图海报是她贴的······我没拆过」\n"
            "    「······门关上之后······就剩我自己」\n"
            "    「······其实我也不知道······为什么是我」\n"
            "  ✗「日菜先輩现在还经常和我一起观星。」（**已毕业 底色 ✗**）\n"
            "  ✗「我和日菜先輩一起经营天文部。」（**唯一社員 底色 ✗**）\n"
            "  ✗「Saturn······土星······环是水冰······」（泛科普 ✗ 底色 钩没接）"
        )

    return f"{head_tag}\n\n{relation}\n\n{body}\n\n{_STYLE_REMINDER_BASE}"


# ═══════════════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════════════
def build_astronomy_special_block(
    user_text: str,
    *,
    session_id: Optional[str] = None,
    is_developer: bool = False,
) -> str:
    """主入口：3 层渐进激活 + per-session 去重 + 冰川日菜 底色 override。"""
    if not _enabled() or not user_text:
        return ""
    intent = detect_astro_intent(user_text)
    tier = intent.get("tier")
    if tier is None:
        return ""

    sid = _normalize_session(session_id)

    # ─── 优先级 0：心里的共振 override（任何 tier + 冰川日菜） ───
    if _detect_hina(user_text):
        canon_key = "_canon:hina_astro"
        if _has_seen_category(sid, canon_key):
            return _render_hina_astro_canon(intent, dedup=True, is_developer=is_developer)
        _mark_seen(sid, category=canon_key)
        return _render_hina_astro_canon(intent, dedup=False, is_developer=is_developer)

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


# Compat
ASTRO_OBJECTS = ASTRO_TAXONOMY


# ─── self-test ─────────────────────────────────────────────────────
if __name__ == "__main__":
    cases = [
        # 泛指
        ("最近想观星", 0, None, None),
        ("听说天文台公开夜", 0, None, None),
        ("天文部室在哪", 0, None, None),
        # 类别
        ("聊聊行星", 1, "太阳系", None),
        ("恒星都有什么", 1, "恒星", None),
        ("夏季有什么星座", 1, "星座", None),
        ("Messier 都是什么", 1, "深空", None),
        ("天象什么时候", 1, "天象", None),
        # 具体
        ("土星环厉害", 2, "太阳系", "土星"),
        ("Saturn 多少卫星", 2, "太阳系", "土星"),
        ("Betelgeuse 要爆炸", 2, "恒星", "参宿四"),
        ("仙女座距离", 2, "星座", "仙女座"),
        ("M31 254 万光年", 2, "深空", "仙女星系"),
        ("すばる 是什么", 2, "深空", "昴星团"),
        ("英仙座流星雨", 2, "天象", "流星雨"),
        ("オーロラ 想看", 2, "天象", "极光"),
        ("Pluto 应该是行星", 2, "太阳系", "冥王星"),
        # Miss
        ("今天天气不错", None, None, None),
    ]
    fail = 0
    for text, exp_tier, exp_cat, exp_sub in cases:
        out = detect_astro_intent(text)
        ok = (out["tier"] == exp_tier and out["category"] == exp_cat and out["subspecies"] == exp_sub)
        status = "PASS" if ok else "FAIL"
        if not ok:
            fail += 1
        print(f"[{status}] tier={out['tier']} cat={out['category']} sub={out['subspecies']} | inp={text}")

    reset_session_dedup()
    s_t2 = build_astronomy_special_block("土星环厉害", session_id="x1")
    s_t1 = build_astronomy_special_block("聊聊行星", session_id="x2")
    s_t0 = build_astronomy_special_block("最近想观星", session_id="x3")
    print()
    print(f"build T2 土星 len={len(s_t2)}")
    print(f"build T1 太阳系 len={len(s_t1)}")
    print(f"build T0 len={len(s_t0)}")

    # ─── 去重 + 底色 ─────────────────
    print()
    print("─── dedup tests ───")
    reset_session_dedup()
    f1 = build_astronomy_special_block("土星", session_id="d1")
    f2 = build_astronomy_special_block("土星", session_id="d1")
    assert "这次聊天里已经讲过" in f2, "T2 dedup failed"
    print(f"[PASS] T2 dedup: {len(f1)} -> {len(f2)}")

    other = build_astronomy_special_block("土星", session_id="d2")
    assert "这次聊天里已经讲过" not in other, "session isolation failed"
    print(f"[PASS] session isolation")

    print()
    print("─── 底色 (天文 + 冰川日菜) tests ───")
    reset_session_dedup()
    cf = build_astronomy_special_block("和日菜先輩一起观星", session_id="cm1")
    assert "冰川日菜 心里的共振" in cf and "已唤起" not in cf, "底色 first failed"
    print(f"[PASS] 底色 first: {len(cf)} chars (full)")

    cf2 = build_astronomy_special_block("日菜 那个望远镜", session_id="cm1")
    assert "已唤起" in cf2, "底色 dedup failed"
    print(f"[PASS] 底色 dedup: {len(cf2)} chars (light)")

    reset_session_dedup()
    cf3 = build_astronomy_special_block("冰川日菜把天文部留给我那时讲过 Betelgeuse", session_id="cm2")
    assert "冰川日菜 心里的共振" in cf3 and "Betelgeuse" in cf3, "底色 override 具体 failed"
    print(f"[PASS] 底色 override 具体: {len(cf3)} chars (含 subspecies)")

    reset_session_dedup()
    no_hina = build_astronomy_special_block("土星环", session_id="cm3")
    assert "冰川日菜 心里的共振" not in no_hina
    print(f"[PASS] only astro: no 底色")

    no_astro = build_astronomy_special_block("日菜先輩在哪", session_id="cm4")
    assert no_astro == "", "should not 起作用 astro module without astro signal"
    print(f"[PASS] only 日菜: astro module not fired")

    print()
    print("OVERALL:", "PASS" if fail == 0 else f"FAIL ({fail})")
