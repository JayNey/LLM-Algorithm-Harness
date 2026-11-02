# #319 真实评估文件产物发布验证

独立分支 feat/319-evaluation-artifacts；初始 main@8a6ab91，实施中合入 main@859f33b（#327、#330 已合并）。用户已确认 Open/Design 及 autonomous / tdd / standard，并明确要求按推荐自主完成两个 PR，不再重复询问常规步骤。正式规格与设计在 openspec/changes/evaluation-artifact-publishing；本报告不代替阶段守卫。

## 实现与关键边界

- 单元真实 execution_payload 脱敏保留；结果、版本化发布快照和业务生命周期同事务持久化。文件注册使用 evaluation_id，不混用检查点 eval-{id} 或数据库报告 run_id。
- Worker 正常路径发布当前快照；API/TaskManager 的暂停、恢复、取消提交后派发独立发布，强制终止 Worker 不依赖 finally。无 AsyncTask 的旧评估取消同样暂存终态。提交后派发前崩溃留下可查询/重试快照，独立发布不调用模型。
- 业务锁、单调 revision、文件摘要及实际结果内容摘要共同保护激活。旧版本/旧代际拒绝；同版本幂等，失败候选复用和回收；相同已删除结果不因仅状态/代际变化复活。
- 失败回写及 retry 的第二事务均重新检查当前有效文件，迟到失败不降级并发成功。下载验证并读取一个不可变文件，复核版本/删除标记后渲染；响应头和内容来自同一冻结快照。
- 部分结果、空值/未知费用、执行题目元数据保留；JSON/CSV/Markdown/HTML/PNG/ZIP 可用，旧手工格式保持读取。主动删除、过期和损坏区别处理；严格计算新旧文件真实并存配额，空间不足明确拒绝，不隐含放宽。
- 独立发布任务 ignore_result，不订阅结果后端；生产端无连接重试，连接/读取有界。队列失败不回滚已提交的取消/评估结果，持久化安全错误分类，不暴露异常原文或私有路径。

## 迁移与公开契约

main 的站内通知已使用 0006，本 change 为 0007/down_revision=0006。升级/降级保留原评估行，降级本迁移不删除通知表。SQLite 真实迁移往返、PostgreSQL 离线 SQL 均核对。

依据 docs/api-versioning.md，HTTP 契约版本增加为 1.6.0，URL 仍 v1，应用版本不变。独立兼容性审查确认既有三项文件 GET 操作仅增加两个可选头；去掉这两项后与基线完全一致，参数、媒体类型、认证、错误和既有组件不变。冻结 JSON 仅定向追加六处头声明及两个新操作，不重录其他主干新增路径，不放宽比较规则。

## RED / GREEN 与异常调查

- /tmp/319-red-schema.log → /tmp/319-green-schema.log：新迁移表/字段及原始执行载荷缺失的真实断言失败，后续3项通过。初次定向未关闭全仓覆盖率门槛，额外覆盖率失败不计为行为 RED；后续定向使用 --no-cov。
- /tmp/319-red-publication.log：新增发布模块/API 尚未实现的结构性失败；后续真实行为 RED 分别记录于候选、并发、完整性和删除回归。未把缺少第三方依赖或路径错误当作产品行为 RED。
- /tmp/319-red-http-worker.log → /tmp/319-green-http-worker.log：原 Worker 未发布、状态路由和版本头缺失；新增真实编排到 HTTP 下载后通过。
- /tmp/319-red-candidate-race.log：崩溃候选不复用导致配额失败、迟到写入失败覆盖成功；补幂等候选与成功保护。
- /tmp/319-red-integrity.log：损坏当前文件无法显式修复；同版本 CAS 增加失效指针条件，保留并发修复幂等。
- /tmp/319-red-deletion-content.log：仅生命周期变化提升版本而重建已删相同结果；补实际结果内容摘要墓碑。
- /tmp/319-red-cors.log：浏览器无法读取产物版本/完整性头；补既有 CORS 暴露配置。
- /tmp/319-red-review.log：独立审查4项问题，5个真实失败（包含JSON/chart两个变体）：旧不可用失败晚到、retry降级并发成功、下载头/内容跨版、取消强杀跳过finally。另 /tmp/319-red-legacy-cancel.log 覆盖无任务旧评估。修复后相关回归通过；同一独立审查者定点复查9项通过，无新缺陷。
- 初次全量结果为3688通过/18失败/25跳过，非通过证据。定位为离线队列驱动缺新任务类型、HTTP单元替身缺新服务/新操作、OpenAPI登记/基线及本地 PATH；按真实新服务边界扩展驱动/替身，补完整文档和经审查的定向基线。质量工具已在虚拟环境，测试命令补其 bin 到 PATH。修复后原失败集合957项通过，仅保守基线尚需定向更新；更新后文档/版本48项通过。
- 过程限制：版本化多格式渲染未单独保留实现前的完整格式断言 RED；有 Worker/HTTP/头/CORS 的 RED 和六种真实输出解析、TCP联调 GREEN。不回退代码伪造历史 RED，也不以此声称所有渲染行均由测试先驱动。

