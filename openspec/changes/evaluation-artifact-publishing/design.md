---
comet_change: evaluation-artifact-publishing
role: technical-design
canonical_spec: openspec
---

## Context

动机见 proposal.md。文件元数据在认证共享 SQLite，Evaluation/EvaluationResult/AsyncTask 在业务数据库；后者部署可用 PostgreSQL，不能假设两库有共同事务。创建评估时文件服务注册 evaluation_id；Worker 的 eval-{evaluation_id} 仅是本地检查点 ID，Evaluation.run_id 是即时报告查询标识，三者不混用。

Worker 已在单元完成后提交数据库结果，持有带 celery_task_id 的执行代际锁，并保留 P8 的执行元数据。EvaluationResult 当前只存度量子集，无法从历史行完整恢复原始 ExecutionResult。FileService 的既有 publish_results 只接受旧策略字典，文件激活没有发布版本。

本文是唯一正式技术设计。用户已选择持久化发布记录、版本检查和独立重试方案，以下具体合同为待审阅的实施建议。

## Goals / Non-Goals

Goals：正常 Worker 自动发布实际结果；结果提交、发布、失败、重试可核对；新版本不能被旧回调覆盖；文件操作失败不撤销已提交执行结果。

Non-Goals：改写即时报告或前端下载 UI、重跑模型补文件、引入对象存储/新队列产品、伪造历史执行内容、改变 P5/P8 的费用和元数据语义。

## Decisions

### 1. Approaches

用户选择 A：业务库持久化发布快照与版本，提交结果后独立发布文件，激活前检查版本；失败由独立发布任务或归属校验的重试入口恢复。重试消费数据库快照，不依赖 Worker 本地目录，也不调用模型。

方案 B 是仅在 Worker 返回前直接调用旧 publish_results：代码较少，但无法覆盖提交后崩溃、独立重试和旧结果覆盖新结果；不采用。方案 C 是外部消息流/对象存储体系，本仓库规模下不必要，不采用。

### 2. 持久化边界与快照

新增业务表 evaluation_artifact_publications，每个评估一条当前发布记录，evaluation_id 主键及 CASCADE 外键，保存 user_id、单调 revision、snapshot JSON、status（pending/published/failed）、published_revision、error_code、attempts 和时间。EvaluationResult 新增 nullable execution_payload JSON，用于新单元原始执行结果的安全持久化；旧行保持 null，不回填默认执行数据。迁移沿现有 Alembic head，兼容 SQLite/PostgreSQL，提供降级。

单元结果、原始 execution_payload、计数和最新发布快照在同一业务事务提交。先按已有顺序锁 AsyncTask/Evaluation，再写发布记录；只有当前执行代际可更新。快照由本事务可见的已持久化 EvaluationResult 生成，包含实际行状态、metrics、error_message 与可空原始 execution；原始内容先脱敏，不持久化凭证。状态变化时即使没有新增单元也更新快照，以记录最终生命周期和完整性。无任何结果时仅记录 unavailable 原因，不发布空的成功文件。

快照内容与上次相同不提升 revision；内容/生命周期/完整性变化则提升。终态消息重复投递只能请求重试已有快照，不能重新执行或覆盖结果。旧代际回调既不能创建新发布版本，也不能改变新版本失败状态。取消、暂停和异常退出以数据库真实状态收尾，保留已提交部分结果；运行线程未确认的结果不宣称已发布。

### 3. 文件内容与兼容性

真实 Worker 发布一个版本化 JSON 文档：schema_version、evaluation_id、run_id（可空）、revision、state、complete、expected_units、recorded_units，以及按策略分组的结果。每条结果保留 problem_id、strategy、status、metrics、error_message、execution（真实原始内容或 null）。complete 仅在评估 completed 且实际记录覆盖全部预期单元时为 true；paused/failed/cancelled/running 均为部分结果，并如实标明缺失数量及原因。

