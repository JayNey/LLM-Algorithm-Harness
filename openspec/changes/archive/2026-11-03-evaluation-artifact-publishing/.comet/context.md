# Comet Design Handoff

- Change: evaluation-artifact-publishing
- Phase: design
- Mode: compact
- Context hash: 724a20ee5837caeee3b3bc63c5fd6d61faf714f0b28b648dd66bf26ea8e9871f

Generated-by: comet-handoff.sh
Task hash policy: task-content-v1. Read tasks.md for live completion; excerpts are design-time context.

OpenSpec remains the canonical capability spec. This handoff is a deterministic, source-traceable context pack, not an agent-authored summary.

## openspec/changes/evaluation-artifact-publishing/proposal.md

- Source: openspec/changes/evaluation-artifact-publishing/proposal.md
- Lines: 1-28
- SHA256: f7bd4d77ec1103b578fe1c692c615c228336f39ea260a3557148d1a9289347a4

```md
## Why

#319：文件服务已支持 publish_results 和多格式导出，但真实评估 Worker 没有发布产物；数据库有结果时文件下载仍可能返回 Result not available。需要把真实执行、持久化、发布与下载接通，并让发布失败可单独恢复。

## What Changes

- 在真实评估结果提交边界持久化待发布记录，明确部分/完成/暂停/失败/取消的完整性语义。
- 按实际账号和已注册 evaluation_id 发布，不混用本地检查点 eval-{id} 或即时报告 run_id。
- 发布记录保存版本与状态；发布过程校验最新版本，防止重复、重试和旧执行回调覆盖较新文件。
- 提供归属校验的发布状态与独立重试能力，失败不丢失已提交结果、不把文件失败改写成模型执行失败。
- 保持既有 JSON、CSV、Markdown、HTML、PNG、ZIP 导出，以及脱敏、完整性、配额、保留期和删除清理；不伪造缺失的度量。
- 通过真实 Worker 编排到 HTTP 下载的集成链和并发/失败回归验证。

## Capabilities

### New Capabilities

- `api/evaluation-artifacts`：真实评估文件发布、版本控制、发布状态、独立重试与完整性说明。

### Modified Capabilities

无。

## Impact

涉及 src/tasks/evaluation.py、发布服务、业务数据库模型和迁移、FileService/FileStore、受认证发布状态/重试路由、文档及测试。沿用已合并 P5/P8 的预算和执行元数据，不改变其统计口径；即时 /reports 接口和 #299 前端独立保持可用。独立于 #322，单独 PR；基线 main@8a6ab918c3f70e38e9c00d4251f9d4343da98120。

非目标：引入新存储产品、重做评估调度、补造历史缺失执行结果、扩展下载 UI 或通知功能。设计需明确跨业务库/文件 SQLite 的提交顺序、部分结果发布点、崩溃后的重试与旧版本文件回收。核心验收包括自动发布下载、多格式可解析、过期回调保护、失败可重试、账号隔离及删除清理。

```

## openspec/changes/evaluation-artifact-publishing/design.md

- Source: openspec/changes/evaluation-artifact-publishing/design.md
- Lines: 1-87
- SHA256: 1eb78f32be336414cd702f68737eafc3dde0a86b34bb09fb1541be9759a97dfe

[TRUNCATED]

