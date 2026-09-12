# 语料获取与派生统计

## 1. 语料是什么

语料是五名角色的原作台词，一行一个 JSON 对象，落盘为 `{lang}.jsonl`（`lang` 取 `jp` 或 `cn`）。`tools/corpus/build_gold.py` 写出的每一行有七个字段：

- `character`：罗马字角色 key，`tomori` / `anon` / `rana` / `soyo` / `taki`
- `text`：一句台词
- `source`：首次出现的来源标签，`bestdori` 或 `hf`
- `also`：覆盖过这句文本的全部来源，排好序的列表
- `dir`：出处。bestdori 行是剧本目录，hf 行是 `event{event_id}`
- `lang`：`jp` 或 `cn`
- `split`：`train` 或 `holdout`

行里没有 scene 字段。场景由消费端派生：`tools/distill/validate_scenes.py` 的 `PROTOTYPES` 给 26 个场景各写一句原型，用句向量近邻把台词归到场景上；运行时场景由 `idiolect/scene_classifier.py` 判定。语料只记「谁说了什么、出自哪里」。

两条来源路径的用途不同：

- **Bestdori**（`tools/corpus/bd_api.py` + `crawl_bestdori.py`）。直接请求 `https://bestdori.com/api/explorer/{locale}/assets/_info.json` 一类的资产接口，抓 `.asset` JSON 剧本，不下载 mp3。取 `Base.talkData[]` 里的 `body`、`voices`、`talkCharacters`，只保留 `characterId` 属于 `{"36": "tomori", "37": "anon", "38": "rana", "39": "soyo", "40": "taki"}` 的行。抓取范围是 11 类剧本目录：`eventstory`、`actionset`、`band`、`birthdaystory`、`main`、`loginstory`、`area_opening_story`、`precedingstory`、`afterlivetalk`、`digeststory`、`backstagestory`（`crawl_bestdori.py` 的 `BUCKETS`，`effects` 明确排除）。`build_gold.py` 把 bestdori 排在前面合并，注释给的理由是它「覆盖更广、含 area/talkset」。这条路的代价是要打上千次接口，好处是能随官方更新重抓。
- **HuggingFace**（`tools/corpus/prep_hf_corpus.py`）。读 `KomeijiForce/BanG_Dream_Events` 的 parquet 快照，列是 `event_id` / `chapter` / `speaker` / `windowDisplayName` / `text`。真正的说话人在 `windowDisplayName`，`speaker` 列是占位符。`windowDisplayName` 含全角间隔号的多人口径整行丢弃，避免归属污染。它只有活动剧情，附带 `event_id` 与 `chapter` 结构，比 Bestdori 少一层抓取。

`prep_hf_corpus.py` 的输入路径是 `tools/raw/{lang}.parquet`（`RAW = HERE.parent / "raw"`），文件头注释说明它共用原项目已下载的 parquet。本仓库没有下载该数据集的脚本，要走这条路得自己准备 parquet 文件。

**为什么不分发。** `tools/_paths.py` 的文件头写明语料目录「不入库，需自己跑 `tools/corpus/` 生成」，`corpus_file()` 找不到文件时抛的 `FileNotFoundError` 也带着同样的说明。仓库只发 `data/` 下的聚合量。实测 `data/` 六个 JSON 里最长的字符串是 56 字，内容是 `style_profiles.json` 的 `note` 说明字段；`scene_char_baseline.json` 与 `scene_stats.json` 的原始产物本来带 `exemplars`（整句原台词），发布的那份已经剥离，130 个 `(角色, 场景)` 键里没有一个含 `exemplars`。两道检查盯着这条线：`tests/test_tooling_contracts.py::test_shipped_profiles_have_no_text` 断言画像里没有 `texts` / `examples` 字段，`tools/offline_smoke.py::check_data` 的「数据.无原作文本」项扫 `exemplars`。

## 2. 抓取与清洗链路

