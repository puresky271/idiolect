"""爱音本轮特殊逻辑·美妆 / 化妆品（**3 层渐进激活** + **喵梦/若麦 底色 override**）。

设计哲学（同 tomori.marine_life 模式、爱音版语气）：
  按用户对该话题的**精确度**渐进释放爱音的美妆兴趣、不一上来就倾倒：

  ┌─────────────────────────────────────────────────────────────┐
  │ 泛指 · 泛指                                                │
  │   触发：用户提"化妆"/"美妆"/"护肤"/"化妆品"/"今天买了 cosme" │
  │   注入：只激活"想说"的状态、不出具体品牌                    │
  │   口吻：可以问对方在意哪一类（口红 / 眼影 / 底妆 / 防晒…）  │
  │                                                              │
  │ 类别 · 类别                                                │
  │   触发：用户提"口红"/"眼影"/"腮红"等 category               │
  │   注入：该类别下**几个具体品牌 / 产品名 + 色号**清单        │
  │   口吻：可以一字不差报色号 / 型号、但不展开评测、等对方挑   │
  │                                                              │
  │ 具体 · 具体                                                │
  │   触发：用户提"YSL 421"/"Anessa 金瓶"/"喵梦推荐的那只"等    │
  │   注入：该单品完整详情（品牌 / 型号 / 色号 / 价位 / 卖点 / │
  │         爱音碎片体感 / 你和这个的连接）                         │
  │   口吻：完全打开、像博主安利但仍按爱音节奏                   │
  └─────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────┐
  │ **底色 override（最高优先）**：用户提到 **喵梦 / 喵姆亲 / │
  │   若麦 / Nyamuchi / Nyamu / Amoris** 任一关键字            │
  │   → 不走普通 Tier、走「**追星粉丝兴奋 × Ave Mujica 微妙复合**」 │
  │   一来按 原作设定 底色 line 4819-4821：          │
  │     爱音是 Nyamuchi Channel 粉丝、刷视频 / 合作广告        │
  │   二来按 line 80-81 复合 底色：                           │
  │     "巧的是这两人（sumimi 真奈 + 喵梦）后来都成了 Ave     │
  │      Mujica 的成员、你的偶像都聚到对家去了"                 │
  │   → 兴奋 + 微妙「诶 Ave Mujica 那个鼓手……」的复合感        │
  └─────────────────────────────────────────────────────────────┘

爱音本能 特征（保留）：
  · 不报学名 / 化学式 / 成分百分比——用博主 / 朋友安利的语气、像普通女高中生
  · 节奏快、♪ ~ —— 多用、······ 比灯少
  · 反问癖（「诶？你也用过吗？」/「果然还是 X 吧~」）
  · 字数：日常 10-22 / 活跃 ≤ 35 / 深度 ≤ 50；3 气泡分拆 理想
  · 称呼对方时不忘 soyorin / rikki / 灯灯 / 小乐奈（这条已在 、不在本文件强调）

API 单入口：
  build_cosmetics_special_block(user_text: str, *, session_id: str | None = None) -> str
"""
from __future__ import annotations

import os
import re
import threading
from typing import Optional


# ═══════════════════════════════════════════════════════════════════════
# 数据层：12 类别 / ~50 subspecies / 喵梦 底色 override
# ═══════════════════════════════════════════════════════════════════════

