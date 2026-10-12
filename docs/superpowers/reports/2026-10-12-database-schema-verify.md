# 验证报告：database-schema（上游 issue #151）

- 日期：2026-10-12
- 分支：comet/database-schema（基线 6d32b3f，即 upstream/main 合入 #171/#172/#173 后的最新点）
- 验证模式：full（17 变更文件 / 1 delta capability / 7 任务）；verify_mode=full（含 delta spec）
- 独立审查：已执行并返回 approve（见 §审查结论）；IMPORTANT 与可安全修复项已在交付前修复

## 检查结果简表

| # | 检查项 | 结果 | 证据 |
|---|--------|------|------|
| 1 | tasks.md 全部完成 | PASS | 7/7 `[x]`（3.2 随本报告完成勾选） |
| 2 | 实现与 tasks 描述一致 | PASS | `git diff 6d32b3f..HEAD` = api/db 包 + 迁移 + 服务落库改造 + 题库导入 + 测试 + 文档，无超范围改动 |
| 3 | 构建/测试通过（Runtime 证据） | PASS | build check exit=0（log b4ac1866）：1281 passed / 4 skipped，coverage 90.41%；verify check 见 §验证证据 |
| 4 | 相关测试通过 | PASS | tests/test_api_database.py 9 条全过；test_api_auth / test_api_files（既有行为回归）121 条全过 |
| 5 | 无安全问题 | PASS | owner 过滤覆盖全部读写路径；ProblemStore 字段白名单；无密钥/注入引入；业务库与认证库物理隔离延续 #172 边界 |
| 6 | 最终集成代码审查 | PASS | 第一轮独立审查 approve（1 IMPORTANT + 3 WARNING + 3 SUGGESTION）；IMPORTANT 与可修复项已修复，见 §审查结论 |
| 7 | 核心场景与边界验证 | PASS | 见 §场景核对 |

## OpenSpec validate

`comet classic openspec -- validate database-schema` → valid

## 场景核对（delta spec: api/database-schema）

| Requirement / Scenario | 核对方式 | 结果 |
|---|---|---|
| 业务数据持久化 · 任务持久化跨重启 | `test_restart_marks_non_terminal_tasks_failed`（两个 app 实例 + 同一库文件，中断任务 failed 附 "interrupted by service restart"）；`test_completed_results_survive_restart`（completed 任务结果/花费跨实例保留） | PASS |
| 业务数据持久化 · 迁移可从空库复现 | `test_roundtrip_on_empty_database`（upgrade→downgrade→upgrade 往返，业务表随之生灭） | PASS |
| 题库入库与幂等导入 · 重复导入幂等 | `test_reimport_updates_in_place_without_duplicates`、`test_import_json_file_is_repeatable`（data/problems.json 12 条两次导入行数不变）、缺 problem_id 拒绝 | PASS |
| 数据库双栈与隔离边界 · 切换目标数据库方言 | `test_upgrade_sql_is_portable_to_postgresql`（PG 方言离线生成含 CASCADE、无 SQLite 构造）；默认 SQLite 路径全量套件佐证；含 `%` 的 URL（百分号编码密码）离线生成实测通过 | PASS |

## 验证证据

- build check（Runtime，本会话）：exit=0，log `openspec/changes/database-schema/.comet/checks/b4ac1866-6dff-4a31-8c1c-527c70d5b55f.log`
- verify check（Runtime，本会话）：见 `.comet/checks/` 最新日志；门禁 `--cov-fail-under=90` 原样未动，实测 90.41%

## 审查结论

第一轮独立审查（general-purpose 子代理，读全部 diff + autogenerate 比对迁移/模型一致性 + 探针脚本实测删除/竞态/重启语义）结论：**approve**，发现如下及处置：

- **IMPORTANT（已修复）**：`api/db/migrate.py` `set_main_option` 走 configparser 插值，URL 含 `%`（百分号编码的 PG 密码）启动即崩。修复：传入前 `%` → `%%`（configparser 读取时还原），并以审查者给出的复现用例实测通过。
- **WARNING（已修复）**：`delete_evaluation` 原实现先删行后 cleanup，cleanup 失败会孤儿化关联记录且不可重试。已恢复"先 cleanup 后删行"的顺序（与原内存语义一致），删除前二次校验状态。
- **WARNING（已修复）**：`_record_tick`/`_finish`/`_fail` 守卫式写在 PostgreSQL READ COMMITTED 下有丢失更新窗口。已对三处写路径加 `with_for_update()`（SQLite 上为 no-op，行为不变）。
- **WARNING（记录，移交 #159）**：`_recover_interrupted` 在多 worker/双实例部署下会误标另一实例的在途任务。当前单实例不触发；#159 引入多 worker 前需加进程级防护（启动锁或心跳）。
- **SUGGESTION（已修复）**：migrate.py docstring 引用了不存在的 alembic.ini，已改为程序化入口说明。
- **SUGGESTION（已修复）**：lifespan shutdown 未释放 engine 连接。已加 `EvaluationService.close()` 并在 main.py finally 中调用。
- **SUGGESTION（记录，移交 #155）**：`list_evaluations` 全量载入后内存分页（与原实现一致），数据量增长后应改 SQL COUNT + LIMIT/OFFSET。

## 已知豁免

- `EvaluationCreateRequest.timeout_seconds/max_concurrency` 未持久化：与原实现行为一致（原 TaskState 亦丢弃），响应模型本就不含
- `evaluation_results` 表当前无写入方：schema 先行，消费方为 #149（队列）/ #155（结果查询）
- CI mypy 仅覆盖 `src/`；`api/models.py` 等处 mypy 报错为上游既有债务，不在本次范围
- 时间戳 naive UTC 存储：全仓既有约定

## 交付门禁（2026-10-12）

推送 `comet/database-schema` 并创建关联 #151 的 PR（base: JayNey/main），检查远端 CI，交付结果记录于 delivery。