全部命令用 `py -X utf8`。

**第一步：抓 Bestdori。**

```powershell
py -X utf8 tools/corpus/crawl_bestdori.py --locales jp,cn --workers 8 --limit 0
```

- `--locales` 默认 `jp,cn`；`--workers` 默认 8，枚举目录清单时用 `max(4, workers)`；`--limit` 为 0 表示全量，大于 0 只抓前 N 个资产（冒烟用）。
- 目录清单缓存在 `tools/corpus/raw/bestdori/_listings_{locale}.json`，命中缓存就不再枚举。断点续跑记在 `_done_{locale}.jsonl`，重跑跳过已抓资产。
- 产物 `tools/corpus/raw/bestdori/{locale}.jsonl`，每行字段是 `character_id`、`voice_id`、`text`、`speaker`、`dir`、`file`。文件头 docstring 声称行里还有 `source`，实际 `bd_api.extract_lines` 不产这个字段，`source` 是 `build_gold.py` 自己打的标签。
- `extract_lines` 的两个细节：`body` 里的换行被替换掉再 strip；一条 `body` 挂多个 `voices` 时逐 voice 展开，`voices` 为空则回落到 `talkCharacters`，否则那行会整条丢失。

**第二步（可选）：整理 HF 语料。**

```powershell
py -X utf8 tools/corpus/prep_hf_corpus.py
```

对 `jp` / `cn` / `en` 三种语言各读一次 `tools/raw/{lang}.parquet`，缺文件就跳过。产物 `tools/corpus/raw/hf/{lang}.jsonl` 加 `_summary.json`，行字段 `character_id` / `character` / `text` / `source`（固定 `hf_eventstory`）/ `event_id` / `chapter` / `lang`。下一步合并时只用 `jp` 与 `cn`。

**第三步：合并成 gold。**

```powershell
py -X utf8 tools/corpus/build_gold.py
```

读上一步的两个目录，产出写在 `tools/_paths.py` 的 `CORPUS_DIR` 下（默认 `<repo>/raw/gold`，可用 `IDIOLECT_CORPUS_DIR` 改），文件是 `{lang}.jsonl` 与 `gold_stats.json`。合并顺序是 bestdori 先、hf 后，同语言内按 `(character, text)` 去重，重复行只把来源追加进 `also`，`source` 保留首次出现的那一个。跨语言不去重，同一句中文和日文各留一行。

**split 怎么切。** `build_gold.py` 的切分依据是文本哈希，与行号、抓取顺序无关：

```python
h = int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)
split = "holdout" if (h % 100) < HOLDOUT_RATIO * 100 else "train"   # HOLDOUT_RATIO = 0.2
```

哈希只吃 `text`，所以同一句台词在哪一行都是同一个 split；两个语言文件也各自独立判。比例常量是 0.2，即约 20% 的留出。`tools/_paths.py` 的格式注释写的是 `"train"|"test"`，与实际写入的 `holdout` 不一致，以代码为准。消费端目前只读 `train`：`scene_char_baseline.py`、`scene_stats.py`、`tic_profile.py`、`tic_by_scene.py`、`validate_scenes.py`、`export_profiles.py`、`probe_runner.py` 都显式过滤 `split == "train"`，全仓库没有任何脚本读取 `holdout`。

有一处例外要说清：`tools/distill/export_targets.py` 读语料时不过滤 split，所以它算出的 `n` 含留出行。`data/style_targets.json` 里 `cn.anon.n` 是 1579，`data/style_profiles.json` 里 `anon.n` 是 1244，两者差约 1.27 倍，来源就是这条口径差异。`idiolect/characters/taki/voice.py` 的注释里也记着「含 holdout 的旧口径」这个坑。

## 3. 质量审计

```powershell
py -X utf8 tools/corpus/audit_corpus_quality.py
```

