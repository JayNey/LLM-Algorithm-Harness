# Issue #491 验证报告

| 维度 | 结果 |
| --- | --- |
| 完整性 | 完成 4 项任务，逐一核对增量规格的 3 项要求和 5 个场景。 |
| 正确性 | 组合目录、实验记录、报告索引和检查点采用相同标识。同名配置在调用供应商前报错。 |
| 一致性 | 实现沿用现有输入指纹、原子检查点和报告生成路径。报告保留用于显示和分组的原始模型名与策略名。 |

## 场景验收

| 场景 | 实现与证据 |
| --- | --- |
| 名称清洗碰撞 | `src/experiment.py:170` 在提交任务前分配序号。`tests/test_experiment.py:1100` 验证串行和并行各有两份原始结果，`comparison.json` 与两两胜率矩阵都记录 `org/model` 通过 1 题、`org_model` 通过 0 题。 |
| 恢复尚未完成的实验 | `src/experiment.py:176` 使用相同标识从实验记录或单元检查点读取结果。`tests/test_experiment.py:1515` 分别从已更新元数据和仅已写入单元检查点恢复，确认原组合标识、结果文件和采样身份保留，只执行剩余组合。`tests/test_business_checkpoints.py:199` 覆盖碰撞名称的暂停续跑。 |
| 同名配置包含不同参数 | `src/models.py:782` 校验模型名和策略名，`src/experiment.py:110` 在运行入口复核。`tests/test_experiment.py:437` 验证构建配置及其被修改后执行两种入口，重复名报错且供应商调用为零。 |
| 重建旧格式实验报告 | `src/experiment_report.py:668` 检测重复标识和共用目录。`tests/test_experiment.py:1141` 验证旧目录可重建，冲突时原报告保留。 |
| 尝试从旧格式检查点恢复 | `src/experiment.py:118` 在读取单元检查点及写入元数据前检查版本。`tests/test_experiment.py:1614` 验证旧版本提示新建实验，原文件保留且供应商调用为零。 |

## 检查结果

- 7 个实验相关模块的 228 项测试全部通过，覆盖 CLI、API、恢复、取消、队列及 Pareto 报告。新增用例在修复前复现了目录覆盖、重名校验缺失和历史引用处理问题。执行日志为 `/private/tmp/comet-491-targeted.log`、`/private/tmp/comet-491-red.log` 和 `/private/tmp/comet-491-red-admission.log`。
- OpenSpec 严格校验、5 个改动文件的 Ruff 与 Black 检查及 `git diff --check` 通过。
- 全量离线套件首次运行覆盖率为 93.08%，4,269 项通过，44 项跳过，3 项失败、4 项报错。补齐环境后定点重跑了全部 7 项异常用例，均通过。全量日志为 `/private/tmp/comet-491-offline.log`。
  - 放开本机环回端口后，`test_full_model_ids_round_trip_over_http`、`test_full_model_id_auth_and_validation_over_http`、`test_real_worker_spend_reaches_http_during_pause_resume_and_duplicate_delivery` 的 `experiment` 和 `ab` 两例，以及 `test_unavailable_broker_has_bounded_retry_and_no_result_backend_subscription` 共 5 项通过。重跑日志为 `/private/tmp/comet-491-loopback.log`。
  - 将 `pylint`、`flake8` 和 `radon` 加入 `PATH` 后，`tests/test_code_quality/test_analyzers.py` 与 `tests/test_code_quality/test_readability_analyzer.py` 各自的 `test_analyze_clean_code` 均通过。重跑日志为 `/private/tmp/comet-491-readability.log`。
- 当前 Tweak 预设关闭独立审查。供应商行为通过离线替身验证。