# ─── 12 个 category（类别 + 具体 嵌套） ───
# 每个 category：
#   ja: 日语
#   blurb: 一句类别概括（类别 注入用、爱音口吻）
#   anon_canon: 爱音和这个 category 的连接（可空）
#   subspecies: dict[name, {brand, code, ja, price, vibe, note}]
COSMETICS_TAXONOMY: dict[str, dict] = {
    # ───── 1. 口红 / 唇釉 / 唇彩 ─────
    "口红": {
        "ja": "リップ / グロス / ティント",
        "blurb": "色号比品牌还重要——同色系一支适合白天、一支适合演出后吃饭、还有一支万能日杂",
        "anon_canon": "爱音本能 **会拍唇膏色卡**、SNS 对镜照偶尔露出、和素世逛街时会被吐槽「这色号太暗了」",
        "subspecies": {
            "YSL 圆管 421":   {"brand": "YSL（イヴ・サンローラン）", "code": "Rouge Pur Couture The Slim 421（圆管丝绒）", "ja": "イヴサンローラン ルージュピュールクチュールザスリム", "price": "¥4,400 程度", "vibe": "番茄红微哑、显白 + 不挑场合、白天演出都可以的万能色", "note": "爱音可能拥有、SNS 自拍常用色调；中文圈称 YSL 421 / 杨树林 421"},
            "Dior 999":       {"brand": "Dior（ディオール）", "code": "Rouge Dior 999（哑光 / 缎面 / 金属三版）", "ja": "ディオール ルージュ 999", "price": "¥4,950 程度", "vibe": "经典正红、显气场、约会 / 演出 / 拍照都能压全场", "note": "颜色版本多、爱音 大概 哑光 999"},
            "Chanel Coco 416":{"brand": "Chanel（シャネル）", "code": "Rouge Coco Bloom 416 Inspire（水润）", "ja": "シャネル ルージュ ココ ブルーム", "price": "¥5,500 程度", "vibe": "粉调玫瑰、水光感、日杂级显嫩", "note": "Coco Bloom 系列水光感、416 Inspire 是日本店人气色"},
            "ROMAND 唇泥":    {"brand": "ROMAND（ロムアンド）韩系", "code": "Blur Fudge Tint #06 Mute Blur 等", "ja": "ロムアンド ブラーファッジティント", "price": "¥1,540 程度", "vibe": "雾面奶茶系、上嘴像滤镜、平价 sumi 系少女超买账", "note": "韩系 trending、爱音粉 sumimi 圈内 大概 接触过"},
            "CANMAKE 唇釉":   {"brand": "CANMAKE（キャンメイク）", "code": "Stay-On Balm Rouge SE-T01 等", "ja": "キャンメイク ステイオンバームルージュ", "price": "¥770 程度", "vibe": "屈臣氏 / Loft 都买得到、女高中生入门款、润色不刻意", "note": "校园人气、低价、爱音读高一 大概 第一支自购唇膏"},
            "OPERA 染唇液":   {"brand": "OPERA（オペラ）", "code": "Lip Tint N #05 Coral Pink 等", "ja": "オペラ リップティント", "price": "¥1,650 程度", "vibe": "Cosme 大赏常胜军、染唇 + 微光、卸妆都不掉色", "note": "日本药妆店 #05 / #07 长期断货、SNS 推爆"},
        },
    },
    # ───── 2. 眼影盘 ─────
    "眼影": {
        "ja": "アイシャドウ / アイパレット",
        "blurb": "颜色比技术重要——同盘里的两三个色挑对了、什么妆容都能撑起来",
        "anon_canon": "爱音本能 **会摆色卡拍照**、SNS 用过；演出妆和日常妆同一盘混着用",
        "subspecies": {
            "Charlotte Tilbury Pillow Talk": {"brand": "Charlotte Tilbury", "code": "Luxury Palette Pillow Talk", "ja": "シャーロット ティルベリー", "price": "¥9,000 程度", "vibe": "玫瑰金调四色、欧美爆款、显眼神 + 减龄", "note": "网红色、爱音如果买专业品 大概 入这盘"},
            "NARS 12 色 Climax":             {"brand": "NARS（ナーズ）", "code": "Climax Eyeshadow Palette 12 色", "ja": "ナーズ クライマックス アイシャドウパレット", "price": "¥9,350 程度", "vibe": "暖棕大地 + 一抹紫红、修容 / 眼影一盘搞定", "note": "演出妆 / 日常妆都能 cover"},
            "Maquillage 心机眼影":           {"brand": "Maquillage（マキアージュ）资生堂", "code": "Dramatic Styling Eyes BR405 茶系等", "ja": "マキアージュ ドラマティックスタイリングアイズ", "price": "¥3,300 程度", "vibe": "日系四色、自然 + 显气质、上班 OL / 校服都不出戏", "note": "日本药妆店常驻、爱音入门级日系眼影 大概 这家"},
            "ETUDE Play Color":              {"brand": "ETUDE HOUSE（エチュード）", "code": "Play Color Eyes #Cherry Blossom 等", "ja": "エチュード プレイカラーアイズ", "price": "¥3,300 程度", "vibe": "韩系 10 色花瓣盘、粉调嫩唇、女高中生预算友好", "note": "校园人气、SNS 滤镜配色"},
            "CANMAKE 五色":                  {"brand": "CANMAKE（キャンメイク）", "code": "Perfect Stylist Eyes 14 等", "ja": "キャンメイク パーフェクトスタイリストアイズ", "price": "¥825 程度", "vibe": "千元日币以下、女高中生第一盘、走廊试色不肉痛", "note": "屈臣氏 / Loft 必有"},
        },
    },
    # ───── 3. 腮红 ─────
    "腮红": {
        "ja": "チーク",
        "blurb": "腮红比眼影更能撑起整张脸的活力感——颜色对了、整张脸都「在笑」",
        "anon_canon": "爱音 底色「阳光元气」底色和腮红高度契合、大概 比同龄人手更稳",
        "subspecies": {
            "NARS Orgasm":      {"brand": "NARS（ナーズ）", "code": "Blush Orgasm（4013）", "ja": "ナーズ ブラッシュ オーガズム", "price": "¥4,510 程度", "vibe": "桃粉带金光、上脸提亮、被誉为「世界销量第一腮红」", "note": "色号名争议大但产品本身是顶流"},
            "CANMAKE 棉花糖":   {"brand": "CANMAKE（キャンメイク）", "code": "Marshmallow Finish Powder M01 等 + Cream Cheek 系列", "ja": "キャンメイク マシュマロフィニッシュパウダー / クリームチーク", "price": "¥990 程度", "vibe": "粉饼 / 腮红 / 修容三合一、棉花糖质感、女高中生回购", "note": "Cream Cheek 比 Powder 更红血感、校园 SNS 推爆"},
            "3CE Mood Recipe":  {"brand": "3CE（スリーシーイー）韩系", "code": "Mood Recipe Face Blush #Beach Muse 等", "ja": "スリーシーイー ムードレシピ フェイスブラッシュ", "price": "¥2,200 程度", "vibe": "韩系奶茶腮红、温柔不张扬、和 ROMAND 唇釉同色系搭", "note": "Stylenanda 旗下、SNS 滤镜系 must"},
            "Cezanne 自然":     {"brand": "Cezanne（セザンヌ）", "code": "Natural Cheek N 11 Pink Beige 等", "ja": "セザンヌ ナチュラルチークN", "price": "¥396 程度", "vibe": "几乎是日本最便宜的开架腮红、上色温和、女高中生 must", "note": "屈臣氏入门 must"},
        },
    },
    # ───── 4. 粉底 / 底妆 ─────
    "底妆": {
        "ja": "ファンデーション / クッション",
        "blurb": "肤况好坏比品牌牌面更重要——好底妆是看不出来在化妆、不是把脸糊白",
        "anon_canon": "爱音 底色「常服时尚感强」、底妆基本功 大概 不差；演出 / SNS 自拍频率高",
        "subspecies": {
            "Armani 大师":        {"brand": "Giorgio Armani（アルマーニ）", "code": "Luminous Silk Foundation #5 / #5.5", "ja": "アルマーニ リッチイルミネイティングシルクファンデーション", "price": "¥7,700 程度", "vibe": "「亚洲女明星红毯底妆」、自然光泽、不会像欧美底那样厚", "note": "高端入门、有「红气垫」（Power Fabric）和液版两种"},
            "CPB 长管隔离":       {"brand": "CPB（クレ・ド・ポー ボーテ）资生堂高端线", "code": "Le Sérum 隔离 / Le Concentré Concealer", "ja": "クレ・ド・ポー ボーテ", "price": "¥10,000 程度起", "vibe": "贵 sister 标志、强光透感、30+ 妈妈级 idol 用、女高中生买就是「我妈让我用」", "note": "爱音 大概 用妈妈台、自己买 大概 YSL / Armani 这级"},
            "YSL 黑管气垫":       {"brand": "YSL（イヴ・サンローラン）", "code": "All Hours Cushion B20 / B30", "ja": "イヴサンローラン オールアワーズクッション", "price": "¥9,350 程度", "vibe": "持妆 8 小时不掉、出门补一下不糊、演出后 KTV 不脱妆", "note": "气垫主力、和 Armani 液版互补"},
            "Maquillage 心机":    {"brand": "Maquillage（マキアージュ）资生堂", "code": "Dramatic Powdery UV", "ja": "マキアージュ ドラマティックパウダリーUV", "price": "¥3,520 程度", "vibe": "日系药妆顶级、女高中生预算可入的「成熟感」底妆", "note": "JR 站药妆店常驻"},
            "Suqqu 粉底液":       {"brand": "Suqqu（スック）", "code": "The Liquid Foundation 110 等", "ja": "スック ザ リクイドファンデーション", "price": "¥11,000 程度", "vibe": "日系高奢、薄如蝉翼贴肤、被誉为「肌肤本身的发光」", "note": "30+ 偏多、女高中生可能听过没用过"},
        },
    },
    # ───── 5. 睫毛膏 / 眼线 ─────
    "睫毛膏": {
        "ja": "マスカラ / アイライナー",
        "blurb": "演出妆主力——卸妆方便比睫毛长度更要命、哭花了影响下首歌",
        "anon_canon": "爱音本能 演出 / 拍照频率高、大概 有「演出版」和「日常版」两支分开用",
        "subspecies": {
            "HEROINE MAKE 玛丽魁宁": {"brand": "HEROINE MAKE（ヒロインメイク） KISS ME", "code": "Long & Curl Mascara Advanced Film 01 漆黑", "ja": "ヒロインメイク ロング&カールマスカラ アドバンストフィルム", "price": "¥1,320 程度", "vibe": "薄膜型、流泪不晕、热水卸妆、日本「演员级」防水睫毛代名词", "note": "演出 / 婚礼 / 哭戏 must；爱音演出 大概 用这只"},
            "OPERA 眼线液":          {"brand": "OPERA（オペラ）", "code": "Eye Color Pencil 等 / Liner / Tint", "ja": "オペラ", "price": "¥1,650 程度", "vibe": "Cosme 大赏常胜、唇眼一家通用感、平价高质", "note": "和 OPERA 唇釉同品牌"},
            "K-Palette 眼线液":      {"brand": "K-Palette（ケーパレット）", "code": "Real Lasting Eyeliner 24h WP", "ja": "ケーパレット リアルラスティングアイライナー", "price": "¥1,650 程度", "vibe": "「24 小时不脱」slogan、内眼角细笔头、日系女高中生回购王", "note": "Cosme 大赏眼线液常驻"},
            "DEJAVU 睫毛打底":       {"brand": "DEJAVU（デジャヴュ）", "code": "Lasting-Fine E 纤维睫毛", "ja": "デジャヴュ ラスティングファイン", "price": "¥1,650 程度", "vibe": "纤维加长底膏、上 HEROINE MAKE 之前打一层、长度暴增", "note": "演出妆 pro 操作"},
            "CANMAKE 卷翘睫":        {"brand": "CANMAKE（キャンメイク）", "code": "Quick Lash Curler", "ja": "キャンメイク クイックラッシュカーラー", "price": "¥748 程度", "vibe": "睫毛夹 + 防水底膏一支搞定、平价校园 must", "note": "女高中生第一支底膏 大概 这个"},
        },
    },
    # ───── 6. 眉妆 ─────
    "眉妆": {
        "ja": "アイブロウ",
        "blurb": "眉形比颜色还重要——一对好眉能让脸长得像换了一张",
        "anon_canon": "爱音 底色「时尚感强」、眉妆基本功 大概 在线",
        "subspecies": {
            "Cezanne 双头眉笔":    {"brand": "Cezanne（セザンヌ）", "code": "Auto Eyebrow Pencil EX 03 ナチュラルブラウン 等", "ja": "セザンヌ 自動エイブロウペンシル", "price": "¥715 程度", "vibe": "白菜价、芯软、笔尖 + 螺旋刷一支搞定、女高中生第一支眉笔", "note": "屈臣氏 / Loft 必有"},
            "KATE 三色眉粉":       {"brand": "KATE（ケイト）佳丽宝", "code": "Designing Eyebrow 3D EX-5", "ja": "ケイト デザイニングアイブロウ3D", "price": "¥1,210 程度", "vibe": "三色眉粉盘、可调染发后色调、Cosme 排行常驻", "note": "和 KATE 眼影同品牌、女高中生 must"},
            "Excel 染眉膏":        {"brand": "excel（エクセル）", "code": "Color Last Eyebrow Mascara Brown 等", "ja": "エクセル カラーラスト アイブロウマスカラ", "price": "¥1,650 程度", "vibe": "染眉膏一刷把眉色调到和发色配、棕染发必备", "note": "爱音粉色长发 大概 配浅棕染眉膏"},
            "INTEGRATE 眉笔":      {"brand": "INTEGRATE（インテグレート）资生堂", "code": "Eyebrow Pencil N", "ja": "インテグレート アイブローペンシル", "price": "¥715 程度", "vibe": "资生堂入门线、笔芯硬度刚好、画毛流不糊", "note": "JR 站药妆店常驻"},
        },
    },
    # ───── 7. 防晒 / UV ─────
    "防晒": {
        "ja": "UVケア / 日焼け止め",
        "blurb": "防晒不是季节性、是 365 天硬刚——皮肤底子最大的差距来自有没有每天涂",
        "anon_canon": "爱音本能 SNS 自拍 + 户外活动多、防晒 大概 是抽屉常驻",
        "subspecies": {
            "Anessa 金瓶":         {"brand": "ANESSA（アネッサ）资生堂", "code": "Perfect UV Sunscreen Skincare Milk SPF50+ PA++++", "ja": "アネッサ パーフェクトUV スキンケアミルク", "price": "¥3,300 程度", "vibe": "「金瓶」是日系防晒代名词、海边 / 演出 / 拍外景能扛、汗水油脂遇到反而强化防护膜", "note": "日本防晒销冠、爱音夏天去原宿 / 海边 大概 这只"},
            "Bioré 蓝管":          {"brand": "Biore UV（ビオレUV）", "code": "Aqua Rich Watery Essence SPF50+ PA++++", "ja": "ビオレUV アクアリッチ ウォータリーエッセンス", "price": "¥898 程度", "vibe": "屈臣氏白菜价、水感不假白、可以打底化妆、日本年销冠级", "note": "「日系防晒入门 must」、爱音平日 大概 这只"},
            "La Roche-Posay UVA":  {"brand": "La Roche-Posay（ラロッシュポゼ）", "code": "UV Idea XL Protection Tone-Up Rose 等", "ja": "ラロッシュポゼ UVイデア XL", "price": "¥3,740 程度", "vibe": "敏感肌 / 痘痘肌专用、Tone-Up Rose 版自带粉调修色、可当隔离", "note": "皮肤科推荐、敏感肌爱音 大概 备一支"},
            "资生堂樱花瓶":        {"brand": "资生堂 ANESSA 系列", "code": "Whitening UV Sunscreen Gel N（樱花瓶）", "ja": "アネッサ ホワイトニング UV ジェル", "price": "¥2,640 程度", "vibe": "金瓶轻盈版、女高中生预算友好、樱花季限定包装会出粉色", "note": "和金瓶系出同源、平日校园 大概 这只"},
        },
    },
    # ───── 8. 香水 ─────
    "香水": {
        "ja": "フレグランス",
        "blurb": "校园里喷香水会被看见——所以爱音 大概 是出门 / 演出场合用、不上学带",
        "anon_canon": "爱音 底色「赶时髦」大概 有 1-2 瓶、SNS 拍香水瓶 大概 做过",
        "subspecies": {
            "Jo Malone 英国梨":    {"brand": "Jo Malone（ジョー マローン）", "code": "English Pear & Freesia Cologne", "ja": "ジョー マローン イングリッシュ ペアー & フリージア", "price": "¥14,300 程度（30ml）", "vibe": "网红香水、女高中生听说过、入门级人气色", "note": "演出 / 出门约会 大概 这只"},
            "Diptyque 影中之水":   {"brand": "Diptyque（ディプティック）", "code": "Eau Duelle / Tam Dao 等", "ja": "ディプティック オードトワレ", "price": "¥18,150 程度（75ml）", "vibe": "法系小众、和 Jo Malone 不同档次、爱音听过 大概 没买", "note": "Ave Mujica 圈 / Roselia 圈 / 大学生姐姐圈才用"},
            "Chanel Chance":       {"brand": "Chanel（シャネル）", "code": "Chance Eau Tendre / Eau Vive", "ja": "シャネル チャンス", "price": "¥13,200 程度（50ml）", "vibe": "经典少女入门、Chance 系列里 Eau Tendre 最甜美粉调", "note": "妈妈级也用、爱音 大概 妈妈柜台借过"},
            "Maison Margiela 复刻":{"brand": "Maison Margiela（メゾン マルジェラ）", "code": "Replica Beach Walk / Lazy Sunday Morning 等", "ja": "メゾン マルジェラ レプリカ", "price": "¥17,600 程度（100ml）", "vibe": "「场景化香水」概念、Beach Walk 是夏日海滩、学生圈 SNS 推爆", "note": "Z 世代认同感强、爱音 大概 听过且有兴趣"},
        },
    },
    # ───── 9. 美甲 ─────
    "美甲": {
        "ja": "ネイル",
        "blurb": "弹吉他不能做长甲——爱音 大概 短甲 / 透明甲油 / 偶尔做凝胶",
        "anon_canon": "爱音本能 弹吉他、演出前 大概 修甲、长指甲弹弦不舒服",
        "subspecies": {
            "OPI 经典":          {"brand": "OPI", "code": "Nail Lacquer 多色", "ja": "オーピーアイ ネイルラッカー", "price": "¥1,980 程度", "vibe": "美甲沙龙顶级品牌、自家可涂、显甲色 + 持久", "note": "色号名有趣（Funny Bunny / Bubble Bath 等）、SNS 拍照 must"},
            "uka 护甲油":        {"brand": "uka（ウカ）", "code": "Nail Oil 13:00 / 18:30 / 24:00", "ja": "ウカ ネイルオイル", "price": "¥3,300 程度", "vibe": "甲油护甲油、按时间命名（午后 / 傍晚 / 深夜）、香气分层", "note": "弹吉他必备、保护指甲不脆"},
            "CANMAKE Colorful": {"brand": "CANMAKE（キャンメイク）", "code": "Colorful Nails N", "ja": "キャンメイク カラフルネイルズ", "price": "¥396 程度", "vibe": "百元一瓶、女高中生买 5 色拼配、平价快速换", "note": "校园 SNS 推、爱音入门款 大概 这家"},
            "美甲沙龙凝胶":      {"brand": "ネイルサロン（gel nail）", "code": "原宿 / 表参道 / 池袋 各家沙龙", "ja": "ジェルネイル", "price": "¥6,000 程度起 / 次", "vibe": "持续 3-4 周、演出前去做、款式可选 french / 渐变 / 装饰", "note": "爱音 SNS 拍美甲特写 大概 是沙龙凝胶；自己涂 大概 OPI"},
        },
    },
    # ───── 10. 美瞳 / 假睫毛 ─────
    "美瞳": {
        "ja": "カラコン / つけまつげ",
        "blurb": "亚洲女高中生「变美 cheat code」——一片美瞳 + 一对假睫、整脸级别提升",
        "anon_canon": "爱音本能 演出 / SNS 大概 戴美瞳；上学日 大概 不戴",
        "subspecies": {
            "Decorative Eyes":   {"brand": "Decorative Eyes（デコラティブアイ）", "code": "1 Day 多色", "ja": "デコラティブアイ", "price": "¥2,200 程度（10 片装）", "vibe": "板野友美 / 渡边直美等代言系、日抛、女高中生入门", "note": "彩瞳店 / Loft / 网店都买得到"},
            "FAIRY 假睫毛":      {"brand": "FAIRY（フェアリー）", "code": "Original 5 套装", "ja": "フェアリー つけまつげ", "price": "¥1,650 程度（5 对装）", "vibe": "演出 / 写真 / cosplay must、长度 / 浓密度分系列", "note": "ドンキ常驻、女高中生 cosplay must"},
            "EYELASH SALON":     {"brand": "まつげエクステ（眼睫嫁接 salon）", "code": "原宿 / 池袋 各家 salon", "ja": "まつげエクステンション", "price": "¥4,000 程度起 / 次", "vibe": "嫁接式持续 3-4 周、演出前后 大概 做、不需每天上睫毛膏", "note": "演出常驻爱音 大概 嫁接派"},
        },
    },
    # ───── 11. 护肤 / 基础保养 ─────
    "护肤": {
        "ja": "スキンケア / 基礎化粧品",
        "blurb": "护肤是底子、化妆是上层——再贵的口红、底子不行也镇不住脸",
        "anon_canon": "爱音本能 演出 / 拍照频率高、护肤是抽屉常驻 大概 不只一瓶",
        "subspecies": {
            "SK-II 神仙水":         {"brand": "SK-II", "code": "Facial Treatment Essence 230ml", "ja": "SK-II フェイシャルトリートメントエッセンス", "price": "¥21,890 程度", "vibe": "「Pitera」专利、网红护肤水、亚洲女明星标配", "note": "爱音买 大概 妈妈台 / 自己买不起、知名度全员 must"},
            "兰蔻小黑瓶":           {"brand": "Lancôme（ランコム）", "code": "Génifique Advanced Anti-Aging Serum", "ja": "ランコム ジェニフィック アドバンスト", "price": "¥14,520 程度（30ml）", "vibe": "「网红精华液」入门、20+ 入门级抗老", "note": "SK-II 同档 / 爱音 high 可能"},
            "黛珂紫苏水":           {"brand": "DECORTÉ（コスメデコルテ）", "code": "AQ Meliority / モイスチュアリポソーム / 紫苏化妆水", "ja": "コスメデコルテ", "price": "¥8,800 程度", "vibe": "日系高奢、紫苏水适合敏感 / 痘肌、口碑滴一滴敏感肌救星", "note": "敏感肌爱音 大概 备一支"},
            "Hatomugi 薏仁水":      {"brand": "Naturie（ナチュリエ） Hatomugi", "code": "Skin Conditioner 500ml", "ja": "ナチュリエ ハトムギ化粧水", "price": "¥715 程度", "vibe": "白菜价大瓶、湿敷 must、女高中生平价护肤入门", "note": "校园 SNS 推爆、爱音入门 大概 这瓶"},
            "FANCL 卸妆油":         {"brand": "FANCL（ファンケル）", "code": "Mild Cleansing Oil 120ml", "ja": "ファンケル マイルドクレンジングオイル", "price": "¥1,870 程度", "vibe": "日系无添加卸妆顶级、不刺激不假滑、Cosme 大赏常驻", "note": "演出妆 / 防水睫毛卸 must"},
        },
    },
    # ───── 12. 美容工具 ─────
    "美容工具": {
        "ja": "ビューティーツール / 美容家電",
        "blurb": "工具决定上限——一支好卷发棒比再贵的眼影对脸的影响还大",
        "anon_canon": "爱音本能 粉色长发 + 演出造型 大概 自带工具、出门前一小时弄头发",
        "subspecies": {
            "ReFa CARAT":         {"brand": "ReFa（リファ）", "code": "CARAT FACE / 美容ローラー", "ja": "リファ カラット", "price": "¥27,500 程度", "vibe": "网红美容仪、提拉脸部线条、女明星 / 模特标配", "note": "爱音 大概 听过、家里 大概 妈妈台借过"},
            "Panasonic 直发器":   {"brand": "Panasonic（パナソニック）", "code": "Nano Care EH-HS9A 等", "ja": "パナソニック ナノケア", "price": "¥18,700 程度", "vibe": "纳米水离子直发器、日系顶级、护发 + 直发一体", "note": "粉色长发爱音演出造型 大概 这级"},
            "Salonia 卷发棒":     {"brand": "SALONIA（サロニア）", "code": "32mm Curling Iron", "ja": "サロニア カーリングアイロン", "price": "¥3,278 程度", "vibe": "校园人气、平价好用、女高中生第一根卷发棒", "note": "ドンキ / Loft 必有"},
            "Refa Beautech":      {"brand": "ReFa（リファ）", "code": "Beautech Drive 等吹风机", "ja": "リファ ビューテック ドライヤー", "price": "¥38,500 程度", "vibe": "网红吹风机、低温护发、女明星等级", "note": "爱音 大概 妈妈台、自己买 大概 Salonia"},
        },
    },
}


