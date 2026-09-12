---
name: idiolect-corpus
description: "Build and validate your own character corpus for idiolect (the prompt-distillation repo) when you want to apply the method to characters other than the shipped MyGO!!!!! five. Use this skill whenever the user asks to add another character or another work, wants to point the pipeline at their own corpus, needs the raw/gold/{lang}.jsonl line schema, asks where the corpus comes from or why a corpus-dependent script refuses to run, or wants to re-derive everything from a fresh corpus. Covers the source options (Bestdori for BanG Dream!, a HuggingFace parquet snapshot, or your own chats/scripts), the exact seven per-line fields, the hash-based train/holdout split, the character-key decision and every table that must be updated to match, the quality audit, and the hard rule that the repository never ships corpus text."
---

# idiolect-corpus：把语料准备好

这一节只做一件事：产出一个**格式正确、可复现、不含在仓库里**的语料目录，让后面所有脚本都能跑。

前置：读 [`docs/02-corpus.md`](../../../docs/02-corpus.md)。那里是本主题的权威源，本 skill 是操作清单。

## 1. 先决定角色 key

仓库里所有工具都用**罗马字 key** 指角色（`anon` / `tomori` / `rana` / `soyo` / `taki`），中文名是 canonical 显示名。换作品时先定 key 表，例如 `{k1: 角色A, k2: 角色B}`，然后：

```bash
# 列出所有硬编码了这五个 key 的文件（换 key 时要一起改的清单）
git grep -l '"tomori"' -- tools idiolect
```

当前命中 28 个文件，其中必须改的是这些**表**：

| 位置 | 内容 |
|---|---|
| `idiolect/registry.py` | `_PACKAGE_NAMES`（canonical 名 → 包路径）+ `_ALIASES`（别名，**唯一一份名字表**） |
| `tools/corpus/*.py` | `CHARS` 列表：`build_gold` / `audit_corpus_quality` / `prep_hf_corpus` / `bd_api` |
| `tools/distill/*.py` | `CHARS` 或 `CHARKEY` 映射：`analyze_corpus` / `char_topic_vocab` / `export_profiles` / `export_targets` / `rules` / `scene_char_baseline` / `scene_discover` / `scene_stats` / `signal_strength` / `tic_by_scene` / `tic_profile` / `validate_scenes` / `verbal_tics` |
| `tools/probe/*.py` | `gen_probe_scenes` / `probe_runner` / `scene_coverage` |
| `tools/score/*.py` | `_copy_audit` / `_noun_initial` / `scene_feedback` |
| `tools/gates/*.py`、`tools/offline_smoke.py`、`idiolect/__main__.py` | 角色清单与自检 |
| `idiolect/general_scenes.py` | 每个角色的通用场景块表 |

一次性确认没有漏：

```bash
py -X utf8 tools/offline_smoke.py        # 「装配.四层齐全」「场景.长度目标覆盖」会直接点名缺谁
```

## 2. 产出语料文件

目标：`$IDIOLECT_CORPUS_DIR/{lang}.jsonl`（默认 `<repo>/raw/gold/`），**每行一个 JSON**：

| 字段 | 说明 |
|---|---|
| `character` | 第 1 步定的罗马字 key |
| `text` | 一句台词 |
| `source` | 首个来源标签，`bestdori` / `hf` / 你自己的标签 |
| `also` | 覆盖过这句文本的全部来源，排好序的列表 |
| `dir` | 出处（剧本目录 / `event{id}` / 你的来源名） |
| `lang` | `jp` / `cn` / … |
| `split` | `train` / `holdout` |

三条来路（详见 `docs/02-corpus.md`）：

- **BanG Dream!**：`tools/corpus/crawl_bestdori.py` 抓 bestdori 资产（要网络、上千次接口）。
- **HuggingFace 快照**：`tools/corpus/prep_hf_corpus.py`，需自备 `tools/raw/{lang}.parquet`（本仓库不附带数据集副本）。
- **你自己的来源**：任何能产出上面七个字段的东西——游戏导出、字幕、聊天记录都行。写个脚本落到 `tools/corpus/raw/<你的来源>/{lang}.jsonl`，再让 `build_gold.py` 合并。

切分规则（`build_gold.py`）：`sha256(text)[:8] % 100 < 20` → `holdout`，其余 `train`。哈希只吃 `text`，所以同一句在哪一行都是同一个 split。

```bash
py -X utf8 tools/corpus/build_gold.py                    # 合并 + 切分 → {lang}.jsonl + gold_stats.json
py -X utf8 tools/corpus/build_gold.py --dry-run           # 只看会写什么
py -X utf8 tools/corpus/audit_corpus_quality.py           # 质检表（重复率 / 多人行 / 来源重合）
```

## 3. 验收

- `gold_stats.json` 里每个语言的**行数与切分数**都是非零；`build_gold.py` 在 0 行时**拒绝写出**（除非显式 `--force-empty`）。
- `audit_corpus_quality.py` 的表里：重复率、含全角间隔号 `・` 的多人行、来源重合都看过一遍；它没有阈值、恒 `return 0`，**拦不住流程，得人看**。
- 缺语料时任何下游脚本都该给一行 `[stop] …` 而不是 traceback（`tools/_paths.py::require_corpus`）。自己新写的脚本也要接它。

## 4. 红线

**语料不入库。** `.gitignore` 已经排除 `raw/` 与 `*.jsonl`；`data/` 只能放聚合统计。发布前跑 `offline_smoke.py` 的「数据.无原作文本」项。自己抓语料要遵守来源站点条款与当地法律。

---

相关：[`docs/02-corpus.md`](../../../docs/02-corpus.md)（权威细节）｜[`docs/06-lessons.md`](../../../docs/06-lessons.md) 的 A 组（统计口径的坑）