`audit_corpus_quality.py` 读的是抓取层的原始文件（`raw/bestdori/{lang}.jsonl` 与 `raw/hf/{lang}.jsonl`），不读 gold。按语言、按角色输出一张表：原始行数、唯一文本数、重复率、含全角间隔号 `・` 的多人行数、两个来源各自的行数、唯一文本的中位字长；再算「来源重合」，即 bestdori 文本集合与 hf 文本集合的交集与覆盖率；最后打印最长的一行（截前 120 字）。结果写到 `REPORT/corpus_audit.md`，同时打到 stdout。

这些异常需要人工看：重复率高说明同一句被多个场景复用，不去重会把分布带偏；多人行占比高说明归属不可靠；来源重合高说明两条路径抓到了同一批活动剧情。脚本本身没有阈值也没有失败分支，`main()` 恒定 `return 0`，所以它拦不住任何流程。

真正会让后续步骤停下来的地方在别处：

- `tools/_paths.py::corpus_file()`：`CORPUS_DIR/{lang}.jsonl` 不存在时抛 `FileNotFoundError`，提示信息指向 `docs/02-corpus.md`（本文件）。
- `tools/probe/probe_runner.py`：既没有语料也没有 `data/style_profiles.json` 时打印提示并 `return 2`。
- `tools/distill/export_profiles.py --check`：文件缺失或画像与语料对不上时 `return 1`。
- `tools/distill/scene_char_baseline.py --min-n 12`：近邻条数不足的 `(角色, 场景)` 组合直接不产出。下游 `prompt_patch.py` 的 `targets_scene` 臂遇到缺失的 cell 会 `raise SystemExit`，不再静默退回全局值。- `tools/offline_smoke.py::check_data`：`style_targets.json`、`scene_char_baseline.json`、`scene_stats.json`、`tic_profile.json`、`tic_by_scene.json` 缺任何一个都判 FAIL。
- `tools/distill/validate_scenes.py` 的冗余判据（场景两两 Top-25 Jaccard > 0.6）与纯度判据（< 0.30）只写进 `report/scene_separation.md`，返回码仍是 0。

## 4. 派生统计清单

除 `export_profiles.py`（按 `--out` 或 `DATA/style_profiles.json` 落盘）与 `export_scene_targets.py`（生成 `idiolect/scene_length_targets.py`）之外，下面每个脚本都把结果写进 `REPORT`（默认 `report/`）。要复现 `data/`，用 `--out` 指定目标路径（`scene_char_baseline.py` / `scene_stats.py` 还要加 `--no-exemplars`），或把 `IDIOLECT_REPORT_DIR` 指到 `data/` 再跑（代价是各脚本的 `.md` 产物也会落进 `data/`）。

**`style_targets.json`**：`{"cn": {...}, "jp": {...}}`，每个角色一份全局数值目标。cn 侧 17 个字段：`name`、`n`、`median_chars`、`mean_chars`、`p90_chars`、`sent_per_turn`、`clause_per_turn`、`ellipsis_rate`、`exclaim_rate`、`question_rate`、`period_rate`、`comma_rate`、`dash_rate`、`first_person_rate`、`filler_rate`、`laugh_rate`、`top_interjections`；jp 侧多 `sent_final_per_turn` 与 `long_vowel_rate`（`style_features.style_targets`）。生成者是 `tools/distill/export_targets.py`。本仓库发布的这份**没有嵌套的场景格**（场景级目标在 `idiolect/scene_length_targets.py`），cn 每个角色就是上面那组标量。生成脚本**不过滤 split**，所以这里的 `n` 含留出行，与 `style_profiles.json` 的 train-only `n` 不同（cn.anon 1579 vs 1244），这是刻意的口径差异，理由写在脚本头部。消费方：`tools/probe/prompt_patch.py`（`TARGETS_PATH`）、`tools/probe/probe_runner.py`（经 `PP.load_targets("cn")` 传给补丁臂）、`tools/offline_smoke.py`。生产 prompt 不读这个文件：`idiolect/style_target.py` 里手抄了一份 `STYLE_TARGETS`，与 `data/style_targets.json` 的 cn 全局字段逐项对齐（中位、p90、句数、小句数相同，六个出现率是同一个数保留两位小数）；乐奈的 `top_interjections` 例外，生产版只留 `["嗯", "啊", "唔", "哦"]`，data 版是 6 个，多出 `ん`、`あ`。