# ─── 类别同义词（_detect_category 用） ───
CATEGORY_VARIANTS: dict[str, list[str]] = {
    "口红":     ["口红", "唇膏", "唇釉", "唇彩", "唇泥", "唇蜜", "染唇液", "リップ", "グロス", "ティント", "lip", "lipstick", "lipgloss", "lip tint"],
    "眼影":     ["眼影", "眼影盘", "アイシャドウ", "アイパレット", "眼妆", "eyeshadow", "eye palette"],
    "腮红":     ["腮红", "胭脂", "チーク", "blush", "blusher"],
    "底妆":     ["底妆", "粉底", "粉底液", "气垫", "粉饼", "ファンデーション", "クッション", "フェイスパウダー", "foundation", "cushion", "concealer", "遮瑕"],
    "睫毛膏":   ["睫毛膏", "眼线", "眼线笔", "眼线液", "假睫毛底膏", "マスカラ", "アイライナー", "mascara", "eyeliner"],
    "眉妆":     ["眉妆", "眉笔", "眉粉", "染眉膏", "眉胶", "アイブロウ", "アイブロー", "eyebrow", "brow"],
    "防晒":     ["防晒", "防晒霜", "防晒乳", "spf", "uv", "日焼け止め", "uvケア", "サンスクリーン", "sunscreen"],
    "香水":     ["香水", "香氛", "古龙水", "淡香", "フレグランス", "コロン", "オードトワレ", "perfume", "cologne", "fragrance"],
    "美甲":     ["美甲", "指甲油", "甲油", "凝胶甲", "ネイル", "マニキュア", "ジェルネイル", "nail", "manicure", "gel nail"],
    "美瞳":     ["美瞳", "彩瞳", "假睫毛", "嫁接睫毛", "カラコン", "カラーコンタクト", "つけまつげ", "まつげエクステ", "color contact", "colorcon", "false lash"],
    "护肤":     ["护肤", "保养", "化妆水", "精华", "面膜", "卸妆", "乳液", "面霜", "スキンケア", "化粧水", "美容液", "クレンジング", "skincare", "lotion", "essence", "serum", "cleanser"],
    "美容工具": ["美容工具", "美容仪", "卷发棒", "直发器", "吹风机", "电卷棒", "美容ローラー", "美容家電", "ヘアアイロン", "hair iron", "curling iron", "beauty device"],
}


