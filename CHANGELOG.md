# 变更记录

版本策略见 [`docs/11-upgrade-guide.md`](docs/11-upgrade-guide.md) 第 3 节。

## v0.1.2（2026-10-14）

从「说得像」到「只说看得见的」：在风格轴旁边加入独立的 grounding 轴与评测有效性检查。运行时仍为零第三方依赖；四层装配输出与旧版逐字节一致（`report/upgrade_20261014/` 的前后 dump，本地产物）。

### 新增

- **证据合同** `idiolect/evidence_contract.py`（`evidence-context/v1`）：严格解析与校验（缺字段、未知字段、桶状态不符、重复/悬空引用、时间矛盾、可见性违规、私有路径、评估字段）；只渲染白名单元数据的安全渲染。
- **显式快照 adapter** `idiolect/adapters/`（`explicit-snapshot/v1`）：要求脱敏与权限声明，不推导时态，不可见记录只报 ID 与原因。
- **评测子包** `idiolect/evals/`：可预注册的任务 schema（11 类任务）、prompt 边界与回复两段 grounding 判定、风格轴逐条检查、双轴聚合与门禁（PASS / FAIL / INCONCLUSIVE）、人工标签与 judge 归因、实验登记与 manifest、批次可比性、family 级符号检验、离线 inspect 报告、显式付费 runner。
- **可选能力** `idiolect/capabilities.py`：`spatiotemporal`、`long-context-stress`（预注册 family 设计、确定性生成器、字符/字节计量、可选 tokenizer、family 配对分析）。
- **同链变异自测**：变异体与健康反控制走真实评测链；每次评测自带门禁金丝雀与表示算子认证。
- **内置数据** `idiolect/benchmarks/`：通用 opaque suite、仅语言 suite、五人同问题展示、长上下文计划、快照样例与合成回放（随 wheel 发布）。
- **统一 CLI**：`capabilities / contract / bench / eval / run / compare / report / selftest`。
- **工具**：`tools/gates/dump_workspace.py`（workspace / 证据路径的确定性 prompt dump）、`tools/gates/style_gate.py`（注释风格门禁）。
- **CI**：lint job（钉死版本的 ruff + style_gate）；wheel job 在仓库外的干净 venv 里 `--no-deps` 安装并跑四种模式、负对照与自测。
- **文档**：`docs/09-evidence-grounding.md`、`docs/10-long-context-stress.md`、`docs/11-upgrade-guide.md`；三语 README 重写。

### 变更

- `build_workspace_messages` / `ContextWorkspace.assemble` 新增可选参数 `trace`（不传时输出不变）。
- 证据块渲染：新增一行用法说明；历史条目带 `[as_of]`；provenance 只渲染白名单键（旧实现照抄全部键）。
- `EvidenceEnvelope` / `TemporalEvidenceContext` 迁到 `idiolect.evidence_contract`，`idiolect.workspace` 继续 re-export；无版本字典走兼容层并发 `DeprecationWarning`。
- `style_target.style_caps()`：说话尺度上限的唯一来源，prompt 与评分侧共用。
- `tools/gates/accept_check.py` 的精确检验迁到 `idiolect.evals.stats`（re-export，数值逐位一致）。
- `probe_runner` 的 metadata 升到 v2（`code`、`intervention`，新增 `--intervention`）；`report_html.py` 新增批次可比性判定。
- `offline_smoke.py` 新增「评测.内置合同」「评测.能力模式」「评测.同链变异自测」与 style_gate 门禁。

### 修复

- `tools/gates/oob_check.py` 的返回注解引用了未导入的 `Path`。
- 清理未使用的导入与局部变量（ruff F401 / F841），统一注释与 docstring 风格。

### 已知边界

- 内置回放全部是合成回复，只验证链路；仓库里还没有真实模型的 grounding 或长上下文批次。
- 长上下文内置矩阵只有 4 个 family，低于预注册下限，不支持模型结论。
- 机械匹配只认声明过的写法；中文数字读法与繁体字未认证。

## v0.1.0

首个公开版本：四层装配、五个角色包、蒸馏与探针工具链、风格轴评测与门禁、五人展示 Skill。