**`scene_char_baseline.json`**：130 个键，形如 `灯|crisis`，5 个中文角色名 × 26 个场景。每格字段 `char`、`scene`、`n`、`length`、`n_sent`、`n_clause`、`punct_rate`、`first_person_rate`、`filler_rate`、`anchor_density`。生成者 `tools/distill/scene_char_baseline.py`：先按角色过滤 train 语料，再用 `BAAI/bge-small-zh-v1.5` 对 26 个场景原型各取 top-k 近邻（`--k` 默认 40），样本不足 `--min-n`（默认 12）的组合不产出。原始产物的每格还带 `exemplars`（前 8 条原句），发布版已剥离。消费方都在 `tools/score/`：`scene_distill.py`、`scene_ab_compare.py`、`_pool_arms.py`、`scene_feedback.py`，以及 `tools/distill/export_scene_targets.py` 与 `tools/offline_smoke.py`。

**`scene_stats.json`**：26 个场景 key，字段 `cn`、`char_side`、`watch`、`n_sampled`、`length`、`sent_per_turn`、`clause_per_turn`、`punct_rate`、`first_person_rate`、`filler_rate`、`char_dist`、`vocab`。与上一份的区别是它**跨角色**：全量 train 语料按原型检索 top-60（`--k` 默认 60，`--min-n` 默认 20），所以某场景的基线里混着别的角色的话。生成者 `tools/distill/scene_stats.py`，同时写 `report/scene_style_table.md`。原始产物的 `exemplars`（每场景 6 条原句）同样没进 `data/`。消费方是 `tools/probe/gen_probe_scenes.py`，但它读的是 `REPORT/scene_stats.json`（写夹具要拿 `exemplars`），只有 `data/` 那份时它跑不了；`offline_smoke` 对这份只检查存在与非空。

**`tic_profile.json`**：5 个中文角色名 → 口癖条目数组。条目字段 `tic`、`count`、`per_10k`、`line_share`、`start_share`、`endpoint`、`specificity`、`top_other`、`top_other_per_10k`。生成者 `tools/distill/tic_profile.py`，候选词表硬编码在代码里（带 ★ 的那些是 `voice.py` 里已写进去的 manifest 声称，用来做「声称 vs 实测」核对），`count < 3` 的候选不报，条目按 `specificity` 排序。条目数：灯 22、爱音 25、乐奈 24、素世 33、立希 21。消费方：`offline_smoke` 检查存在与角色数；生产代码只把它当证据注释引用（`idiolect/characters/rana/canon.py`、`rana/voice_check/thresholds.py`、`tests/test_scene_turn_logic.py` 的文件头），运行时没有读取点。

**`tic_by_scene.json`**：114 个键，形如 `灯|low_mood`，字段 `char`、`scene`、`k`、`tics`；`tics` 里的每条是 `tic`、`count`、`per_10k`、`base_per_10k`、`lift`。生成者 `tools/distill/tic_by_scene.py`：先按角色过滤 train 语料，再对 26 个原型各取 top-k 近邻（`--k` 默认 120），只报 cell 内出现 ≥ `--min-count`（默认 5）次且 `lift` ≥ `--min-lift`（默认 1.4）的口癖，`lift` 是该场景每万字频次比上该角色全局每万字频次。有 cell 的角色分布：乐奈 25、素世 25、爱音 23、立希 23、灯 18。消费方：`offline_smoke` 只要求文件存在，不解析；生产侧是注释级证据，`idiolect/scene_engine.py` 明确规定场景口癖必须来自这里的 `lift`，`soyo` / `rana` / `taki` 三个 `turn_logic/scenes.py` 引用了具体数值。