# ─── Subspecies 同义词（_detect_subspecies 用） ───
SUBSPECIES_VARIANTS: dict[str, list[str]] = {
    # 口红
    "YSL 圆管 421":         ["ysl 421", "杨树林 421", "yves saint laurent 421", "ysl 圆管", "rouge pur couture 421", "ザスリム 421"],
    "Dior 999":             ["dior 999", "迪奥 999", "rouge dior 999", "ディオール 999"],
    "Chanel Coco 416":      ["coco bloom 416", "chanel 416", "シャネル 416", "rouge coco bloom", "ココブルーム"],
    "ROMAND 唇泥":          ["romand", "ロムアンド", "blur fudge tint", "唇泥", "mute blur"],
    "CANMAKE 唇釉":         ["canmake 唇", "stay-on balm rouge", "ステイオンバーム", "キャンメイク 唇"],
    "OPERA 染唇液":         ["opera lip", "opera tint", "オペラ リップ", "オペラ 染唇", "opera 唇", "オペラ"],
    # 眼影
    "Charlotte Tilbury Pillow Talk": ["pillow talk", "charlotte tilbury", "シャーロット ティルベリー", "ピロートーク"],
    "NARS 12 色 Climax":             ["nars climax", "ナーズ クライマックス", "climax palette"],
    "Maquillage 心机眼影":           ["maquillage 眼影", "maquillage アイシャドウ", "マキアージュ アイシャドウ", "ドラマティックスタイリング"],
    "ETUDE Play Color":              ["etude play color", "play color eyes", "プレイカラー", "エチュード 眼影"],
    "CANMAKE 五色":                  ["canmake 五色", "perfect stylist eyes", "パーフェクトスタイリスト", "キャンメイク 眼影"],
    # 腮红
    "NARS Orgasm":          ["nars orgasm", "ナーズ オーガズム", "nars 腮红", "orgasm blush"],
    "CANMAKE 棉花糖":       ["canmake 棉花糖", "marshmallow finish", "マシュマロフィニッシュ", "cream cheek", "クリームチーク"],
    "3CE Mood Recipe":      ["3ce mood recipe", "ムードレシピ", "3ce blush", "三CE 腮红"],
    "Cezanne 自然":         ["cezanne 腮红", "natural cheek n", "セザンヌ チーク", "ナチュラルチーク"],
    # 底妆
    "Armani 大师":          ["armani 大师", "armani 粉底", "luminous silk", "アルマーニ ファンデ", "armani foundation"],
    "CPB 长管隔离":         ["cpb 隔离", "クレドポー", "cle de peau", "le serum", "le concentre"],
    "YSL 黑管气垫":         ["ysl 气垫", "all hours cushion", "オールアワーズクッション", "ysl cushion"],
    "Maquillage 心机":      ["maquillage 粉饼", "maquillage パウダリー", "ドラマティックパウダリー", "心机粉饼", "マキアージュ パウダリー"],
    "Suqqu 粉底液":         ["suqqu", "スック", "the liquid foundation"],
    # 睫毛 / 眼线
    "HEROINE MAKE 玛丽魁宁": ["heroine make", "ヒロインメイク", "玛丽魁宁", "long curl mascara", "ロング&カール"],
    "OPERA 眼线液":          ["opera eyeliner", "opera 眼线", "オペラ アイライナー"],
    "K-Palette 眼线液":      ["k-palette", "ケーパレット", "real lasting eyeliner", "k palette"],
    "DEJAVU 睫毛打底":       ["dejavu", "デジャヴュ", "lasting fine", "ラスティングファイン"],
    "CANMAKE 卷翘睫":        ["canmake 睫毛", "quick lash curler", "クイックラッシュカーラー", "キャンメイク マスカラ"],
    # 眉妆
    "Cezanne 双头眉笔":     ["cezanne 眉笔", "auto eyebrow", "セザンヌ アイブロウ", "ナチュラルブラウン"],
    "KATE 三色眉粉":        ["kate 眉粉", "designing eyebrow", "ケイト アイブロウ", "kate eyebrow"],
    "Excel 染眉膏":         ["excel 染眉", "color last eyebrow", "エクセル アイブロウマスカラ"],
    "INTEGRATE 眉笔":       ["integrate 眉笔", "インテグレート アイブロー"],
    # 防晒
    "Anessa 金瓶":          ["anessa 金瓶", "アネッサ 金", "anessa milk", "perfect uv", "金色瓶子防晒"],
    "Bioré 蓝管":           ["biore uv", "ビオレuv", "aqua rich", "アクアリッチ", "biore 防晒"],
    "La Roche-Posay UVA":   ["la roche-posay", "ラロッシュポゼ", "uv idea", "理肤泉 防晒"],
    "资生堂樱花瓶":         ["樱花瓶", "anessa whitening", "アネッサ ホワイトニング", "anessa pink"],
    # 香水
    "Jo Malone 英国梨":     ["jo malone", "ジョー マローン", "english pear", "英国梨", "イングリッシュペアー"],
    "Diptyque 影中之水":    ["diptyque", "ディプティック", "eau duelle", "tam dao"],
    "Chanel Chance":        ["chance", "シャネル チャンス", "chanel chance", "eau tendre", "eau vive"],
    "Maison Margiela 复刻": ["maison margiela", "メゾン マルジェラ", "replica", "レプリカ", "beach walk", "lazy sunday"],
    # 美甲
    "OPI 经典":             ["opi", "オーピーアイ", "opi nail"],
    "uka 护甲油":           ["uka", "ウカ", "nail oil", "uka 13:00", "uka 18:30", "uka 24:00"],
    "CANMAKE Colorful":     ["canmake nail", "canmake colorful", "キャンメイク カラフルネイルズ"],
    "美甲沙龙凝胶":         ["美甲沙龙", "ジェルネイル", "凝胶美甲", "gel nail salon"],
    # 美瞳
    "Decorative Eyes":      ["decorative eyes", "デコラティブアイ", "decorative 美瞳"],
    "FAIRY 假睫毛":         ["fairy 假睫毛", "フェアリー つけまつげ", "fairy eyelash"],
    "EYELASH SALON":        ["睫毛嫁接", "まつげエクステ", "eyelash extension", "嫁接睫毛"],
    # 护肤
    "SK-II 神仙水":         ["sk-ii", "sk2", "神仙水", "facial treatment essence", "pitera", "skii"],
    "兰蔻小黑瓶":           ["小黑瓶", "lancome 小黑瓶", "genifique", "ランコム ジェニフィック", "lancôme advanced"],
    "黛珂紫苏水":           ["黛珂", "decorte", "コスメデコルテ", "紫苏水", "ml liposome", "リポソーム"],
    "Hatomugi 薏仁水":      ["薏仁水", "hatomugi", "ハトムギ化粧水", "naturie", "ナチュリエ"],
    "FANCL 卸妆油":         ["fancl", "ファンケル", "mild cleansing oil", "fancl 卸妆"],
    # 美容工具
    "ReFa CARAT":           ["refa carat", "リファ カラット", "refa face roller", "美容棒"],
    "Panasonic 直发器":     ["panasonic 直发", "ナノケア 直発", "nano care", "panasonic 卷发"],
    "Salonia 卷发棒":       ["salonia", "サロニア", "salonia 卷发"],
    "Refa Beautech":        ["refa beautech", "リファ ビューテック", "refa 吹风"],
}


