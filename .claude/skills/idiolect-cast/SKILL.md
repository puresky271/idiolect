---
name: idiolect-cast
description: "Create the role packages for a new cast in idiolect: the per-character canon profile, voice manifest, turn_logic scene modules and voice_check post-processing, plus registration and the gates that keep them honest. Use this skill whenever the user wants to add a character, move the method to another work's cast, wire a new character into the four-layer assembly, write or review a voice manifest, add a turn_logic module, or asks why a character's prompt is missing a layer or why a scene never fires. Covers the minimum package API, the registry registration step, the general-scene order invariant, the no-copyable-example rule, the meta-narrative ban, and the offline_smoke acceptance run."
---

# idiolect-cast：建角色包并接进四层

四层里有两层是**人手写的**，不是从语料推出来的：

| 层 | 来源 | 谁写 |
|---|---|---|
| `canon` | 角色长档案 | **你**（据公开资料整理） |
| `voice` | 语气 manifest：句式、口癖、关系差异、反模板硬约束 | **你**（据 `data/` 的统计落笔） |
| `style_target` | 字数/句数/句末/自称的数字；命中场景换该场景数字 | 从 `data/` 生成 |
| `turn_logic` | 本轮场景/话题指引，命中才注入 | **你**（触发词要有语料实证） |

前置：派生统计已就绪（[`idiolect-distill`](../idiolect-distill/SKILL.md)）。逐条细节见 [`docs/05-tooling.md`](../../../docs/05-tooling.md) 第 9 节与 [`docs/07-turn-logic-and-postprocessing.md`](../../../docs/07-turn-logic-and-postprocessing.md)。

## 1. 最小角色包

```
idiolect/characters/<key>/
  __init__.py
  api.py          # 对外窄入口：get_canon_profile / get_voice_manifest /
                  # render_supplemental_blocks / postprocess_reply（可选）
  canon.py        # 长档案正文（PROFILE_TEXT）
  voice.py        # 语气 manifest
  turn_logic/     # 场景模块（SceneModule）+ __init__.py 的模块列表
  voice_check/    # 出站清洗（无损）与风格改写（有损，分开）
```

`is_<char>()` 这类名字判断**不要自带名单**：名字表只有 `idiolect/registry.py` 一份，函数体写成 `canonicalize_name(character) == "<canonical>"`。自带一张表的代价实测过——别名解析成功、包内 gate 判 False，于是**静默返回空**（2026-09-13 修的那批）。

## 2. 注册

```python
# idiolect/registry.py
_PACKAGE_NAMES = {"<canonical>": "idiolect.characters.<key>.api", ...}
_ALIASES = {"<romaji>": "<canonical>", "<日文/简繁/常见误写>": "<canonical>", ...}
```

`registry` 是唯一分发点：调用方只走 `get_canon_profile` / `get_voice_manifest` / `render_turn_special_block` / `postprocess_reply`，不要按角色名堆 if/elif，也不要直接 import `idiolect.characters.<key>.*`。分发时 registry 会把名字归一化再往下传。

## 3. 场景接线

- 通用场景写在 `idiolect/general_scenes.py`，**顺序必须与 `idiolect/scene_classifier.py` 的 `_RULES` 里通用场景的相对顺序一致**（不变量：`test_layer_order_matches_classifier_order`）。
- 角色专属场景只在 `char` 命中时判；一轮最多注入 2 个块（`build_scene_blocks(max_blocks=2)`）。
- `SceneModule.tics` 只能填 `data/tic_by_scene.json` 里的显著项——凭感觉填的口癖会被门禁打回。

## 4. 两条文字红线（会被机械门禁查）

1. **不许有可整句照抄的例句**。注入正文里给正例台词，实测 22%~27% 的回复会逐字复述。只给「字数上限 + 句数 + 结构描述 + 口癖长度的起手（≤4 字）」；canon 原话写成「从你自己的档案里取」。门禁：`tests/test_scene_turn_logic.py::NoReusableExampleSentencesTests`、`tools/gates/_gen_scene_check.py`。
2. **角色可见文本里不许有元叙述**。「语料 / 实测 / 中位 / 基线 / 频次」这类词进了 prompt，模型会顺着谈自己的设定。门禁：`tools/gates/voice_meta_gate.py`（扫 canon / voice / style_target / turn_logic 四个面）。

## 5. 验收

```bash
py -X utf8 tools/gates/audit_role_packages.py     # 五包逐项对照：组件、API 契约，缺什么点名
py -X utf8 tools/gates/voice_meta_gate.py         # 元叙述
py -X utf8 tools/gates/_gen_scene_check.py        # 通用场景正文
py -X utf8 tools/gates/_tl_deep_check.py          # 深模块
py -X utf8 tools/offline_smoke.py                 # 总闸：装配/覆盖/触发矩阵/红线/门禁/单测/零写
py -X utf8 tools/gates/dump_prompt.py --all --matrix   # 20 份分层 dump，肉眼过一遍
```

改了 prompt 文本一定要留两臂证据：

```bash
py -X utf8 tools/gates/dump_prompt.py --all --matrix --phase before
# …改…
py -X utf8 tools/gates/dump_prompt.py --all --matrix --phase after
```

逐项确认：层顺序、块边界、触发只在该触发时发生、无关场景零漂移、预算未超。**注意 `--phase before` 会把深模块/通用场景的 env 回退开关全关**，它是 A/B 臂，不是「改动前快照」；比较改动前后要用同一个 phase 各跑一次。

## 6. 触发词纪律

触发词必须能拿出语料实证，否则就是凭感觉加规则：

```bash
py -X utf8 tools/distill/verify_triggers.py       # 每个触发词在语料里的可用性
```

语料里不存在的写法直接剔除（脚本会打印「可用 / 剔除」两列）。canon 里有的设定即使语料不覆盖也保留——语料是游戏活动剧情，日常道具天然缺席，不据此删 canon。

---

相关：[`docs/07-turn-logic-and-postprocessing.md`](../../../docs/07-turn-logic-and-postprocessing.md)（两个动态部件的搭建流程）｜[`docs/03-features.md`](../../../docs/03-features.md)（措辞规范与触发词纪律）