**`style_profiles.json`**：`lang`、`note` 加 5 个角色 key。每角色 19 个字段，覆盖长度（`length`、`length_core`、`max_sent_len`）、结构（`n_sent`、`n_clause`）、标点（`punct_density` 8 个标点各自的分布，`punct_rate` 10 个标点的出现率）、自称与他人称呼（`first_person_rate`、`first_person_per_turn`、`second_person_rate`、`address_suffix_rate`）、填充与笑声（`filler_per_turn`、`filler_rate`、`laugh_rate`）、日文相关（`sent_final_jp_per_turn`、`long_vowel_rate`）、语气词（`interjection_top`、`interjection_per_turn`）。生成者 `tools/distill/export_profiles.py`，唯一直接写 `DATA` 的脚本，只统计 `split == "train"` 的行。n 值：爱音 1244、立希 1113、素世 862、灯 757、乐奈 389。消费方：`tools/probe/probe_runner.py`（没有语料时用这份当 gold 画像算 fidelity；两份都没有时 `return 2`）、`tests/test_tooling_contracts.py`。文件头写了它存在的理由：`style_targets.json` 只有中位与 p90，够写 prompt，不够算分布分。

**发布形态怎么来。** `scene_char_baseline.json` 与 `scene_stats.json` 在发布前要剥掉例句字段，两个脚本各自带 `--no-exemplars`（外加 `--out`），所以这一步是可复现的命令，不是人工编辑。剥离后六个文件都能由语料逐字节重建，实测见下文「边界与限制」。

**写文件的守卫。** 语料路径存在但内容为空时，读侧由 `require_corpus()` 当场退出，写侧由零结果守卫拦下（`build_gold.py` 在没有源文件时拒绝写出，除非显式 `--force-empty`；`prep_hf_corpus.py` 与 `export_scene_targets.py` 同理）。加这两道的原因是：一次 `--help` 之类的误调用曾经把外部语料目录覆盖成 0 字节，而退出码是 0。

**`gold_stats.json`** 跟着语料走，由 `build_gold.py` 写在 `CORPUS_DIR` 里，字段是 `unique_total`、`per_character`、`per_split`、`coverage_both_sources`，按语言分。它不在 `data/` 下。

## 5. 落地操作

从零到 `data/` 齐备、探针能跑：

```powershell
# 1) 抓 Bestdori 剧本（首次要枚举目录清单，代码注释口径约 8600 次 API 调用）
py -X utf8 tools/corpus/crawl_bestdori.py --locales jp,cn --workers 8

# 2) 可选：把 HF parquet 整理成同一形态（需要先自备 tools/raw/{jp,cn,en}.parquet）
py -X utf8 tools/corpus/prep_hf_corpus.py

# 3) 合并 + 切分 → <repo>\raw\gold\{jp,cn}.jsonl 与 gold_stats.json
py -X utf8 tools/corpus/build_gold.py

# 4) 审计原始抓取层（只出报告，不拦流程）
py -X utf8 tools/corpus/audit_corpus_quality.py

# 5) 派生统计，产物默认落 report\
py -X utf8 tools/distill/export_targets.py
py -X utf8 tools/distill/tic_profile.py
py -X utf8 tools/distill/tic_by_scene.py
py -X utf8 tools/distill/scene_stats.py
py -X utf8 tools/distill/scene_char_baseline.py
py -X utf8 tools/distill/export_scene_targets.py
py -X utf8 tools/distill/export_profiles.py

# 6) 发布形态：剥掉例句字段再放进 data\（两个脚本自带 --no-exemplars）
py -X utf8 tools/distill/scene_char_baseline.py --no-exemplars --out data\scene_char_baseline.json
py -X utf8 tools/distill/scene_stats.py        --no-exemplars --out data\scene_stats.json

# 7) 校验
py -X utf8 tools/distill/export_profiles.py --check     # 只查 style_profiles.json，一致返回 0
py -X utf8 tools/offline_smoke.py --fast                # 含「数据.」五项形状检查

# 8) 探针：先 dry-run 验装配，不调模型
py -X utf8 tools/probe/probe_runner.py --label smoke --dry-run --assemble --turn-logic --registry --runs 1
# 实跑要 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL（默认模型名 deepseek-flash）
py -X utf8 tools/probe/probe_runner.py --label base --runs 6 --assemble --turn-logic --registry
```