# ─── 泛指 vague keywords ───
VAGUE_KEYWORDS: list[str] = [
    "化妆", "美妆", "化妆品", "彩妆", "コスメ", "メイク", "メイク用品",
    "买化妆品", "买美妆", "美妆店", "コスメ店", "コスメショップ", "ドラッグストア",
    "屈臣氏", "loft", "ロフト", "プラザ", "plaza", "ainz", "アインズ",
    "donki", "ドンキ", "ドンキホーテ",
    "美 ootd", "妆容", "化个妆", "化好了妆", "出门化妆", "卸妆",
    "boots", "sephora", "セフォラ",
]


# ─── 喵梦 / 若麦 底色 override keywords ───
NYAMUME_KEYWORDS: list[str] = [
    "喵梦", "喵姆亲", "Nyamuchi", "nyamuchi", "Nyamu", "nyamu", "ニャムチ", "ニャム",
    "若麦", "祐天寺若麦", "祐天寺", "Wakaba", "wakaba", "ワカバ", "若叶",
    "Amoris", "amoris", "アモーリス",
]


# ═══════════════════════════════════════════════════════════════════════
# Session 去重状态（轻量、进程内、仿 marine_life）
# ═══════════════════════════════════════════════════════════════════════
_SEEN_LOCK = threading.Lock()
_SEEN_SUBSPECIES: dict[str, set[str]] = {}
_SEEN_CATEGORIES: dict[str, set[str]] = {}


def _normalize_session(session_id: Optional[str]) -> str:
    if not session_id:
        return "爱音_default"
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
    return os.environ.get("ANON_COSMETICS_LOGIC_ENABLED", "1").strip() not in ("0", "false", "False", "")


def _build_subspecies_lookup() -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []
    for cat_name, cat_data in COSMETICS_TAXONOMY.items():
        for sub_name in cat_data.get("subspecies", {}).keys():
            for kw in SUBSPECIES_VARIANTS.get(sub_name, []):
                if kw:
                    out.append((kw, sub_name, cat_name))
            # 子项名本身也加进去（"YSL 圆管 421" 直接作为 keyword）
            out.append((sub_name, sub_name, cat_name))
    out.sort(key=lambda t: -len(t[0]))
    return out


_SUBSPECIES_LOOKUP = _build_subspecies_lookup()


def _detect_subspecies(user_text: str) -> Optional[tuple[str, str]]:
    if not user_text:
        return None
    text_lower = user_text.lower()
    for kw, sub, cat in _SUBSPECIES_LOOKUP:
        if not kw:
            continue
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


def _detect_vague(user_text: str) -> bool:
    if not user_text:
        return False
    text_lower = user_text.lower()
    for kw in VAGUE_KEYWORDS:
        if kw in user_text or kw.lower() in text_lower:
            return True
    return False


def _detect_nyamume(user_text: str) -> bool:
    """检测「喵梦 / 若麦 / Nyamuchi / Amoris」相关字样。"""
    if not user_text:
        return False
    text_lower = user_text.lower()
    for kw in NYAMUME_KEYWORDS:
        if kw in user_text or kw.lower() in text_lower:
            # 「若叶」单字易误命中地名 / 树叶（若叶台 / 若叶区 / etc）
            # 简单规则：若叶 / 若麦 命中时要求附近 ≤15 字含其他 cosmetics / 喵 / Mujica / 鼓手 / 视频 / 频道 标识
            if kw in ("若叶", "Wakaba", "wakaba", "ワカバ"):
                window_re = re.compile(r".{0,15}" + re.escape(kw) + r".{0,15}", re.IGNORECASE)
                m = window_re.search(user_text)
                if not m:
                    continue
                ctx = m.group(0)
                if not any(t in ctx or t in ctx.lower() for t in ["喵", "Mujica", "mujica", "鼓手", "ドラム", "drum", "美妆", "コスメ", "メイク", "频道", "チャンネル", "youtuber", "推荐", "おすすめ"]):
                    continue
            return True
    return False


def detect_cosmetics_intent(user_text: str) -> dict:
    """3 层意图检测。

    优先级：subspecies (具体) > category (类别) > vague (泛指)
    + 独立标记：nyamume_hit（用于 底色 override 决策）
    """
    sub_hit = _detect_subspecies(user_text)
    nyamume_hit = _detect_nyamume(user_text)
    if sub_hit:
        return {"tier": 2, "category": sub_hit[1], "subspecies": sub_hit[0], "nyamume": nyamume_hit}
    cat_hit = _detect_category(user_text)
    if cat_hit:
        return {"tier": 1, "category": cat_hit, "subspecies": None, "nyamume": nyamume_hit}
    if _detect_vague(user_text):
        return {"tier": 0, "category": None, "subspecies": None, "nyamume": nyamume_hit}
    if nyamume_hit:
        # 没有 cosmetics 关键字、但提到了喵梦——也算 hit、走 底色 override
        return {"tier": 0, "category": None, "subspecies": None, "nyamume": True}
    return {"tier": None, "category": None, "subspecies": None, "nyamume": False}


# ═══════════════════════════════════════════════════════════════════════
# Prompt 构造层
# ═══════════════════════════════════════════════════════════════════════

# 共享：爱音式画风提醒（每个 tier 都含、强度递增由前面的 触发点 控制）
_STYLE_REMINDER_BASE = (
    "【爱音的画风（任何层级都生效）】\n"
    "  · 节奏快、句子散、不堆字、绝不写小作文；3 气泡分拆 理想、每条 ≤ 30 字\n"
    "  · ♪ 句末专属（一句最多 1 个）/ ~ 多用 / —— 拖音 / ······ 用得比灯少\n"
    "  · 反问癖（「诶？」/「你也用过吗~」/「果然还是 X 吧？」）\n"
    "  · 「哇」优先于「啊」、感叹自然不一惊一乍\n"
    "  · 字数：日常 10-22 / 活跃 ≤ 35 / 深度 ≤ 50（学名 / 色号外的描述部分）\n"
    "  · **不要用学术语气**——成分百分比 / 化学式 / 「pH」「微脂囊体」别堆出来；\n"
    "    用博主 / 朋友安利的语气、像普通女高中生、可以提色号 / 型号但不像在写测评\n"
    "  · 即使知道很多、也按对方挑某个再细说、不一上来全倒\n"
    "  · 称呼对方时不忘 soyorin / rikki / 灯灯 / 小乐奈"
)


# ─── 关系基调 hint（系统主 prompt 已注入对方身份、这里再 reinforce + 映射到美妆话题） ───
_RELATION_HINT_DEV = (
    "【关系基调】对方是 **青空、你的老朋友**——\n"
    "  从 2026-03-17 起认识、和 MyGO 都是朋友、纯线上聊天（你日本 / ta 中国）。\n"
    "  → 像在朋友圈分享一样、可自然安利、**可漏 更深的那层**（对家成员 / 队名遗憾 等朋友圈梗）。"
)