既有 publish_results 的旧策略字典和手工/历史文件继续可读。新发布路径和渲染器识别版本化文档，不用构造默认 ExecutionResult 填补缺失度量。JSON/Markdown/HTML 保留完整性清单和实际结果；CSV 提供实际行字段，缺值留空并附版本/完整性列；PNG 明确部分结果标题，成功比例基于实际记录单元；ZIP 包含 JSON 清单和其余既有格式。源数据中的 P8 元数据与未知费用标记保留。下载入口仍为 /results/{evaluation_id}/download、export、charts；即时 /reports/* 不改变。

HTTP 下载增加可核对且经 CORS 暴露的发布版本与完整性响应头，不把部分结果称为完整结果；GET 发布状态提供同一信息。完全没有结果返回明确不可用；已产生新 revision 但当前文件尚未发布时不把上一版当作当前成功文件，可返回明确的未就绪错误，调用者能查询/重试。失效、被删除或过期文件不能因为旧状态为 published 就宣称可下载。

### 4. 发布、版本和文件回收

业务事务提交后调用发布器；发布器先从持久化快照生成并暂存不可变文件，持久化文件元数据后才准备激活。最终激活前按同一锁顺序重新锁业务实体/发布记录，核对 owner、当前 revision、删除状态；核对失败放弃候选文件。锁内只做有界版本验证、FileStore 原子激活和发布确认，不做渲染。

FileStore 注册记录兼容增加已激活 revision、文件摘要和实际结果内容摘要；删除标记保留真实结果摘要，单纯状态/代际变化形成的新 revision 不能重新发布已删的相同结果，只有真实结果内容变化才可发布新产物。SQLite BEGIN IMMEDIATE 保证文件指针/版本原子更新；较低版本拒绝，重复相同版本相同摘要幂等返回，重复同版本不同摘要拒绝。最终业务确认和文件激活分属两库：若文件激活后业务提交前崩溃，重试通过 revision+摘要识别已激活文件，再完成确认，不重新创建有效副本。若新版本已激活，旧发布即使晚返回也不能替换它。

文件层仅将完整写入且校验成功的候选文件激活，失败不覆盖当前可读文件。候选写入、登记或激活失败时清理候选或标记可回收；旧版本、过期或删除文件沿用清理机制。候选登记前先检查幂等及回收可清理候选，配额按新旧文件实际并存占用计算，不给予隐含替换额度；仍不足时记录 storage_limit/413，保留旧文件，用户释放空间后可重试。失败候选不得永久耗尽配额。旧有效版本可在新发布期间保留供恢复核对，但不得冒充最新版本下载。

### 5. 独立重试与可观察性

新增 GET /api/v1/results/{evaluation_id}/publication，返回 revision、published_revision、status、available、complete、recorded_units、expected_units、attempts、最近错误分类和时间；未发布、无结果、文件过期与发布失败均可区分。错误不包含原始路径、凭证或不受控异常文本。

新增 POST /api/v1/results/{evaluation_id}/publication/retry，只对当前所有者注册且未删除的评估操作；只发送/执行独立发布任务，绝不启动评估。已发布且当前文件有效时幂等返回状态；无结果明确拒绝；排队/处理中重复请求不产生重复激活。端点继续使用 Cookie/CSRF/统一错误规范。独立任务支持有上限的退避重试；队列失败记录失败状态而非伪造已排队成功。

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

先 RED 再 GREEN 覆盖迁移、版本递增/幂等、原始字段保留和空值语义。真实 Worker 编排到数据库快照、文件发布、受认证 HTTP 下载，外部模型采用可控替身，不手工 publish_results 作为主验收。分别解析 JSON/CSV/Markdown/HTML/PNG/ZIP，验证状态、内容、P8 元数据及未知费用。

故障注入覆盖暂存/登记/激活/业务确认/队列失败，旧代际、较旧 revision、同版本重复、暂停恢复/取消竞争、部分异常、重试不重新调用模型、删除/过期/配额回收及跨账号访问。运行定向回归、数据库迁移和 PostgreSQL 离线 SQL、相关类型/格式/编码检查，按 CI 要求检查 macOS/Ubuntu/Windows。最终独立集成审查。

## Migration Plan

先应用兼容业务库迁移和文件 SQLite 增量元数据，再部署 API/Worker；旧文件继续按旧格式读取，新 Worker 才写版本化快照。部署前确认 API 与 Worker 使用相同认证元数据库和共享 UPLOAD_DIR。回滚时停止新发布任务后回滚代码；新文件仍可保留供审计或清理；数据库降级会移除新增发布记录和原始执行字段，需显式由部署者选择，日常回滚不自动丢弃数据。