语料已经在别处，不想重抓时用环境变量指过去，抓取与合并两步都可以跳过：

```powershell
$env:IDIOLECT_CORPUS_DIR = "D:\corpus\mygo-gold"      # 需含 cn.jsonl / jp.jsonl
py -X utf8 tools/distill/export_profiles.py
```

四个环境变量都由 `tools/_paths.py` 与 `tools/mock_clock.py` 读取：

- `IDIOLECT_CORPUS_DIR`：语料目录，默认 `<repo>/raw/gold`
- `IDIOLECT_REPORT_DIR`：产物目录，默认 `<repo>/report`
- `IDIOLECT_DATA_DIR`：派生统计目录，默认 `<repo>/data`
- `IDIOLECT_MOCK_NOW`：mock 时钟，默认 `2026-09-12T15:00:00+09:00`（周六下午）；填 `real` 关掉 pin，但那样产出的数字不可跨批次比较

`export_profiles.py --check` 的用途是语料换代后的口径校验：它按当前语料重算画像，与已发布的 `data/style_profiles.json` 逐角色比 `n`、`length`、`n_sent`、`punct_rate`、`first_person_rate` 五项，有差异就打印前 12 条并返回 1，提示重跑导出。它只守这五项，也不比对 `style_targets.json` 和 `scene_length_targets.py`。本次在无语料的机器上实测：它直接抛 `FileNotFoundError`（退出码 1），走不到那个「FAIL」分支。

探针还有两个前置条件：`fixtures/` 里那 5 份夹具是占位件，system 段为空，所以必须带 `--assemble`（否则模型收到空 system）；`--registry` 用 `probe_registry` 的 26 场景夹具，不带它则退回 `probe_scenarios` 的 v1 手写场景。

## 6. 边界与限制

**语料版本会改变所有数字。** Bestdori 会持续上新活动与卡面剧情，重抓得到的 `n` 与分布必然和已发布的那份不同；HF 那条路是固定快照，但本仓库没有下载脚本，快照从哪来由使用者决定。派生统计是某个时点的快照，不是可复现的常数。`--check` 只比对五个字段，其余字段漂移时仍会报一致。

**发布文件与生产 prompt 是两套东西。** 角色 prompt 里的长度与句数目标来自 `idiolect/style_target.py` 里手抄的 `STYLE_TARGETS`，命中场景时换成 `idiolect/scene_length_targets.py`（由 `export_scene_targets.py` 生成，`MIN_N = 20`，当前 130 格丢弃 0，文件 940 行）。重跑派生统计不会自动更新这两个文件；要让 prompt 跟着新语料走，得重新跑 `export_scene_targets.py` 并逐项核对 `STYLE_TARGETS`。生成物的目标路径已指向包内模块，重跑会原位更新 `idiolect/scene_length_targets.py`；这次用发布数据重跑，除文件头的三行来源说明外逐字节一致，数字完全可重建。

**发布数据的可重建性（2026-09-13 实测）。** 用金标准 cn 语料跑完上面第 5、6 步的六条命令，`data/` 下六个文件与仓库里的发布版本**逐字节相同**。为此修了两个确定性缺陷：`scene_stats.py` 的词表并列项按词兜底排序，`style_features.logodds_signature` 的 top-N 截断同样加兜底排序（它从 `set` 迭代取词，只按 logodds 排序时，同为 2.48 的两个词谁进榜会随进程的哈希随机化变化，同一份语料两次跑出的词表不同）。诊断类报告（`scene_discover`、`validate_scenes`、`scene_distill` 的排序）只保证内容一致，并列项的先后不保证。

