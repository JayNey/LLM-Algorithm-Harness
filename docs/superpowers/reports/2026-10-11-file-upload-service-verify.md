# Issue #153 文件上传与处理服务验证报告

日期：2026-10-11（Asia/Shanghai）。基线：`b5fa68c`（#172 已合并）。分支：`tweak/20261011/file-upload-service`。

## 实现范围

- 用户隔离本地存储、UUID 文件、所有者/大小/哈希/时间元数据。
- 解析前认证、IP/账号限流、真实字节上限、传输并发和接收超时；Multipart 文件/字段限制与句柄关闭。
- UTF-8 JSON/YAML/CSV 内容检查、危险标签/别名/二进制拒绝、结构和字段边界。
- Problem Schema 与完整性验证、按 problem_id 的事务追加/覆盖去重、同步报告与可查询后台导入进度。
- HarnessConfig/ExperimentConfig 验证、脱敏文件保存和模板查询。
- 用户题库与结果 JSON/CSV/Markdown/HTML/PNG/ZIP 下载；不接受任意本机路径。
- 任务归属登记、可信 worker 结果发布、任务删除 tombstone、定时过期清理、占用重试及崩溃孤立文件回收。

## 验证证据

- 文件服务定向测试：**60 passed**。
- 已有 #152 认证回归：**61 passed**；文件服务变更保持身份与所有权行为。
- 最终全量离线套件：**1272 passed、4 skipped**，覆盖率 **93.41%**，90% 门禁保持不变。
- 完整测试通过 `comet check run file-upload-service build --local -- python -m pytest -m 'not online' --cov --cov-report=term --cov-report=xml` 实际运行，exit=0。
- `ruff check .`、`black --check .`、显式文本编码扫描（0 处隐式编码）：通过。
- `mypy src/ --ignore-missing-imports`：87 文件通过；新增文件服务与路由额外类型检查：9 文件通过。
- OpenSpec `file-upload-service` strict 校验：通过。

## 调试与独立审查

第一轮文件测试中，分块超限触发了字节上限，但 BaseHTTPMiddleware 将接收异常包装成 ExceptionGroup，MultipartParser 无法按原异常关闭 spool。将日志中间件改为直接 ASGI，保留异常类型；测试另发现 TestClient 会聚合请求体，改用真正多次 receive 的 ASGI 输入，强制 spool 落盘，确认超限/断开/空闲超时关闭句柄。CORS 和日志放在边界之外，覆盖提前拒绝及最终状态码。

Bugbot 独立审查发现 1 个 P2：CSV 使用不存在的 judge 字段，并遗漏 entry_point、unsupported_reason、source_metadata 等，重新导入会改变评测语义。已改为全字段 json-v1 单元格编码，支持 None、复杂值、判题/入口/来源与公式字符串的准确往返，并修正普通 CSV JSON 列。补全字段、非默认判题、普通 CSV 和大单元格回归后复审通过。审查者独立运行 CSV/孤立文件相关 **9 passed**，未发现新的可操作问题。

另外补充了文件改名后、元数据提交前崩溃留下的孤立 UUID 文件回收；只处理过保守期限、未登记、在私有分类目录的生成文件，保留已登记和非生成名称。

## 规格场景映射

- 分块超限与句柄关闭：`test_declared_and_chunked_body_caps_and_auth_before_parsing`。
- 断开/空闲超时：`test_interrupted_and_idle_upload_closes_disk_spool`。
- 伪装二进制与解析限制：`test_content_grammar_and_header_checks`、`test_rejects_wrong_media_type_and_deep_json`。
- 所有者：`test_unique_private_upload_metadata_download_and_deletion`、`test_result_download_formats_and_owner_boundaries`。
- 并发追加：`test_concurrent_append_preserves_both_datasets_across_services`。
- 配置无明文持久化：`test_config_validation_templates_and_no_secret_persistence`（两种 Schema、三种格式）。
- 进度与活跃来源保护：`test_running_progress_and_active_source_not_cleaned`。
- 定时清理：`test_periodic_cleanup_and_orphan_stage_cleanup`。
- 占用重试与过期作业：`test_cleanup_retries_permission_error_and_expires_stale_jobs`。
- 迟到 worker：`test_run_deletion_cleans_artifacts_and_blocks_late_worker`。
- CSV 语义：`test_csv_roundtrip_preserves_judge_entry_source_optional_and_formula_strings`。
- 崩溃孤立文件：`test_crash_rename_orphans_reclaimed_but_registered_objects_preserved`。

## 依赖与限制

- #151 尚未完成，元数据和当前题库使用认证 SQLite 中独立的 api_file_* 表；对象存储为可选功能，当前使用本地目录。
- 后台导入为进程内 BackgroundTasks；崩溃/停机作业超时后明确失败，重提交，不伪记成功。#149 后续可对接可靠队列。
- #148 评估执行器仍是模拟器，真实运行结果由 #149 调用可信 publish_results 发布；没有结果时下载返回 404，不放开全局 CLI 目录。
- 派生下载在内存生成、CSV 暂存立即删除；已验证配置保留原 JSON/YAML 格式，输入密钥被移除。
- 上传配置仅验证/保存，不直接执行其路径、URL、env 引用；worker 必须绑定已授权资源与 #152 用户密钥。
- 最终跨平台结论以 PR 最新提交的 CI 为准；不添加测试 continue-on-error，不自动合并。

## 交付

实现、测试、独立审查修复与文档完成；创建关联 #153 的 PR，并在 PR 描述记录最终 CI 结果。