## 实际检查与场景映射

专用 tests/test_evaluation_artifacts.py 共41项：自动发布与缺失字段；暂停/恢复、取消/失败部分结果；旧版本和同版本并发；激活后业务确认前崩溃；候选复用/配额；删除/过期/损坏；迟到失败/重试竞态；冻结下载；两类取消；归属/CSRF/队列失败/独立重试；有界发布传输与迁移。

- 真实执行自动发布/历史缺失：test_real_worker_commits_publishes_and_http_downloads_without_manual_injection、test_explicit_legacy_retry_builds_snapshot_from_actual_rows_only；raw execution及metrics未知标记不补造。
- 部分结果/新版本/格式：test_worker_partial_lifecycle_and_old_generation_preserve_current_artifacts、test_partial_newer_revision_cannot_be_replaced_by_older_publication、test_versioned_http_downloads_include_real_revision_and_completeness、两个冻结下载变体。
- 版本/幂等/崩溃：test_late_inflight_older_snapshot_cannot_replace_newer_activation、test_simultaneous_duplicate_publishers_leave_one_active_file、test_activation_before_business_confirmation_is_recoverable_and_idempotent、候选复用测试。
- 状态/独立重试：文件失败与Worker失败隔离、HTTP拥有者/空态/队列失败、独立任务重试、实际取消无需finally、legacy取消及CSRF测试。
- 生命周期/清理：跨账号/删除延迟消息、配额并存、内容删除标记、过期和损坏的显式修复回归。

分段审查前定向182项、修复后240项通过；合入主干后159项（含通知、TaskManager及Worker）通过。mypy src/ --ignore-missing-imports 无错误；ruff及Black检查通过。最终全量及当前提交检查在下节按真实结果补记。

scripts/verify_evaluation_artifacts.py 在隔离真实 TCP API、认证、数据库与文件服务上运行实际 Celery 任务函数：导入/创建、用户暂停后部分下载、恢复后完整下载、六格式、文件失败隔离、独立重试不增加模型驱动调用均通过。没有人工注入 EvaluationResult 或手动 publish_results。Provider、sandbox、broker/backend 为明确的可控替身，共3次模型驱动调用；这不是付费供应商或独立OS Worker/真实Redis的测试。诊断及实际输出保存在脚本创建的私有临时目录。

## Build 最终检查：通过

- 最新主干合并后的全量 `pytest -m "not online"`：3716 passed、25 skipped，覆盖率92.90%，实际exit=0。日志 /tmp/319-full-tests-final-3.log。前一轮仅余通知模块旧1.5.0断言，已与1.6.0一致；文档/版本/通知63项复跑通过。
- ruff全部通过；Black检查360文件不需变化；mypy src/ --ignore-missing-imports：101源文件无错误；git diff --check通过。
- 最终真实TCP六场景/六格式通过，模型驱动3次；独立重试没有增加模型调用。日志 /tmp/319-http-final.log。
- 五项需求、14项规格场景均有上文对应实现与验证；修复复查和公开契约兼容性独立审查均通过。

Verify唯一最终集成审查、阶段守卫及远端交付将在实际完成后补记。没有 PostgreSQL在线/NFS/大型数据集压测、独立OS Worker/真实Redis或真实模型费用验证。

## Verify 三维结论：PASS

- 完整性：8/8实施任务已验收提交；5项需求、14项规格场景均有前述实现与验证映射，迁移、API文档和兼容基线齐备。
- 正确性：当前提交全量3716通过、25跳过、覆盖率92.90%；专用边界、原HTTP工作流、跨账号/CSRF、错误与下载冻结、迁移保留通知均验证。源数据、空值/未知费用和部分结果说明一致，无需人工发布或重跑模型修复文件。
- 一致性：遵循用户确认的唯一设计和原任务范围；新迁移0007依赖已合并0006，HTTP契约按既有政策为兼容1.6.0。公开请求、原媒体类型、认证、错误及既有组件保持，新增头为可选。
- 唯一最终集成审查 review_319_final 通过，实际检查 origin/main...7722612 全部PR差异，独立64项复跑通过；定向基线去掉两个新增操作和六处可选头后与主干完全一致。审查未修改跟踪文件。
- Build阶段全部守卫通过。最终验证回执由Runtime另行执行相关测试记录，只有守卫通过后才归档。此后提交的本报告变化仅补验证事实，业务实现与被审查版本相同。

本报告的过程和环境限制仍适用，未将可控替身称作真实付费模型或独立进程/真实Redis；渲染初始RED缺口如实保留。PR仅供审查，不自动合并。