**发布数据的可重建性（2026-09-13 实测）。** 用金标准 cn 语料跑完第 5、6 步的六条命令，`data/` 下六个文件与仓库里的发布版本**逐字节相同**。为此修了两个确定性缺陷：`scene_stats.py` 的词表并列项按词兜底排序，`style_features.logodds_signature` 的 top-N 截断同样加兜底排序（它从 `set` 迭代取词，只按 logodds 排序时，同为 2.48 的两个词谁进榜会随进程的字符串哈希随机化变化，同一份语料两次跑出的词表不同）。诊断类报告（`scene_discover`、`validate_scenes`、`scene_distill` 的排序）只保证内容一致，并列项的先后不保证。

**锚点口径在两处都不完整。** `scene_char_baseline.json` 每格带 `anchor_density`，由 `style_features.anchor_density(lines)` 算出；但 `profile_from_texts` 不产这个字段，`data/style_profiles.json` 里也就没有。`style_features.composite_score` 靠 `gold.get("anchor_density")` 定满分线，取不到就退回 `1.0`，而该函数在本仓库没有调用点（全仓库只有定义那一行）。实际在用的是 `tools/score/scene_distill.py`，它的注释写明 2026-09-12 把 anchor 移出了复合分，只留固定占位值 `1.8` 作诊断列，基线锚点另从 `scene_char_baseline.json` 取。

**以下脚本本次只读代码，没有在独立仓库里跑过，标注未验证：**

- `tools/corpus/crawl_bestdori.py`：需要访问 bestdori.com，未跑。它的文件头声称产出行含 `source`，与 `bd_api.extract_lines` 的实际字段不符。
- `tools/corpus/prep_hf_corpus.py`：需要 `tools/raw/{lang}.parquet`，仓库内无下载脚本，未跑。
- `tools/corpus/build_gold.py`、`tools/corpus/audit_corpus_quality.py`：本机没有 `raw/bestdori` 与 `raw/hf`，未跑，链路按代码读出。
- `tools/distill/scene_stats.py`、`scene_char_baseline.py`、`tic_by_scene.py`、`validate_scenes.py`：需要 `sentence_transformers`，首次还要下载 `BAAI/bge-small-zh-v1.5`，未跑。
- `tools/distill/export_targets.py`、`tic_profile.py`：需要语料，未跑。
- `tools/probe/prompt_patch.py` 的 `targets_scene` 臂：原先 `from scene_targets import ...` 引用了一个只存在于原项目的模块，在本仓库必然 ImportError，这条臂是死的。已改为读 `idiolect.scene_length_targets.get_scene_target`，并用 `build_scene_block` 渲染同一组字段；dry-run 实测该臂能给每格加上约 402 字符的场景块。臂的措辞是按元叙述门禁重写的，因此与历史批次**不可逐字节比较**。
- 探针实跑（真实调模型）未执行。本次只跑了 `py -X utf8 tools/offline_smoke.py --fast`，结果 PASS，其中「数据.长度目标覆盖」「数据.场景基线」「数据.场景统计」「数据.无原作文本」四项通过，场景基线报 130 键（5 角色 × 26 场景），`scene_stats` 26 场景、`tic_profile` 5 角色。

已验证的部分包括：`data/` 六个文件的字段与条数逐项读出（含 `scene_char_baseline.json` 无 `exemplars`、`tic_by_scene.json` 114 个 cell、`style_profiles.json` 19 个字段与各角色 n）；`export_profiles.py --check` 在缺语料时的实际行为；`idiolect/style_target.py` 与 `idiolect/scene_length_targets.py` 这两个生产消费点，以及与发布文件的数值比对。