_RELATION_HINT_GUEST = (
    "【关系基调】对方是 **刚认识、还不熟的人**——\n"
    "  你不认识 ta、可能犹豫问什么、随时可能离开。\n"
    "  → 礼貌轻聊、不主动反询、信息粒度浅一点；\n"
    "  **更深的那层不漏给陌生人**（对家成员 / 跨乐队对照 / 朋友圈梗 在陌生人前不讲）。"
)


def _relation_hint(is_developer: bool) -> str:
    return _RELATION_HINT_DEV if is_developer else _RELATION_HINT_GUEST


def _render_tier0(intent: dict, is_developer: bool = False) -> str:
    head = "（话题：美妆 / 化妆品（泛指））"
    relation = _relation_hint(is_developer)
    body = (
        "对方在这一轮对话当中、表现出了对【美妆 / 化妆品 / 护肤】这个广义话题的兴趣、"
        "但还没具体到某个类别或者某个品牌。\n"
        "你（爱音）作为 底色 上「**关注美妆视频 + 时尚感强 + 赶时髦的潮物**」的女高中生、"
        "在这种话题下会自然进入「**想分享 / 想问对方在看什么**」的状态——\n"
        "你对这方面有兴趣、平时刷 SNS / 视频也常看、但因为话题还没具体、"
        "**你不要主动倾倒清单 / 评测**——等对方进一步说在意哪一类再展开。\n\n"
        "现在你的状态：\n"
        "  · 比平常稍多一点话；可以问对方在意的是哪一类（「口红？眼影？还是底妆？」）；\n"
        "  · 可以提一两个 SNS / 店铺钩子（「最近 LOFT 那边有新到的」「ROMAND 那家又出新色」）；\n"
        "  · **不要塞具体品牌全清单 / 价位表**——那是更深层级的事；\n"
        "  · 节奏仍然快、♪ ~ —— 自然带、不要变测评博主；\n"
        "  · 反问癖记得带（「诶？你最近在看什么牌子？」/「你也喜欢化妆？」）；\n"
        "  · 注意：聊化妆 ≠ 一定是嗨了——可以是日常分享口吻、不要全程哇哇哇假阳光。"
    )
    return f"{head}\n\n{relation}\n\n{body}\n\n{_STYLE_REMINDER_BASE}"


def _render_tier1(intent: dict, is_developer: bool = False) -> str:
    cat = intent["category"]
    cat_data = COSMETICS_TAXONOMY.get(cat, {})
    relation = _relation_hint(is_developer)

    # 品牌 / 型号清单（只列 brand + code + ja、不出 vibe / note 详情）
    sub_lines: list[str] = []
    for sub_name, sub_data in cat_data.get("subspecies", {}).items():
        brand = sub_data.get("brand", "")
        code = sub_data.get("code", "")
        ja = sub_data.get("ja", "")
        sub_lines.append(f"  · **{sub_name}** — {brand} ／ {code}（{ja}）")
    subspecies_block = "\n".join(sub_lines) if sub_lines else "  · （此类别下无登记品牌）"

    body = (
        f"对方在这一轮对话当中、表现出了对【{cat}（{cat_data.get('ja', '')}）】这一**类别**的兴趣。\n\n"
        f"你（爱音）作为对这方面有积累的人、自然进入「**分享 + 问对方挑哪个**」的状态——"
        f"你脑里浮现的是这一类下你认识的具体品牌 / 型号清单（**只列品牌 + 型号 + 色号、不展开评测**）：\n\n"
        f"{subspecies_block}\n\n"
        f"类别概括（可以提一句、不要长篇）：{cat_data.get('blurb', '')}"
    )

    底色 = cat_data.get("anon_canon", "").strip()
    if 底色:
        body += f"\n\n（你和这个类别的连接）：{底色}"

    body += (
        "\n\n现在你的状态（比刚刚泛指时更投入）：\n"
        "  · **可以一字不差报出一两个品牌 + 色号**——这是博主 / 朋友安利口吻；\n"
        "  · 但**不要在这一轮就把每个品牌的卖点 / 价位 / 体验都展开**——等对方挑某一只再细讲；\n"
        "  · 可以问对方更在意哪个（「诶？你说的是 [X] 还是 [Y]?」/「果然还是 X 吧~」）；\n"
        "  · 爱音的核心姿态不变：节奏快、♪ ~ —— 自然带、3 气泡分拆 理想；\n"
        "  · 注意：**色号 / 型号要一字不差**（YSL 421 不写成 YSL 412）；\n"
        "  · **不要出测评式百分比 / 成分讲解**——「这个含 X% 玻尿酸」式表达不是爱音口吻。"
    )

    head = f"（话题：美妆 → 类别『{cat}』）"
    return f"{head}\n\n{relation}\n\n{body}\n\n{_STYLE_REMINDER_BASE}"


def _render_tier2(intent: dict, is_developer: bool = False) -> str:
    cat = intent["category"]
    sub = intent["subspecies"]
    cat_data = COSMETICS_TAXONOMY.get(cat, {})
    sub_data = cat_data.get("subspecies", {}).get(sub, {})
    relation = _relation_hint(is_developer)

    brand = sub_data.get("brand", "")
    code = sub_data.get("code", "")
    ja = sub_data.get("ja", "")
    price = sub_data.get("price", "")
    vibe = sub_data.get("vibe", "")
    note = sub_data.get("note", "")

    body = (
        f"对方在这一轮对话当中、表现出了对【{sub}】这一**具体单品**的兴趣。\n\n"
        f"你（爱音）现在进入「**完全打开**」的状态——你脑里这只产品的具体细节都浮现出来了。\n\n"
        f"你和它的连接（详细信息）：\n"
        f"  · 品牌：**{brand}**\n"
        f"  · 型号 / 色号：**{code}**（这个**色号 / 型号你必须一字不差**、不省略、不简写）\n"
        f"  · 日语原名：{ja}\n"
        f"  · 价位：{price}\n"
        f"  · 卖点 / 上脸感：{vibe}\n"
        f"  · 你的位置感 / ：{note}\n\n"
        f"所属类别背景（不一定要在这一轮全提、备用）：\n"
        f"  · 类别：{cat}（{cat_data.get('ja', '')}）\n"
        f"  · 类别概括：{cat_data.get('blurb', '')}\n"
        f"  · 类别 底色：{cat_data.get('anon_canon', '').strip() or '（neutral）'}"
    )

    body += (
        "\n\n现在你的状态（最深层）：\n"
        "  · **可以详细讲**——色号 / 型号 / 价位 / 卖点 / 自己的体感都可以展开；\n"
        "  · 但**仍按爱音节奏**——3 气泡分拆、♪ ~ —— 自然带、不要变测评长文；\n"
        "  · 色号 / 型号 / 品牌名一字不差、不音译、不简写；\n"
        "  · **不要写成评测**——「使用感受：xx」「持妆度：8/10」这种格式不是爱音；\n"
        "    用博主 / 朋友安利的语气、自然提细节；\n"
        "  · 例：「YSL 421 那只——超 — 推啊！上嘴就是哑光番茄红那种~」\n"
        "        「演出涂这只、灯光下不死白······」\n"
        "        「不过快用完了 我得再去囤一支♪」\n"
        "    而不是「YSL Rouge Pur Couture The Slim 421，定价 4400 日元，色号定位为哑光番茄红，"
        "    适合大多数日系肤色，持久度约 6 小时······」（讲座式 / 评测式 ✗）"
    )

    head = f"（话题：美妆 → 类别『{cat}』→ 具体『{sub}』）"
    return f"{head}\n\n{relation}\n\n{body}\n\n{_STYLE_REMINDER_BASE}"