```md
---
comet_change: evaluation-artifact-publishing
role: technical-design
canonical_spec: openspec
---

## Context

动机见 proposal.md。文件元数据在认证共享 SQLite，Evaluation/EvaluationResult/AsyncTask 在业务数据库；后者部署可用 PostgreSQL，不能假设两库有共同事务。创建评估时文件服务注册 evaluation_id；Worker 的 eval-{evaluation_id} 仅是本地检查点 ID，Evaluation.run_id 是即时报告查询标识，三者不混用。

Worker 已在单元完成后提交数据库结果，持有带 celery_task_id 的执行代际锁，并保留 P8 的执行元数据。EvaluationResult 当前只存度量子集，无法从历史行完整恢复原始 ExecutionResult。FileService 的既有 publish_results 只接受旧策略字典，文件激活没有发布版本。

本文是用户已确认的唯一正式技术设计；采用持久化发布记录、版本检查和独立重试方案。

## Goals / Non-Goals

Goals：正常 Worker 自动发布实际结果；结果提交、发布、失败、重试可核对；新版本不能被旧回调覆盖；文件操作失败不撤销已提交执行结果。

Non-Goals：改写即时报告或前端下载 UI、重跑模型补文件、引入对象存储/新队列产品、伪造历史执行内容、改变 P5/P8 的费用和元数据语义。

## Decisions

### 1. Approaches

用户选择 A：业务库持久化发布快照与版本，提交结果后独立发布文件，激活前检查版本；失败由独立发布任务或归属校验的重试入口恢复。重试消费数据库快照，不依赖 Worker 本地目录，也不调用模型。

方案 B 是仅在 Worker 返回前直接调用旧 publish_results：代码较少，但无法覆盖提交后崩溃、独立重试和旧结果覆盖新结果；不采用。方案 C 是外部消息流/对象存储体系，本仓库规模下不必要，不采用。

### 2. 持久化边界与快照

新增业务表 evaluation_artifact_publications，每个评估一条当前发布记录，evaluation_id 主键及 CASCADE 外键，保存 user_id、单调 revision、snapshot JSON、status（pending/published/failed）、published_revision、error_code、attempts 和时间。EvaluationResult 新增 nullable execution_payload JSON，用于新单元原始执行结果的安全持久化；旧行保持 null，不回填默认执行数据。迁移沿现有 Alembic head，兼容 SQLite/PostgreSQL，提供降级。

单元结果、原始 execution_payload、计数和最新发布快照在同一业务事务提交。先按已有顺序锁 AsyncTask/Evaluation，再写发布记录；只有当前执行代际可更新。快照由本事务可见的已持久化 EvaluationResult 生成，包含实际行状态、metrics、error_message 与可空原始 execution；原始内容先脱敏，不持久化凭证。状态变化时即使没有新增单元也更新快照，以记录最终生命周期和完整性。API 暂停/取消/恢复与 TaskManager 的状态提交在同一事务暂存快照，提交后投递独立发布；即使 revoke(terminate=True) 使 Worker 无法运行 finally，已提交部分结果仍可自动发布。无 AsyncTask 的历史取消同样处理。无任何结果时仅记录 unavailable 原因，不发布空的成功文件。

快照内容与上次相同不提升 revision；内容/生命周期/完整性变化则提升。终态消息重复投递只能请求重试已有快照，不能重新执行或覆盖结果。旧代际回调既不能创建新发布版本，也不能改变新版本失败状态。取消、暂停和异常退出以数据库真实状态收尾，保留已提交部分结果；运行线程未确认的结果不宣称已发布。

### 3. 文件内容与兼容性

真实 Worker 发布一个版本化 JSON 文档：schema_version、evaluation_id、run_id（可空）、revision、state、complete、expected_units、recorded_units，以及按策略分组的结果。每条结果保留 problem_id、strategy、status、metrics、error_message、execution（真实原始内容或 null）。complete 仅在评估 completed 且实际记录覆盖全部预期单元时为 true；paused/failed/cancelled/running 均为部分结果，并如实标明缺失数量及原因。

既有 publish_results 的旧策略字典和手工/历史文件继续可读。新发布路径和渲染器识别版本化文档，不用构造默认 ExecutionResult 填补缺失度量。JSON/Markdown/HTML 保留完整性清单和实际结果；CSV 提供实际行字段，缺值留空并附版本/完整性列；PNG 明确部分结果标题，成功比例基于实际记录单元；ZIP 包含 JSON 清单和其余既有格式。源数据中的 P8 元数据与未知费用标记保留。下载入口仍为 /results/{evaluation_id}/download、export、charts；即时 /reports/* 不改变。

HTTP 下载先验证并读取同一不可变文件快照，再核对当前版本与删除标记；响应头和渲染内容均源于该快照，若读取期间版本发生变化则明确拒绝而不混用。HTTP 下载增加可核对且经 CORS 暴露的发布版本与完整性响应头，不把部分结果称为完整结果；GET 发布状态提供同一信息。完全没有结果返回明确不可用；已产生新 revision 但当前文件尚未发布时不把上一版当作当前成功文件，可返回明确的未就绪错误，调用者能查询/重试。失效、被删除或过期文件不能因为旧状态为 published 就宣称可下载。

### 4. 发布、版本和文件回收

业务事务提交后调用发布器；发布器先从持久化快照生成并暂存不可变文件，持久化文件元数据后才准备激活。最终激活前按同一锁顺序重新锁业务实体/发布记录，核对 owner、当前 revision、删除状态；核对失败放弃候选文件。锁内只做有界版本验证、FileStore 原子激活和发布确认，不做渲染。

FileStore 注册记录兼容增加已激活 revision、文件摘要和实际结果内容摘要；删除标记保留真实结果摘要，单纯状态/代际变化形成的新 revision 不能重新发布已删的相同结果，只有真实结果内容变化才可发布新产物。SQLite BEGIN IMMEDIATE 保证文件指针/版本原子更新；较低版本拒绝，重复相同版本相同摘要幂等返回，重复同版本不同摘要拒绝。最终业务确认和文件激活分属两库：若文件激活后业务提交前崩溃，重试通过 revision+摘要识别已激活文件，再完成确认，不重新创建有效副本。若新版本已激活，旧发布即使晚返回也不能替换它。

文件层仅将完整写入且校验成功的候选文件激活，失败不覆盖当前可读文件。候选写入、登记或激活失败时清理候选或标记可回收；旧版本、过期或删除文件沿用清理机制。候选登记前先检查幂等及回收可清理候选，配额按新旧文件实际并存占用计算，不给予隐含替换额度；仍不足时记录 storage_limit/413，保留旧文件，用户释放空间后可重试。失败候选不得永久耗尽配额。旧有效版本可在新发布期间保留供恢复核对，但不得冒充最新版本下载。

### 5. 独立重试与可观察性

新增 GET /api/v1/results/{evaluation_id}/publication，返回 revision、published_revision、status、available、complete、recorded_units、expected_units、attempts、最近错误分类和时间；未发布、无结果、文件过期与发布失败均可区分。错误不包含原始路径、凭证或不受控异常文本。

新增 POST /api/v1/results/{evaluation_id}/publication/retry，只对当前所有者注册且未删除的评估操作；只发送/执行独立发布任务，绝不启动评估。已发布且当前文件有效时幂等返回状态；无结果明确拒绝；排队/处理中重复请求不产生重复激活。端点继续使用 Cookie/CSRF/统一错误规范。独立任务支持有上限的退避重试；发布者不订阅结果后端，连接/套接字读取有明确超时且无连接重试，队列失败记录失败状态而非伪造已排队成功。失败回写或将版本置 pending 前，在业务锁内重新核对当前有效文件，不降级并发成功。

历史评估若有数据库结果但没有 publication 记录，仅在所有者显式 retry 时从现有结果建立快照，execution 保持 null；不在迁移或普通查询时自动全量回填，不通过终态 Worker 重投递重跑模型。历史完整性按真实行覆盖数和状态计算，另保留 execution_payload_available=false 的原始字段缺失说明。

Worker 正常路径在结果和最终状态提交后触发发布，失败不把 Evaluation/AsyncTask 的终态改成 failed。进程在提交快照后退出但尚未派发时，pending 记录仍可通过状态查询和独立重试恢复；本次不承诺无需部署调度器的无限自动扫描。恢复评估产生新 revision，旧重试自动失效。发布错误写结构化日志及持久化错误码。

### 6. 删除与账号隔离

状态/重试同时检查业务所有权及文件注册归属，未知资源和跨账号访问按既有 404 隐藏存在性。发布器不得根据任务参数自注册他人/不存在 run。删除评估沿既有锁与回调使文件不可读，级联删除发布记录；延迟消息发现源记录或注册已删除即终止，不能复活。

保留现有结果文件 expires_at=null、直至主动删除的保留策略，不把上传文件的 24 小时 TTL 套到结果；未激活候选则有可清理期限。单独删除当前产物时按 revision 保留删除标记，即使文件对象已被 cleanup 移除，同 revision 的自动重投递和显式 retry 也拒绝（artifact_deleted）；未来真实新结果的新 revision 可发布新文件，但不恢复已删文件对象。评估级删除禁止所有后续版本。

若导入的旧元数据或未来保留策略造成源文件过期，状态 available=false，自动重投递不延长其寿命；仅所有者显式 retry 可从持久快照新建一个文件，沿现有结果文件保留策略处理，旧文件 expiry 不改写。以上历史、删除及配额策略为实现者明确提出的默认取舍，纳入本次正式设计审阅。

## Risks / Trade-offs

- 两库不具分布式事务：采用持久快照、单调 revision、内容摘要和幂等激活，覆盖两次提交之间崩溃。
- 文件渲染耗时与锁竞争：在锁外渲染/暂存，锁内核对当前版本后激活；所有路径遵循相同业务锁顺序。
- 旧结果缺少原始 execution：保留 null/实际度量；历史缺失不补造代码、token、迭代或计时。
- 大运行原始结果占库空间：只保存当前发布快照，不为每次进度保留全量历史副本，遵守既有结果数量/文件尺寸/用户配额限制；部分更新仅在真实已提交结果和生命周期变化时发生。
- 队列或进程故障：持久 pending/failed 可查询且可独立重试，避免模型重复消耗。

## Validation


```

