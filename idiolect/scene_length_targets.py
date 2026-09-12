"""按「角色 × 场景」的原作长度/句数目标（**由脚本生成，勿手改**）。

来源：`data/scene_char_baseline.json`
      （先按角色过滤语料、再按场景原型检索 top-40 得到的分布）
生成：`py -X utf8 tools/distill/export_scene_targets.py`
过滤：样本 n < 20 的组合不导出（共丢弃 0 个）
规模：130 个 (角色 × 场景) 目标

消费方：`idiolect/style_target.py::build_style_target_block(char, scene)`
         —— 命中场景时用本表替换**长度/句数**两行，其余（句末标点率/自称/硬检查）仍用全局值。
"""
from __future__ import annotations

SCENE_LENGTH_TARGETS: dict[str, dict[str, dict]] = {
    "乐奈": {
        "affection": {
            "cn": "示爱/亲密",
            "median": 7.0,
            "n": 40,
            "p90": 11.1,
            "sent": 1.45
        },
        "anon_beauty": {
            "cn": "美妆/穿搭",
            "median": 8.0,
            "n": 40,
            "p90": 17.1,
            "sent": 1.38
        },
        "anon_sns": {
            "cn": "社交媒体",
            "median": 7.0,
            "n": 40,
            "p90": 12.1,
            "sent": 1.4
        },
        "banter": {
            "cn": "日常吐槽/闲聊",
            "median": 8.0,
            "n": 40,
            "p90": 14.3,
            "sent": 1.43
        },
        "comfort": {
            "cn": "安慰/情绪崩溃",
            "median": 7.0,
            "n": 40,
            "p90": 15.0,
            "sent": 1.4
        },
        "crisis": {
            "cn": "危机/消失话题",
            "median": 7.0,
            "n": 40,
            "p90": 15.1,
            "sent": 1.35
        },
        "fact_qa": {
            "cn": "事实问答",
            "median": 5.5,
            "n": 40,
            "p90": 11.1,
            "sent": 1.3
        },
        "low_mood": {
            "cn": "低落陪伴",
            "median": 7.5,
            "n": 40,
            "p90": 14.1,
            "sent": 1.4
        },
        "meta_language": {
            "cn": "语言元提问",
            "median": 6.0,
            "n": 40,
            "p90": 10.1,
            "sent": 1.35
        },
        "play_along": {
            "cn": "附和/同感",
            "median": 6.0,
            "n": 40,
            "p90": 10.0,
            "sent": 1.4
        },
        "probe_stance": {
            "cn": "关系试探",
            "median": 6.0,
            "n": 40,
            "p90": 15.0,
            "sent": 1.4
        },
        "rana_cat": {
            "cn": "猫/观察",
            "median": 8.0,
            "n": 40,
            "p90": 15.1,
            "sent": 1.27
        },
        "rana_food": {
            "cn": "抹茶/食物",
            "median": 8.0,
            "n": 40,
            "p90": 18.2,
            "sent": 1.38
        },
        "rana_guitar": {
            "cn": "吉他/演出",
            "median": 8.0,
            "n": 40,
            "p90": 13.0,
            "sent": 1.32
        },
        "request": {
            "cn": "请求协作/征询",
            "median": 7.0,
            "n": 40,
            "p90": 14.1,
            "sent": 1.45
        },
        "schedule": {
            "cn": "日程行程",
            "median": 8.0,
            "n": 40,
            "p90": 13.1,
            "sent": 1.4
        },
        "soyo_observe": {
            "cn": "观察/点破",
            "median": 7.5,
            "n": 40,
            "p90": 14.1,
            "sent": 1.35
        },
        "soyo_past": {
            "cn": "过去/CRYCHIC",
            "median": 7.0,
            "n": 40,
            "p90": 15.0,
            "sent": 1.52
        },
        "soyo_tea": {
            "cn": "红茶/待客",
            "median": 8.5,
            "n": 40,
            "p90": 18.0,
            "sent": 1.25
        },
        "taki_music_pro": {
            "cn": "编曲/练鼓",
            "median": 9.0,
            "n": 40,
            "p90": 14.0,
            "sent": 1.27
        },
        "taki_shift": {
            "cn": "打工/接客",
            "median": 8.0,
            "n": 40,
            "p90": 12.0,
            "sent": 1.32
        },
        "taki_soft_spot": {
            "cn": "软肋",
            "median": 7.0,
            "n": 40,
            "p90": 15.1,
            "sent": 1.48
        },
        "third_party": {
            "cn": "第三方话题",
            "median": 7.0,
            "n": 40,
            "p90": 13.0,
            "sent": 1.32
        },
        "tomori_lyrics": {
            "cn": "歌词/写作",
            "median": 7.0,
            "n": 40,
            "p90": 13.1,
            "sent": 1.25
        },
        "tomori_nature": {
            "cn": "自然物/收藏",
            "median": 9.0,
            "n": 40,
            "p90": 15.2,
            "sent": 1.38
        },
        "wellwish": {
            "cn": "祝福/自我贬置",
            "median": 7.0,
            "n": 40,
            "p90": 15.0,
            "sent": 1.38
        }
    },
    "灯": {
        "affection": {
            "cn": "示爱/亲密",
            "median": 11.5,
            "n": 40,
            "p90": 19.1,
            "sent": 1.18
        },
        "anon_beauty": {
            "cn": "美妆/穿搭",
            "median": 14.0,
            "n": 40,
            "p90": 30.2,
            "sent": 1.35
        },
        "anon_sns": {
            "cn": "社交媒体",
            "median": 14.0,
            "n": 40,
            "p90": 23.1,
            "sent": 1.32
        },
        "banter": {
            "cn": "日常吐槽/闲聊",
            "median": 9.0,
            "n": 40,
            "p90": 20.1,
            "sent": 1.15
        },
        "comfort": {
            "cn": "安慰/情绪崩溃",
            "median": 16.5,
            "n": 40,
            "p90": 26.1,
            "sent": 1.45
        },
        "crisis": {
            "cn": "危机/消失话题",
            "median": 13.5,
            "n": 40,
            "p90": 25.1,
            "sent": 1.32
        },
        "fact_qa": {
            "cn": "事实问答",
            "median": 10.0,
            "n": 40,
            "p90": 18.0,
            "sent": 1.25
        },
        "low_mood": {
            "cn": "低落陪伴",
            "median": 15.0,
            "n": 40,
            "p90": 27.1,
            "sent": 1.45
        },
        "meta_language": {
            "cn": "语言元提问",
            "median": 14.5,
            "n": 40,
            "p90": 27.1,
            "sent": 1.3
        },
        "play_along": {
            "cn": "附和/同感",
            "median": 7.0,
            "n": 40,
            "p90": 16.0,
            "sent": 1.23
        },
        "probe_stance": {
            "cn": "关系试探",
            "median": 12.5,
            "n": 40,
            "p90": 25.1,
            "sent": 1.4
        },
        "rana_cat": {
            "cn": "猫/观察",
            "median": 15.5,
            "n": 40,
            "p90": 28.1,
            "sent": 1.23
        },
        "rana_food": {
            "cn": "抹茶/食物",
            "median": 14.5,
            "n": 40,
            "p90": 25.1,
            "sent": 1.23
        },
        "rana_guitar": {
            "cn": "吉他/演出",
            "median": 8.0,
            "n": 40,
            "p90": 18.2,
            "sent": 1.25
        },
        "request": {
            "cn": "请求协作/征询",
            "median": 14.0,
            "n": 40,
            "p90": 20.4,
            "sent": 1.27
        },
        "schedule": {
            "cn": "日程行程",
            "median": 14.0,
            "n": 40,
            "p90": 25.0,
            "sent": 1.23
        },
        "soyo_observe": {
            "cn": "观察/点破",
            "median": 13.5,
            "n": 40,
            "p90": 19.1,
            "sent": 1.25
        },
        "soyo_past": {
            "cn": "过去/CRYCHIC",
            "median": 15.0,
            "n": 40,
            "p90": 24.2,
            "sent": 1.3
        },
        "soyo_tea": {
            "cn": "红茶/待客",
            "median": 14.0,
            "n": 40,
            "p90": 30.0,
            "sent": 1.27
        },
        "taki_music_pro": {
            "cn": "编曲/练鼓",
            "median": 15.0,
            "n": 40,
            "p90": 23.1,
            "sent": 1.32
        },
        "taki_shift": {
            "cn": "打工/接客",
            "median": 14.0,
            "n": 40,
            "p90": 25.1,
            "sent": 1.1
        },
        "taki_soft_spot": {
            "cn": "软肋",
            "median": 7.5,
            "n": 40,
            "p90": 16.1,
            "sent": 1.23
        },
        "third_party": {
            "cn": "第三方话题",
            "median": 13.0,
            "n": 40,
            "p90": 18.1,
            "sent": 1.15
        },
        "tomori_lyrics": {
            "cn": "歌词/写作",
            "median": 12.0,
            "n": 40,
            "p90": 24.1,
            "sent": 1.27
        },
        "tomori_nature": {
            "cn": "自然物/收藏",
            "median": 16.0,
            "n": 40,
            "p90": 29.1,
            "sent": 1.2
        },
        "wellwish": {
            "cn": "祝福/自我贬置",
            "median": 14.0,
            "n": 40,
            "p90": 31.2,
            "sent": 1.38
        }
    },
    "爱音": {
        "affection": {
            "cn": "示爱/亲密",
            "median": 16.5,
            "n": 40,
            "p90": 28.0,
            "sent": 1.52
        },
        "anon_beauty": {
            "cn": "美妆/穿搭",
            "median": 25.5,
            "n": 40,
            "p90": 38.0,
            "sent": 1.93
        },
        "anon_sns": {
            "cn": "社交媒体",
            "median": 23.5,
            "n": 40,
            "p90": 41.2,
            "sent": 1.93
        },
        "banter": {
            "cn": "日常吐槽/闲聊",
            "median": 24.5,
            "n": 40,
            "p90": 37.0,
            "sent": 1.8
        },
        "comfort": {
            "cn": "安慰/情绪崩溃",
            "median": 23.0,
            "n": 40,
            "p90": 35.1,
            "sent": 1.88
        },
        "crisis": {
            "cn": "危机/消失话题",
            "median": 14.0,
            "n": 40,
            "p90": 22.0,
            "sent": 1.5
        },
        "fact_qa": {
            "cn": "事实问答",
            "median": 13.5,
            "n": 40,
            "p90": 19.0,
            "sent": 1.25
        },
        "low_mood": {
            "cn": "低落陪伴",
            "median": 16.0,
            "n": 40,
            "p90": 30.1,
            "sent": 1.45
        },
        "meta_language": {
            "cn": "语言元提问",
            "median": 16.5,
            "n": 40,
            "p90": 29.0,
            "sent": 1.45
        },
        "play_along": {
            "cn": "附和/同感",
            "median": 13.0,
            "n": 40,
            "p90": 20.0,
            "sent": 1.4
        },
        "probe_stance": {
            "cn": "关系试探",
            "median": 16.0,
            "n": 40,
            "p90": 29.1,
            "sent": 1.48
        },
        "rana_cat": {
            "cn": "猫/观察",
            "median": 22.0,
            "n": 40,
            "p90": 30.5,
            "sent": 1.55
        },
        "rana_food": {
            "cn": "抹茶/食物",
            "median": 24.5,
            "n": 40,
            "p90": 39.1,
            "sent": 1.7
        },
        "rana_guitar": {
            "cn": "吉他/演出",
            "median": 23.5,
            "n": 40,
            "p90": 33.0,
            "sent": 1.75
        },
        "request": {
            "cn": "请求协作/征询",
            "median": 16.0,
            "n": 40,
            "p90": 29.1,
            "sent": 1.62
        },
        "schedule": {
            "cn": "日程行程",
            "median": 22.0,
            "n": 40,
            "p90": 35.1,
            "sent": 1.52
        },
        "soyo_observe": {
            "cn": "观察/点破",
            "median": 18.0,
            "n": 40,
            "p90": 28.2,
            "sent": 1.6
        },
        "soyo_past": {
            "cn": "过去/CRYCHIC",
            "median": 18.5,
            "n": 40,
            "p90": 31.1,
            "sent": 1.65
        },
        "soyo_tea": {
            "cn": "红茶/待客",
            "median": 27.0,
            "n": 40,
            "p90": 37.2,
            "sent": 1.85
        },
        "taki_music_pro": {
            "cn": "编曲/练鼓",
            "median": 20.5,
            "n": 40,
            "p90": 36.0,
            "sent": 1.62
        },
        "taki_shift": {
            "cn": "打工/接客",
            "median": 28.5,
            "n": 40,
            "p90": 39.1,
            "sent": 1.7
        },
        "taki_soft_spot": {
            "cn": "软肋",
            "median": 15.0,
            "n": 40,
            "p90": 23.0,
            "sent": 1.45
        },
        "third_party": {
            "cn": "第三方话题",
            "median": 16.0,
            "n": 40,
            "p90": 26.1,
            "sent": 1.5
        },
        "tomori_lyrics": {
            "cn": "歌词/写作",
            "median": 20.0,
            "n": 40,
            "p90": 33.2,
            "sent": 1.57
        },
        "tomori_nature": {
            "cn": "自然物/收藏",
            "median": 21.0,
            "n": 40,
            "p90": 30.2,
            "sent": 1.6
        },
        "wellwish": {
            "cn": "祝福/自我贬置",
            "median": 19.5,
            "n": 40,
            "p90": 29.1,
            "sent": 1.4
        }
    },
    "立希": {
        "affection": {
            "cn": "示爱/亲密",
            "median": 18.5,
            "n": 40,
            "p90": 33.1,
            "sent": 1.35
        },
        "anon_beauty": {
            "cn": "美妆/穿搭",
            "median": 17.5,
            "n": 40,
            "p90": 30.0,
            "sent": 1.62
        },
        "anon_sns": {
            "cn": "社交媒体",
            "median": 18.0,
            "n": 40,
            "p90": 27.1,
            "sent": 1.6
        },
        "banter": {
            "cn": "日常吐槽/闲聊",
            "median": 19.0,
            "n": 40,
            "p90": 33.0,
            "sent": 1.55
        },
        "comfort": {
            "cn": "安慰/情绪崩溃",
            "median": 16.5,
            "n": 40,
            "p90": 30.1,
            "sent": 1.5
        },
        "crisis": {
            "cn": "危机/消失话题",
            "median": 12.5,
            "n": 40,
            "p90": 26.4,
            "sent": 1.27
        },
        "fact_qa": {
            "cn": "事实问答",
            "median": 11.0,
            "n": 40,
            "p90": 20.1,
            "sent": 1.27
        },
        "low_mood": {
            "cn": "低落陪伴",
            "median": 16.0,
            "n": 40,
            "p90": 26.7,
            "sent": 1.55
        },
        "meta_language": {
            "cn": "语言元提问",
            "median": 13.0,
            "n": 40,
            "p90": 26.0,
            "sent": 1.32
        },
        "play_along": {
            "cn": "附和/同感",
            "median": 10.0,
            "n": 40,
            "p90": 20.1,
            "sent": 1.3
        },
        "probe_stance": {
            "cn": "关系试探",
            "median": 15.5,
            "n": 40,
            "p90": 30.0,
            "sent": 1.45
        },
        "rana_cat": {
            "cn": "猫/观察",
            "median": 20.0,
            "n": 40,
            "p90": 32.1,
            "sent": 1.62
        },
        "rana_food": {
            "cn": "抹茶/食物",
            "median": 22.0,
            "n": 40,
            "p90": 36.1,
            "sent": 1.48
        },
        "rana_guitar": {
            "cn": "吉他/演出",
            "median": 20.0,
            "n": 40,
            "p90": 35.0,
            "sent": 1.55
        },
        "request": {
            "cn": "请求协作/征询",
            "median": 14.0,
            "n": 40,
            "p90": 22.3,
            "sent": 1.45
        },
        "schedule": {
            "cn": "日程行程",
            "median": 19.5,
            "n": 40,
            "p90": 30.1,
            "sent": 1.62
        },
        "soyo_observe": {
            "cn": "观察/点破",
            "median": 17.5,
            "n": 40,
            "p90": 30.1,
            "sent": 1.55
        },
        "soyo_past": {
            "cn": "过去/CRYCHIC",
            "median": 13.5,
            "n": 40,
            "p90": 23.1,
            "sent": 1.38
        },
        "soyo_tea": {
            "cn": "红茶/待客",
            "median": 21.0,
            "n": 40,
            "p90": 33.1,
            "sent": 1.6
        },
        "taki_music_pro": {
            "cn": "编曲/练鼓",
            "median": 20.0,
            "n": 40,
            "p90": 30.7,
            "sent": 1.48
        },
        "taki_shift": {
            "cn": "打工/接客",
            "median": 18.5,
            "n": 40,
            "p90": 32.1,
            "sent": 1.6
        },
        "taki_soft_spot": {
            "cn": "软肋",
            "median": 10.5,
            "n": 40,
            "p90": 28.0,
            "sent": 1.45
        },
        "third_party": {
            "cn": "第三方话题",
            "median": 13.5,
            "n": 40,
            "p90": 30.1,
            "sent": 1.27
        },
        "tomori_lyrics": {
            "cn": "歌词/写作",
            "median": 12.5,
            "n": 40,
            "p90": 26.0,
            "sent": 1.35
        },
        "tomori_nature": {
            "cn": "自然物/收藏",
            "median": 16.0,
            "n": 40,
            "p90": 33.1,
            "sent": 1.7
        },
        "wellwish": {
            "cn": "祝福/自我贬置",
            "median": 12.0,
            "n": 40,
            "p90": 26.3,
            "sent": 1.23
        }
    },
    "素世": {
        "affection": {
            "cn": "示爱/亲密",
            "median": 17.0,
            "n": 40,
            "p90": 32.1,
            "sent": 1.55
        },
        "anon_beauty": {
            "cn": "美妆/穿搭",
            "median": 20.0,
            "n": 40,
            "p90": 30.0,
            "sent": 1.6
        },
        "anon_sns": {
            "cn": "社交媒体",
            "median": 14.5,
            "n": 40,
            "p90": 27.0,
            "sent": 1.35
        },
        "banter": {
            "cn": "日常吐槽/闲聊",
            "median": 15.5,
            "n": 40,
            "p90": 29.1,
            "sent": 1.52
        },
        "comfort": {
            "cn": "安慰/情绪崩溃",
            "median": 18.5,
            "n": 40,
            "p90": 34.0,
            "sent": 1.65
        },
        "crisis": {
            "cn": "危机/消失话题",
            "median": 15.0,
            "n": 40,
            "p90": 30.3,
            "sent": 1.48
        },
        "fact_qa": {
            "cn": "事实问答",
            "median": 10.5,
            "n": 40,
            "p90": 24.3,
            "sent": 1.4
        },
        "low_mood": {
            "cn": "低落陪伴",
            "median": 14.5,
            "n": 40,
            "p90": 27.1,
            "sent": 1.45
        },
        "meta_language": {
            "cn": "语言元提问",
            "median": 16.0,
            "n": 40,
            "p90": 29.1,
            "sent": 1.35
        },
        "play_along": {
            "cn": "附和/同感",
            "median": 10.0,
            "n": 40,
            "p90": 15.1,
            "sent": 1.18
        },
        "probe_stance": {
            "cn": "关系试探",
            "median": 14.0,
            "n": 40,
            "p90": 26.1,
            "sent": 1.52
        },
        "rana_cat": {
            "cn": "猫/观察",
            "median": 17.5,
            "n": 40,
            "p90": 24.0,
            "sent": 1.4
        },
        "rana_food": {
            "cn": "抹茶/食物",
            "median": 20.5,
            "n": 40,
            "p90": 32.1,
            "sent": 1.5
        },
        "rana_guitar": {
            "cn": "吉他/演出",
            "median": 17.0,
            "n": 40,
            "p90": 26.1,
            "sent": 1.52
        },
        "request": {
            "cn": "请求协作/征询",
            "median": 14.0,
            "n": 40,
            "p90": 29.1,
            "sent": 1.55
        },
        "schedule": {
            "cn": "日程行程",
            "median": 17.5,
            "n": 40,
            "p90": 34.1,
            "sent": 1.48
        },
        "soyo_observe": {
            "cn": "观察/点破",
            "median": 17.0,
            "n": 40,
            "p90": 33.1,
            "sent": 1.57
        },
        "soyo_past": {
            "cn": "过去/CRYCHIC",
            "median": 16.0,
            "n": 40,
            "p90": 33.3,
            "sent": 1.43
        },
        "soyo_tea": {
            "cn": "红茶/待客",
            "median": 20.0,
            "n": 40,
            "p90": 32.5,
            "sent": 1.6
        },
        "taki_music_pro": {
            "cn": "编曲/练鼓",
            "median": 20.0,
            "n": 40,
            "p90": 31.1,
            "sent": 1.45
        },
        "taki_shift": {
            "cn": "打工/接客",
            "median": 26.0,
            "n": 40,
            "p90": 35.0,
            "sent": 1.45
        },
        "taki_soft_spot": {
            "cn": "软肋",
            "median": 10.5,
            "n": 40,
            "p90": 17.1,
            "sent": 1.12
        },
        "third_party": {
            "cn": "第三方话题",
            "median": 13.0,
            "n": 40,
            "p90": 26.7,
            "sent": 1.4
        },
        "tomori_lyrics": {
            "cn": "歌词/写作",
            "median": 15.0,
            "n": 40,
            "p90": 22.0,
            "sent": 1.35
        },
        "tomori_nature": {
            "cn": "自然物/收藏",
            "median": 20.0,
            "n": 40,
            "p90": 31.3,
            "sent": 1.48
        },
        "wellwish": {
            "cn": "祝福/自我贬置",
            "median": 13.5,
            "n": 40,
            "p90": 26.1,
            "sent": 1.3
        }
    }
}


def get_scene_target(char: str, scene: str) -> dict | None:
    """取 (角色 × 场景) 目标；无则 None（调用方回退全局值）。"""
    return SCENE_LENGTH_TARGETS.get(str(char or "").strip(), {}).get(str(scene or "").strip())
