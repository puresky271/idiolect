# data/ —— 派生统计（不含原作文本）

这里的文件是从原作台词**统计出来的聚合量**，随仓库发布，用来让「clone 下来就能跑」成立：prompt 里的数字、评分的基线、探针的参照系都读这些文件。

| 文件 | 内容 | 生成脚本 | 被谁消费 |
|---|---|---|---|
| `style_targets.json` | 每个角色的全局说话尺度：中位/p90 字数、句数、小句数、标点出现率、自称率、高频语气词 | `tools/distill/export_targets.py` | `idiolect/style_target.py` |
| `scene_char_baseline.json` | 130 个 `角色\|场景` 组合的原作分布（条数、字数分位、句数分位） | `tools/distill/scene_char_baseline.py` | `tools/score/scene_distill.py` |
| `scene_stats.json` | 逐场景的通用统计与角色侧对照 | `tools/distill/scene_stats.py` | 场景发现与文档 |
| `tic_profile.json` | 每角色的口癖排行：频次、每万字出现率、句首/句末占比、专指度 | `tools/distill/tic_profile.py` | `idiolect/characters/*/voice.py` 的编写依据 |
| `tic_by_scene.json` | 口癖按场景拆开的显著项 | `tools/distill/tic_by_scene.py` | 场景化口癖指引 |
| `style_profiles.json` | 评分用的完整风格画像（均值/标准差/分位/出现率），探针在无语料时读它 | `tools/distill/export_profiles.py` | `tools/probe/probe_runner.py` |

两点说明：

1. **没有台词。** 原本的基线文件里带例句字段，发布前已剥离。要例句就自己抓语料重算，见 `docs/02-corpus.md`。
2. **语料换代要重算。** `py -X utf8 tools/distill/export_profiles.py --check` 会比对已发布画像与新语料的重算结果；不一致说明语料换了版本，数字需要重新导出，否则 prompt 里的尺度与评分基线会对不上。