Full source: openspec/changes/evaluation-artifact-publishing/design.md

## openspec/changes/evaluation-artifact-publishing/tasks.md

- Source: openspec/changes/evaluation-artifact-publishing/tasks.md
- Lines: 1-16
- SHA256: 7fc84d60431a36e726daacc34d48728ecf45770fa36119d89fd246aed97dab97

```md
## 1. 持久发布合同

- [ ] 1.1 添加原始执行载荷与当前发布记录的兼容模型/迁移；验证旧数据库升级/降级、新旧结果空值语义和 PostgreSQL 离线 SQL。 <!-- comet-task:714ee1d7-5776-4573-b4d1-d28107985c61 -->
- [ ] 1.2 实现真实结果快照、完整性计算和单调版本分配；以测试验证快照与已提交行一致、未知字段不补造、重复内容幂等和旧代际拒绝。 <!-- comet-task:920bbb87-dd55-40df-aba1-54382c5c9de9 -->

## 2. 文件发布与恢复

- [ ] 2.1 扩展文件版本/摘要和候选激活流程；故障与竞争测试验证旧版本拒绝、同版本幂等、激活后确认前崩溃恢复及配额/候选清理。 <!-- comet-task:7ebc2395-4101-43ff-a5cb-ad7a115ecbc2 -->
- [ ] 2.2 接入 Worker 单元/生命周期持久化边界与独立发布任务；真实编排测试覆盖完成、暂停/恢复、失败/取消、提交后退出，确认发布失败不改变执行真值。 <!-- comet-task:32792741-abaf-4cd8-8676-f356f7f39e5d -->
- [ ] 2.3 实现认证的发布状态/独立重试和安全错误分类；HTTP 测试验证归属、CSRF、无结果、重复请求、队列失败、文件过期和重试不增加模型调用。 <!-- comet-task:6d8967f8-a8b7-4632-ad3a-b762cd61bbdf -->
- [ ] 2.4 兼容版本化产物的多格式下载与完整性元数据；解析 JSON/CSV/Markdown/HTML/PNG/ZIP，验证执行原始字段、P8 元数据、未知费用及旧格式回归。 <!-- comet-task:4c7c62cb-c182-457f-8bb1-df8e2bad5d4a -->

## 3. 综合验收与交付

- [ ] 3.1 完成 Worker → 发布 → HTTP 下载的完整集成链、跨账号/删除/延迟消息/清理回归、定向测试及格式类型编码检查；更新 API 文档并提交可复跑验证报告。 <!-- comet-task:072dce93-1669-4901-8445-856a7ae7afbe -->
- [ ] 3.2 完成分段独立审查并修复问题，核对规格和提交归属，备齐独立 PR 交付材料；以实际复审、检查及提交记录验收。 <!-- comet-task:c4eb5f79-0f22-4cde-831f-0f15e2943341 -->

```

