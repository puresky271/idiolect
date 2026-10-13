# 参与贡献

感谢你愿意改进 idiolect。这份指南说明：动手之前要知道的红线、提交之前必须过的检查、改 prompt 与评测代码的纪律、风格约定，以及版本发布流程。

> English summary at the end. 文档与代码注释以简体中文为准。

**目录**：[开始之前](#开始之前) ｜ [准备环境](#准备环境) ｜ [提交前必须通过](#提交前必须通过) ｜ [改 prompt 的纪律](#改-prompt-的纪律) ｜ [改评测代码的纪律](#改评测代码的纪律) ｜ [代码与注释风格](#代码与注释风格) ｜ [数据、隐私与权利红线](#数据隐私与权利红线) ｜ [文档纪律](#文档纪律) ｜ [分支、提交与 PR](#分支提交与-pr) ｜ [发布流程](#发布流程) ｜ [报告问题](#报告问题) ｜ [English summary](#english-summary)

## 开始之前

- 先读 [`AGENTS.md`](AGENTS.md)（仓库实际结构与约定）与 [`docs/README.md`](docs/README.md)（按目的挑阅读路径）。改动越靠近 prompt 或评测，越要先读 [`docs/06-lessons.md`](docs/06-lessons.md)：大多数约束都是被事故教出来的。
- idiolect 是**角色语言与文本回答的评测、受控上下文装配工具**。它不是世界模拟器、记忆数据库或多模态获取引擎；超出这个边界的功能（读宿主数据库、推进世界状态、图像识别、地理投影）请不要往这里加，它们属于上游。
- 较大的改动（新的评测能力、合同新版本、改变默认渲染或公共 API）请先开 issue 说明动机与方案，避免白做。

## 准备环境

需要 Python 3.11+。Windows 上一律用 `py -X utf8`（裸 `python`、`pip`、`ruff` 可能解析到没装依赖的解释器或别的环境）；macOS / Linux 把下文的 `py -X utf8` 换成 `python3 -X utf8`。所有命令在仓库根目录执行。

```bash
py -X utf8 bootstrap.py                     # 建 .venv、装依赖、跑自检、打印一份 prompt
py -X utf8 -m pip install -r requirements.txt
py -X utf8 -m pip install -e ".[lint]"      # 钉死版本的 ruff，与 CI 一致
```

不需要语料、不需要密钥就能完成绝大多数开发与全部离线检查。只有重算 `data/` 或跑真实探针时才需要 `IDIOLECT_CORPUS_DIR` 或 `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL`。

## 提交前必须通过

```bash
py -X utf8 tools/offline_smoke.py           # 总闸：装配、红线、数据、评测合同、四种能力模式、同链自测、门禁、单测、零写校验
py -X utf8 -m pytest tests/                 # 单测（smoke 也会跑；单独跑便于看细节）
py -X utf8 -m ruff check .                  # 代码风格：pyflakes + 机械格式
py -X utf8 tools/gates/style_gate.py        # 注释风格：中文 docstring / 注释格式 / 繁体字 / 纯英文注释
```

改动小的时候可以先用 `py -X utf8 tools/offline_smoke.py --fast` 快速确认，但提交前跑全套。CI（`.github/workflows/ci.yml`）会再跑一遍：Ubuntu 3.11–3.13 与 Windows 3.12 的 smoke 矩阵、wheel 包数据与仓库外干净环境的 `--no-deps` 安装验收、lint。**CI 不绿不合并。**

`offline_smoke` 自带零写校验：除了 `report/`，任何仓库文件被改动都会 FAIL。脚本产物一律写 `report/`（可用 `IDIOLECT_REPORT_DIR` 改）。

## 改 prompt 的纪律

凡是会改变最终 prompt 的改动（角色包、场景模块、说话尺度、装配、workspace、证据渲染），都要留前后证据，而且**基线必须在动手之前生成**：

```powershell
$env:IDIOLECT_REPORT_DIR = "report/<改动名>/before"
py -X utf8 tools/gates/dump_prompt.py --all --matrix --phase current
py -X utf8 tools/gates/dump_workspace.py --contract
# 修改代码后，保持相同的输入、时钟与开关
$env:IDIOLECT_REPORT_DIR = "report/<改动名>/after"
py -X utf8 tools/gates/dump_prompt.py --all --matrix --phase current
py -X utf8 tools/gates/dump_workspace.py --contract
Remove-Item Env:\IDIOLECT_REPORT_DIR
```

- `--phase before/after` 是开关消融，不能代替代码前后对比；代码对比用 `--phase current`。
- 审 diff 时逐项确认：层顺序、块边界、触发只在该触发的场景发生、无关场景零漂移、预算未超、执行包位置；`dump_workspace.py` 的 `legacy.*` 用例必须零漂移。
- 在 PR 描述里写明 diff 结论（哪些产物一致、哪些有意改变、为什么）。
- 角色可见文本里不许有元叙述（「语料」「中位」「基线」……），不许有能整句照抄的例句；`voice_meta_gate.py` 与 smoke 的红线扫描会抓。
- 触发词必须有语料实证（`tools/distill/verify_triggers.py`）；访问角色包只走 `idiolect/registry.py`。

## 改评测代码的纪律

- **先写有行为价值的契约测试，再改实现**。测试要能在缺陷存在时失败，不要只是复述实现。
- **评估侧与模型侧隔离**：评测任务的 `expect` / `oracle`（期望、隐藏值、gold）永远不进 messages；证据合同只渲染白名单元数据。
- **不把缺测当通过**：新评分部件必须给出 applicability、status、reason、分子分母与 scorer 版本；空回复、报错、干跑占位绝不能判 `pass`；判不了就给 `needs_review`。
- **新任务类型或新能力**：在 `idiolect/capabilities.py` 登记（版本、输入合同、适用任务、scorer、fixture、依赖、覆盖与不覆盖），并至少加一个会被抓到的变异体与一个健康反控制（`idiolect/evals/mutants.py`）。`py -X utf8 -m idiolect selftest` 必须保持零存活、零误报。
- **不从被测回复反推 gold**：期望由任务作者先于回复写定（`label_source.independent_of_responses`）。
- **合成不等于实证**：内置回放与干跑只能验证链路；声称模型改善需要 manifest 判定可比、family 数达到预注册下限的真实批次。
- **合同演进**：字段语义变化或新增必填字段要升合同版本号，解析器对不认识的版本拒收；改了内置 suite 要确认对应回放仍然成立后再重录（回放登记了 suite 指纹，过期会被测试抓到）。
- **评测时钟**：读「现在」的代码从 `tools/mock_clock.py` 的 `mock_now()` 取（包内评测读同一个 `IDIOLECT_MOCK_NOW`），不要直接 `datetime.now()`。
- **付费调用**：不要在测试或 CI 里调真实模型；需要时用 `idiolect run --dry-run` 先看估算，再由维护者显式 `--yes --max-calls N`。

## 代码与注释风格

- 注释、docstring 与文档用**简体中文**。模块 docstring 先写「这是什么、为什么」；`idiolect/` 运行时包（角色包正文除外）的公开类与公开函数要有中文 docstring。
- 注释以 `# ` 开头；不写繁体专用字；不写纯英文的说明性注释（`noqa` / `type:` 之类的工具指令除外）。以上由 `tools/gates/style_gate.py` 检查。
- ruff 规则集见 `pyproject.toml` 的 `[tool.ruff.lint]`：正确性与机械格式，行宽 120。`idiolect/characters/**` 的 prompt 正文长行豁免——重排中文注入正文有 prompt 漂移风险。不要用 `# noqa` 掩盖真问题；确实需要时写明理由（例如「registry 经 getattr 取用的公开入口」）。
- 运行时包保持**零第三方依赖**；工具链依赖放 `requirements.txt` 或 extras。
- 路径只从 `tools/_paths.py` 取；写文件的脚本要有零结果守卫；读语料的脚本对空文件直接退出；会碰外部数据目录的脚本必须带 argparse（`--help` 不能动手）。
- 跟随周围代码的命名、注释密度与写法；小步提交，不要顺手大面积重排无关代码（导入排序、风格改写会在 prompt 模块里制造无关 diff）。

## 数据、隐私与权利红线

- **不分发原作文本**：`data/` 只能是聚合统计；基线文件发布前剥掉例句（`--no-exemplars`）。语料（`raw/`、`*.jsonl`）不入库。
- **不提交密钥与真实对话**：密钥只从环境变量、`.env` 或 `.streamlit/secrets.toml` 读取，三者都已被 `.gitignore` 排除；评测任务与回放必须是合成、脱敏的（用 `actor_a` / `scene_02` / `evidence_17` 这类 opaque ID）。
- **宿主数据只经显式快照**：不要加任何自动打开宿主数据库、记忆账本、聊天历史的代码；快照必须声明已脱敏与权限。
- 角色与作品的权利属于 Bushiroad / Craft Egg 及相关权利方（见 [`NOTICE.md`](NOTICE.md)）；不要提交官方素材、台词、歌词或音频。

## 文档纪律

- 新增、移动或删除 `docs/` 下的文件，同步改 [`docs/README.md`](docs/README.md) 的索引，并在 `AGENTS.md` 的文档清单里登记。
- 文档里不要固化 pytest 项数（smoke 会检查）；数字以现场运行结果为准。
- 三语 README（`README.md` / `README.en.md` / `README.ja.md`）要同步：开头段保持原样；三份文件里的数字记号必须完全一致，字数表与 `layer_sizes` 实测对账，历史探针表的标注与指标命名有专门测试（`tests/test_eval_gates.py`、smoke 的「文档.README 字数表」）。只改一种语言会让检查变红。
- 面向用户的变化写进 [`CHANGELOG.md`](CHANGELOG.md)；影响兼容性的写进 [`docs/11-upgrade-guide.md`](docs/11-upgrade-guide.md) 的兼容性一览。

## 分支、提交与 PR

- 从最新的 `main` 拉分支：`feat/…`、`fix/…`、`docs/…`、`release/vX.Y.Z`。不要直接推 `main`。
- 提交信息沿用仓库现有格式：`类型(范围): 一句话`，例如 `feat(evals): …`、`fix(gates): …`、`docs(readme): …`；正文用中文写清「为什么」。
- PR 描述至少包括：
  - 改了什么、为什么；
  - 本地跑过的检查与结果（smoke、pytest、ruff、style_gate）；
  - 改 prompt 时的前后 dump 结论；
  - 改评测时的 selftest 结果与新增的变异体 / 反控制；
  - 已知边界与没做的部分。
- 一个 PR 只做一件事；纯重排与功能改动分开提。

## 发布流程

1. 在 `release/vX.Y.Z` 分支上：改 `idiolect/__init__.py` 的 `__version__`，补 `CHANGELOG.md`，必要时更新 `docs/11-upgrade-guide.md`。
2. 本地跑全套检查；构建 wheel 与 sdist，在仓库之外的干净 venv 里 `--no-deps` 安装后跑 `idiolect selftest` 与离线评测。
3. 开 PR，CI 全绿后合并。
4. 从**合并后的 `main` 提交**重新构建 wheel 与 sdist 并验收，再打带注释的 tag `vX.Y.Z`、创建 GitHub Release，附上两个文件与 SHA-256。

## 报告问题

- Bug：请附上命令、完整输出、idiolect 版本（`py -X utf8 -c "import idiolect; print(idiolect.__version__)"`）、操作系统与 Python 版本、是否设置了 `IDIOLECT_MOCK_NOW`；评测相关的请附上 `report/experiments/<实验>/manifest.json`（它不含密钥）。
- 安全问题（例如合同或 adapter 放行了不该进入 prompt 的数据）：请不要在公开 issue 里贴可复现的利用细节，先通过仓库维护者的私信或 GitHub 的私密安全报告渠道联系。

## English summary

- Read `AGENTS.md` first. idiolect evaluates and assembles text for character replies; it is not a world simulator, memory store, or multimodal ingestion engine.
- Before every PR, run `py -X utf8 tools/offline_smoke.py`, `py -X utf8 -m pytest tests/`, `py -X utf8 -m ruff check .` (install with `py -X utf8 -m pip install -e ".[lint]"`; on macOS/Linux use `python3 -X utf8` instead of `py -X utf8`) and `py -X utf8 tools/gates/style_gate.py`. CI must be green.
- Any change that can alter the final prompt needs before/after dumps (`tools/gates/dump_prompt.py --all --matrix --phase current` and `tools/gates/dump_workspace.py --contract`), with the baseline generated before editing.
- Evaluation code: write contract tests first; evaluator-only expectations never enter model messages; missing, empty, error, and dry-run results never count as a pass; new capabilities need a registry entry plus at least one mutant and one healthy control, and `py -X utf8 -m idiolect selftest` must stay clean.
- Comments and docstrings are written in Simplified Chinese; the runtime package keeps zero third-party dependencies.
- Never commit original script text, secrets, or real user conversations. Host data enters only through redacted, permission-declared explicit snapshots.
- Keep the three READMEs in sync (number tokens must match exactly), and update `CHANGELOG.md` for user-facing changes.