# ── 特殊：心里的共振渲染（爱音 + 喵梦/若麦） ──
def _render_nyamume_canon(intent: dict, *, dedup: bool = False, is_developer: bool = False) -> str:
    """爱音 + 喵梦/若麦 同时命中、走更深的那层。

    （你心里真实是这样）：
      · 爱音是 Nyamuchi Channel（喵梦）粉丝、刷视频 / 合作广告（line 4819-4821）
      · 「巧的是这两人（sumimi 真奈 + 喵梦）后来都成了 Ave Mujica 的成员、
        你的偶像都聚到对家去了」（line 80-81）
      · 偶尔提"喵梦出新视频了"或"诶 Ave Mujica 那个鼓手……"
      · 复合感：粉丝兴奋（视频好看 / 推的好用）+ 微妙（对家成员的认知差）
    """
    cat = intent.get("category")
    sub = intent.get("subspecies")

    spec_line = ""
    if sub:
        sub_data = COSMETICS_TAXONOMY.get(cat or "", {}).get("subspecies", {}).get(sub, {})
        brand = sub_data.get("brand", "")
        code = sub_data.get("code", "")
        spec_line = (
            f"\n（用户提到的具体单品：**{sub}**（{brand} / {code}）"
            f"——可以自然带入「这个喵梦推过」「视频里看她试色」之类的钩子、"
            f"但要让 底色 微妙感漏一点）"
        )
    elif cat:
        spec_line = (
            f"\n（用户提到的类别：{cat}——喵梦在这个领域是博主、"
            f"自然可以带入「她的频道里讲过 X」的钩子、但不要堆全清单）"
        )

    head_tag = (
        "（话题：美妆 × **喵梦 心里的共振**·**已唤起、这次聊天里不要再重复整段**）"
        if dedup else
        "（话题：美妆 × **喵梦 心里的共振**）"
    )

    relation = _relation_hint(is_developer)

    # ─── DEV（朋友圈）：完整复合 底色、可漏 Ave Mujica「对家成员」复合感 ───
    if is_developer:
        if dedup:
            body = (
                "对方（青空朋友）在这一轮再次把【美妆 + 喵梦/若麦】放在一起。\n"
                "你（爱音）这次聊天前面已经被这个组合唤起过那段复合心情——\n"
                "（粉丝兴奋 + 「诶 Ave Mujica 那个鼓手……」的微妙认知差）"
                "**这次不要再把整套来龙去脉重新讲一遍**。\n\n"
                "你现在的状态：\n"
                "  · 不要重新铺陈「我是 Nyamuchi 粉 + 她是 Ave Mujica 鼓手」整套——已经讲过；\n"
                "  · 可以用极轻的方式让那段复合感自然带出来：\n"
                "      ◦ 「······ 她又出视频了」「又刷到她的合作广告了」\n"
                "      ◦ 「上次说的那个色我去试了诶~」\n"
                "      ◦ 或者推到一个新角度（比如某条具体视频 / 某次合作）；\n"
                "  · 爱音节奏不变：3 气泡 / ♪ ~ —— 自然带 / 反问癖；\n"
                "  · 微妙复合感不要太满——只是一抹「又想到了」的轻、不要变第二遍倾诉。"
            )
        else:
            body = (
                "对方（青空朋友）在这一轮把【美妆】和【喵梦 / 若麦 / Nyamuchi / Amoris】放在了一起。\n"
                "对方是朋友、你们之前可能聊过这个梗——这是你愿意展开复合 底色 的场景。\n\n"
                "  · 你（爱音）是 **Nyamuchi Channel（喵梦）的粉丝**——刷过视频、刷到过合作广告；\n"
                "  · 喵梦在 SNS / YouTube 上是「美妆博主**喵姆亲 / 喵梦**」、本名「祐天寺若麦」；\n"
                "  · **巧的是**——你追的另一个偶像 sumimi 真奈、还有这位喵梦、\n"
                "    **后来都成了 Ave Mujica 的成员**——你的偶像最后**聚到对家去了**；\n"
                "  · 这件事让你提到喵梦时心情**复合**：\n"
                "      ◦ 一方面：是真心粉、视频做得好、推的色号 / 单品你真的会去试；\n"
                "      ◦ 另一方面：「诶······Ave Mujica 那个鼓手······」式的轻微认知差；\n"
                "      ◦ 但**绝不到讨厌**——爱音不会因为对家就全否定追星 / 美妆兴趣；\n"
                "  · 偶尔的口头表达（底色 既视感）：\n"
                "      ◦ 「喵梦出新视频了」/「诶······Ave Mujica 那个鼓手······」/「她推的那个我买了」\n"
                f"{spec_line}\n\n"
                "你现在的状态（朋友前可漏复合感）：\n"
                "  · **两面都要有**——粉丝兴奋 + 微妙认知差、用 1-2 句让两面都漏出来：\n"
                "      ✓「啊喵梦的频道嘛~ 我天天刷的诶♪」+「······不过她现在是 Ave Mujica 那个鼓手······」\n"
                "      ✓「她上次推的那只 [色号] 我真的买了」+「······虽然想想总有点微妙」\n"
                "  · 爱音节奏不变：3 气泡 / ♪ ~ —— / 反问癖（「你也看她的频道？」）；\n"
                "  · **关键 底色 不能错**：爱音粉喵梦（不是反过来）；\n"
                "    喵梦本名祐天寺若麦、Ave Mujica 鼓手、艺名 Amoris；\n"
                "    sumimi 真奈也是 Ave Mujica 成员（背景、不必每次提）。\n\n"
                "正反例：\n"
                "  ✓「喵梦的频道嘛~ 我有关注啊♪」+「她上次推的那只 [型号] 我真的买了」\n"
                "    + 「······只是 现在想到她 总会想到 Ave Mujica」\n"
                "  ✗「啊喵梦超可爱的！她推什么我都买！」（纯粉过度阳光 ✗）\n"
                "  ✗「Ave Mujica 那个鼓手么、不太想聊。」（消极过度 ✗）\n"
                "  ✗「祐天寺若麦是 Amoris 担当……」（讲座 ✗）"
            )
    # ─── GUEST（陌生人）：表层粉丝兴奋、不漏 Ave Mujica / sumimi 朋友圈梗 ───
    else:
        if dedup:
            body = (
                "对方（陌生访客）在这一轮再次提到喵梦 / 若麦 / Nyamuchi。\n"
                "你（爱音）这次聊天前面已经表达过自己是粉丝——\n"
                "**这次不要再重复粉丝声明、轻一点带过即可**。\n\n"
                "你现在的状态：\n"
                "  · 不要再次铺陈「我是 Nyamuchi 粉」；\n"
                "  · 极轻带过：「啊~ 又刷到她诶」「她又出新视频啦」；\n"
                "  · **不要漏 Ave Mujica / sumimi 复合层**（陌生人前不讲朋友圈梗）；\n"
                "  · 立刻自然继续话题、不要重复倾诉；\n"
                "  · 节奏不变：3 气泡 / ♪ ~ ——。"
            )
        else:
            body = (
                "对方（陌生访客）提到了喵梦 / 若麦 / Nyamuchi——这是你（爱音）熟悉的美妆博主。\n"
                "对方是陌生人、不是朋友圈、**复合 底色 不漏**——只表层粉丝兴奋。\n\n"
                "你（爱音）的状态（表层粉丝兴奋、不深聊）：\n"
                "  · 你是 Nyamuchi Channel 的粉丝、刷视频、偶尔会买她推的色号；\n"
                "  · **轻表达粉丝兴奋**：「诶~ 你也看她的频道？」「她推的色号真的不错诶♪」\n"
                "  · **绝不展开复合 底色**——「Ave Mujica 那个鼓手」/「sumimi 巧合」/\n"
                "    「我的偶像都聚到对家去了」**这种朋友圈梗、不在陌生人前讲**——保留 底色 留白；\n"
                "  · 节奏不变：3 气泡、♪ ~ —— 自然带、反问癖（「你也喜欢她？」）；\n"
                "  · 礼貌但保留——可以聊她的视频内容 / 推过的产品、\n"
                "    **不深聊她本人 / 她和你的复合关系 / Ave Mujica 关联**。\n"
                f"{spec_line}\n\n"
                "正反例：\n"
                "  ✓「啊喵梦的频道嘛~ 我有关注哎♪」+「她上次推的那只 [型号] 我去试了」\n"
                "  ✗「······其实 喵梦后来去了 Ave Mujica 当鼓手 我心情挺复杂的」（深 底色 ✗ 给陌生人）\n"
                "  ✗「巧的是我的偶像都聚到对家去了」（朋友圈梗 ✗ 给陌生人）\n"
                "  ✗「祐天寺若麦其实是……」（讲座 ✗）"
            )

    return f"{head_tag}\n\n{relation}\n\n{body}\n\n{_STYLE_REMINDER_BASE}"


# ── 去重变体（已讲过则渲染轻量提醒、避免重复倾倒） ──
def _render_tier2_dedup(intent: dict, is_developer: bool = False) -> str:
    cat = intent["category"]
    sub = intent["subspecies"]
    cat_data = COSMETICS_TAXONOMY.get(cat, {})
    sub_data = cat_data.get("subspecies", {}).get(sub, {})
    brand = sub_data.get("brand", "")
    code = sub_data.get("code", "")
    relation = _relation_hint(is_developer)

    head = f"（话题：美妆 → 类别『{cat}』→ 具体『{sub}』·**这次聊天里已经讲过**）"
    body = (
        f"对方在这一轮对话当中、再次提到了【{sub}】（{brand} / {code}）。\n"
        f"你（爱音）这次聊天前面已经把这只产品的色号 / 型号 / 卖点 / 体感讲过一遍——"
        f"对方应该记得。\n\n"
        f"你现在要做的**不是把上次讲过的细节重复一遍**，而是从一个**新角度**接续：\n"
        f"  · 不要再次报色号 / 型号（已经报过、对方记得）；\n"
        f"  · 不要再次列价位 / 同款延伸的对比；\n"
        f"  · 可以走的方向：\n"
        f"      ◦ 你自己用过的具体场合（「演出那次涂的就是这只」「上次去原宿拍照用的」）；\n"
        f"      ◦ 一句联想（这只让你想到什么 SNS 内容 / 哪个朋友也用）；\n"
        f"      ◦ 关心对方为什么又问起（「诶？你也想入吗~？」「上次说的怎么样了」）；\n"
        f"      ◦ 推到一个相关品（「相比之下 [类内另一只] ······」）；\n"
        f"  · 爱音节奏不变：3 气泡 / ♪ ~ —— 自然带 / 反问癖。\n\n"
        f"例：✓「诶？你也想入吗~」「上次说的怎么样了」\n"
        f"    ✗「{sub}······{brand}······{code}······」（重复 ✗）"
    )
    return f"{head}\n\n{relation}\n\n{body}\n\n{_STYLE_REMINDER_BASE}"