## openspec/changes/evaluation-artifact-publishing/.openspec.yaml

- Source: openspec/changes/evaluation-artifact-publishing/.openspec.yaml
- Lines: 1-2
- SHA256: 108f7b3dae33488206672f31b510275110c0194c93062eb1970e19ca60c08722

```md
schema: spec-driven
created: 2026-11-01

```

## openspec/changes/evaluation-artifact-publishing/specs/api/evaluation-artifacts/spec.md

- Source: openspec/changes/evaluation-artifact-publishing/specs/api/evaluation-artifacts/spec.md
- Lines: 1-95
- SHA256: 4eb13b629f34754d8937471fb7ac11409ba85661eb31d02b25d3a17683a7ff02

[TRUNCATED]

```md
## Purpose

将 Web 评估实际执行后已提交的结果发布为归属正确、版本可核对的下载产物，明确完整与部分结果的区别，并让文件发布失败可观察且可在不重新运行模型的情况下恢复，同时保持文件隔离、脱敏和删除清理语义。

## ADDED Requirements

### Requirement: 真实执行自动发布

系统 SHALL 在评估真实结果持久化后自动发布对应已注册评估的文件产物。文件内容 SHALL 来自该账号该次运行的已提交结果，保留实际执行字段和元数据；缺失内容 SHALL 明确为空或不可用，不补造代码、迭代、token、费用或计时。文件发布失败 SHALL NOT 撤销已提交执行结果或伪造评估执行失败。

#### Scenario: 完成评估后直接下载

- **WHEN** 用户的真实评估执行完成并产生持久化结果
- **THEN** 无需人工调用发布方法或注入结果文件，受认证下载、导出和图表接口可读取该评估产物，内容与该次已提交结果一致

#### Scenario: 历史缺失字段

- **WHEN** 已有结果没有完整执行载荷
- **THEN** 发布内容保留真实状态和已有度量，并显式表示缺失字段，不将默认成功或默认零值作为执行证据

### Requirement: 部分结果和多格式一致性

系统 SHALL 明确发布版本、评估状态、已记录及预期单元数和完整性；running/paused/failed/cancelled 的已提交结果 SHALL 作为部分结果呈现。没有结果或产物不可用 SHALL 返回明确错误，不作为成功空文件下载。既有 JSON、CSV、Markdown、HTML、PNG、ZIP 格式 SHALL 可解析或打开，并表达相同运行和版本的真实内容及完整性。

#### Scenario: 暂停或失败后已有部分结果

- **WHEN** 评估暂停、失败或取消前已有已提交结果
- **THEN** 可用产物标记为部分结果，说明实际记录数和预期数，未执行单元不伪装为成功

#### Scenario: 新版本未发布

- **WHEN** 当前持久化结果版本比已发布文件更新
- **THEN** 系统不将旧文件作为当前完整成功产物，发布状态明确表示当前版本尚未可用

#### Scenario: 多格式内容可核对

- **WHEN** 用户下载同一可用版本的 JSON、CSV、Markdown、HTML、PNG 和 ZIP
- **THEN** 文件均为可用格式，内容对应同一账号和运行，部分结果在文件或随附清单及响应元数据中明确表达

### Requirement: 单调发布版本与幂等激活

系统 SHALL 持久化待发布内容和版本，防止旧执行代际、较旧发布版本、重复消息和恢复回调覆盖较新产物。同一内容版本重复发布 SHALL 幂等；失败候选和已替代文件 SHALL 可清理，不产生无法回收的占用。最终激活 SHALL 只引用完整、校验成功且仍为当前允许版本的文件。

#### Scenario: 旧发布晚返回

- **WHEN** 新版本已生成并激活，旧版本发布或旧 Worker 回调随后完成
- **THEN** 当前产物不被旧版本替换，当前发布状态和结果不倒退

#### Scenario: 激活后确认前崩溃

- **WHEN** 文件已激活但发布确认尚未提交时进程退出，之后重试同一版本
- **THEN** 系统能核对并完成该版本确认，不生成重复有效副本或破坏更新产物

### Requirement: 发布状态和独立重试

系统 SHALL 向当前所有者提供发布状态和重试入口，区分待发布、已发布、失败、无结果及文件不可用，提供版本、完整性、重试次数和安全错误分类。重试 SHALL 只处理持久化发布内容，不重新调用模型；队列或文件操作失败 SHALL 可观察，不能报告未发生的成功。

#### Scenario: 发布失败后恢复

- **WHEN** 文件写入或激活失败，用户或独立任务重试发布
- **THEN** 已提交结果保持，发布错误可查询；成功重试后当前版本可下载，模型执行次数不增加

#### Scenario: 提交快照后进程退出

- **WHEN** 待发布快照已提交但尚未完成文件发布时进程退出
- **THEN** 待发布状态仍可查询并可独立重试，无需重新运行评估

#### Scenario: 历史评估没有发布记录

- **WHEN** 所有者显式重试已有真实数据库结果、但尚无发布记录的历史评估
- **THEN** 系统可从实际结果建立快照并发布，无法恢复的原始执行载荷明确缺失，不调用模型或伪造字段

### Requirement: 文件归属和生命周期保护

发布、状态、重试与下载 SHALL 检查业务及文件注册归属，沿用脱敏、完整性校验、配额、保留期及清理机制。已删除评估和文件 SHALL 不可通过延迟发布复活；过期或已删除文件 SHALL 不因旧发布状态而假装可用。

#### Scenario: 跨账号和删除后的延迟任务

- **WHEN** 其他账号查询或重试产物，或删除评估后旧发布任务到达
- **THEN** 系统拒绝越权访问且不泄露内容，延迟任务不会重新注册、激活或公开已删除产物

```

Full source: openspec/changes/evaluation-artifact-publishing/specs/api/evaluation-artifacts/spec.md