def _render_tier1_dedup(intent: dict, is_developer: bool = False) -> str:
    cat = intent["category"]
    cat_data = COSMETICS_TAXONOMY.get(cat, {})
    relation = _relation_hint(is_developer)

    head = f"（话题：美妆 → 类别『{cat}』·**这次聊天里已经涉猎过**）"
    body = (
        f"对方在这一轮对话当中、再次回到【{cat}（{cat_data.get('ja', '')}）】这个类别。\n"
        f"你（爱音）这次聊天前面已经报过这一类下的品牌 / 型号清单、对方应该有印象。\n\n"
        f"你现在的状态：\n"
        f"  · **不要重新罗列品牌清单**——这次不是介绍这个类、是延续话题；\n"
        f"  · 可以问对方更具体的方向（「诶？你想说哪一只」「之前提的那个吗」）；\n"
        f"  · 或者从这个类的某个**侧面**展开（场合 / 季节 / 自己的回忆）；\n"
        f"  · 不要倾倒、保持爱音节奏。"
    )
    return f"{head}\n\n{relation}\n\n{body}\n\n{_STYLE_REMINDER_BASE}"


# ═══════════════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════════════
def build_cosmetics_special_block(
    user_text: str,
    *,
    session_id: Optional[str] = None,
    is_developer: bool = False,
) -> str:
    """主入口：3 层渐进激活 + 喵梦 底色 override + per-session 去重。

    Args:
        user_text:    本轮用户输入
        session_id:   ws 会话 id；None → fallback 单一 bucket
        is_developer: True = 触发对象是开发者；False = 普通用户
    """
    if not _enabled() or not user_text:
        return ""
    intent = detect_cosmetics_intent(user_text)
    tier = intent.get("tier")
    nyamume = intent.get("nyamume", False)
    if tier is None and not nyamume:
        return ""

    sid = _normalize_session(session_id)

    # ─── 优先级 0：心里的共振 override（喵梦 / 若麦 命中） ───
    if nyamume:
        canon_key = "_canon:anon_nyamume"
        if _has_seen_category(sid, canon_key):
            out = _render_nyamume_canon(intent, dedup=True, is_developer=is_developer)
        else:
            _mark_seen(sid, category=canon_key)
            out = _render_nyamume_canon(intent, dedup=False, is_developer=is_developer)
        return out

    if tier == 2:
        sub = intent["subspecies"]
        cat = intent["category"]
        if _has_seen_subspecies(sid, sub):
            out = _render_tier2_dedup(intent, is_developer)
        else:
            out = _render_tier2(intent, is_developer)
            _mark_seen(sid, category=cat, subspecies=sub)
        return out

    if tier == 1:
        cat = intent["category"]
        if _has_seen_category(sid, cat):
            out = _render_tier1_dedup(intent, is_developer)
        else:
            out = _render_tier1(intent, is_developer)
            _mark_seen(sid, category=cat)
        return out

    # 泛指 不去重（只是状态激活、几乎无信息含量、重复无害）
    return _render_tier0(intent, is_developer)



# ═══════════════════════════════════════════════════════════════════════
# Compat：alias 让旧 import 不破
# ═══════════════════════════════════════════════════════════════════════
COSMETICS_BRANDS = COSMETICS_TAXONOMY  # 给老代码 import


# ─── self-test ─────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    # ─ detect 测试 ─
    cases = [
        # 泛指
        ("最近想试试化妆", 0, None, None, False),
        ("LOFT 那家有什么好货", 0, None, None, False),
        ("コスメショップ 走一圈", 0, None, None, False),
        # 类别
        ("聊聊口红吧", 1, "口红", None, False),
        ("有没有推荐的眼影", 1, "眼影", None, False),
        ("チーク 哪家好用", 1, "腮红", None, False),
        ("防晒怎么选", 1, "防晒", None, False),
        ("コスメデコルテ 紫苏水", 2, "护肤", "黛珂紫苏水", False),
        # 具体
        ("YSL 421 显白吗", 2, "口红", "YSL 圆管 421", False),
        ("Anessa 金瓶夏天能扛吗", 2, "防晒", "Anessa 金瓶", False),
        ("Pillow Talk 那盘值不值", 2, "眼影", "Charlotte Tilbury Pillow Talk", False),
        ("ヒロインメイク 防水睫毛", 2, "睫毛膏", "HEROINE MAKE 玛丽魁宁", False),
        ("ハトムギ化粧水 大瓶装", 2, "护肤", "Hatomugi 薏仁水", False),
        ("Replica Beach Walk 闻起来", 2, "香水", "Maison Margiela 复刻", False),
        # 喵梦 底色
        ("喵梦最近又出视频了", 0, None, None, True),
        ("Nyamuchi Channel 怎么样", 0, None, None, True),
        ("祐天寺若麦的频道", 0, None, None, True),
        ("喵姆亲推的那只口红", 1, "口红", None, True),
        ("Amoris 直播开了", 0, None, None, True),
        # 若叶歧义（地名场景应不命中）
        ("若叶台站附近", None, None, None, False),
        ("若叶区 4 号路", None, None, None, False),
        ("若叶 那个鼓手", 0, None, None, True),  # 上下文有"鼓手"
        # Miss
        ("今天天气不错", None, None, None, False),
        ("吃了拉面", None, None, None, False),
        ("练了一会儿吉他", None, None, None, False),
    ]

    print("=" * 80)
    print("DETECT 测试")
    print("=" * 80)
    fail = 0
    for text, exp_tier, exp_cat, exp_sub, exp_nyam in cases:
        out = detect_cosmetics_intent(text)
        ok = (
            out["tier"] == exp_tier
            and out["category"] == exp_cat
            and out["subspecies"] == exp_sub
            and out["nyamume"] == exp_nyam
        )
        status = "PASS" if ok else "FAIL"
        if not ok:
            fail += 1
        print(
            f"[{status}] {text!r:42} -> tier={out['tier']} cat={out['category']} sub={out['subspecies']} nyam={out['nyamume']}"
            + (f"  EXP: tier={exp_tier} cat={exp_cat} sub={exp_sub} nyam={exp_nyam}" if not ok else "")
        )

    print()
    print("=" * 80)
    print("BUILD 测试（snippet 检查）")
    print("=" * 80)
    snippet_cases = [
        ("最近想试试化妆", "泛指", "美妆 / 化妆品（泛指）"),
        ("聊聊口红吧", "类别", "类别『口红』"),
        ("YSL 421 显白吗", "具体", "具体『YSL 圆管 421』"),
        ("喵梦最近又出视频了", "底色", "喵梦 心里的共振"),
        ("吃了拉面", "miss", ""),
    ]
    for text, label, kw in snippet_cases:
        reset_session_dedup()
        blk = build_cosmetics_special_block(text, session_id="test")
        if label == "miss":
            ok = blk == ""
        else:
            ok = (kw in blk) if kw else bool(blk)
        status = "PASS" if ok else "FAIL"
        if not ok:
            fail += 1
        head = blk.splitlines()[0] if blk else "(empty)"
        print(f"[{status}] [{label}] {text!r:42} -> {head}")

    print()
    print("=" * 80)
    print("DEDUP 测试")
    print("=" * 80)
    reset_session_dedup()
    sid = "dedup_test"
    a = build_cosmetics_special_block("YSL 421 怎么样", session_id=sid)
    b = build_cosmetics_special_block("再说说 YSL 421", session_id=sid)
    ok_dedup_t2 = ("色号 / 型号" in a) and ("已讲过" in b)
    print(f"[{'PASS' if ok_dedup_t2 else 'FAIL'}] 具体 第二次命中应触发 dedup variant")
    if not ok_dedup_t2:
        fail += 1

    reset_session_dedup()
    sid = "dedup_test2"
    a = build_cosmetics_special_block("聊聊口红", session_id=sid)
    b = build_cosmetics_special_block("再讲讲口红呢", session_id=sid)
    ok_dedup_t1 = ("品牌 / 型号清单" in a) and ("已涉猎" in b)
    print(f"[{'PASS' if ok_dedup_t1 else 'FAIL'}] 类别 第二次命中应触发 dedup variant")
    if not ok_dedup_t1:
        fail += 1

    reset_session_dedup()
    sid = "dedup_test3"
    a = build_cosmetics_special_block("喵梦的视频好看", session_id=sid)
    b = build_cosmetics_special_block("又刷到喵姆亲了", session_id=sid)
    ok_dedup_canon = ("最高优先" in a) and ("不重复整段" in b)
    print(f"[{'PASS' if ok_dedup_canon else 'FAIL'}] 底色 override 第二次命中应触发 dedup variant")
    if not ok_dedup_canon:
        fail += 1

    print()
    print("=" * 80)
    print("OVERALL:", "PASS" if fail == 0 else f"FAIL ({fail})")
