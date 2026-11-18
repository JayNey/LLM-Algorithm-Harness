# Issue #492 验证报告

日期：2026-11-18。基线：8a4d0e1c。工作区：main，current。

## 验收结论

本次 issue 验收通过。完整离线套件初次运行暴露的两项真实回归已修复，相关路径新增复核 177 项全部通过；环境异常亦逐项复核通过。原始完整运行不是一次全绿，详见补充回归记录。配置为 tweak、direct/direct/off，未执行独立审查；主会话已检查最终 diff。

| 维度 | 证据 |
| --- | --- |
| 完整性 | 6/6 任务完成，4 项 requirement、11 项 scenario 均有实现及验证映射 |
| 正确性 | 新增 36 项参数契约回归；相关 8 个测试文件合计 340 passed |
| 一致性 | 共享序列化保留字段显式性、ToT 合并优先级、控制字段过滤与指纹隔离均符合 design.md |

## A：持久化与继承

实现：`src/models.py` 的 StrategyConfig wrap serializer 仅移除未显式提供的 temperature 和 max_tokens。保留其他默认字段及显式默认值；嵌套序列化使用同一逻辑，三个 API service 无需复制特殊处理。

`test_database_round_trip_preserves_generation_overrides`：实验、A/B、基准各 4 组，经过真实业务 SQLite 保存、新 session 加载及生产配置重建，再用真实 LLMClient 与模拟 SDK 验证请求与 effective_params。覆盖模型温度 0.2、token 上限 3500；策略显式 0.7、2000 优先及分别省略。

`test_nested_config_snapshots_keep_omitted_overrides`：策略、Harness、Experiment、A/B 的 JSON 快照往返仍继承模型；`test_historical_explicit_defaults_remain_overrides` 保留历史显式 0.7/2000。README 说明无法恢复历史输入显式性，需要重新创建并省略覆盖字段。

## B：ToT 生产工厂与请求

实现：`src/strategies/tree_of_thoughts.py` 按显式构造器值、custom_params、既有默认值解析；严格检查正整数、非布尔数、有限范围和搜索枚举。`src/strategy_base.py` 将四个搜索字段纳入供应商参数过滤集合。

`test_harness_tot_controls_reach_search_and_stay_out_of_sdk`：从 Harness 工厂创建，实际小树按 1/1/dfs/0.9 运行，生成与评分共两次模型调用，0.8 分支被剪枝。真实请求构建中不出现控制字段，top_p=0.85 保留，迭代 effective_params 与请求一致。

`test_harness_rejects_invalid_tot_before_provider_call`：14 组非法值在供应商调用前失败，覆盖类型、布尔、小数、字符串、边界、NaN/Inf。`test_tot_defaults_and_explicit_constructor_precedence` 与已有 ToT 策略回归验证默认值和直接构造兼容。

## 复用兼容

实现：保留显式性后的策略快照进入既有任务与组合指纹；`src/task_service.py` 在配置指纹中增加参数契约版本，隔离无法证明使用了新语义的旧结果。沿用阶段 3 的独立采样保护，不改变供应商响应缓存身份。

`test_checkpoint_refuses_omitted_vs_explicit_defaults` 验证温度和 token 的省略/显式默认值不能复用检查点；`test_checkpoint_refuses_old_parameter_contract_and_search_changes` 验证旧指纹、搜索设置变化被拒绝，原结果文件仍可读取。已有实验、A/B、基准正常暂停恢复回归仍通过。

## 命令与结果

执行目录均为仓库根，除基线复核位于 `/private/tmp/comet-492-baseline`（git archive HEAD 的未修改副本）。解释器为 `/private/tmp/harness-review-env/bin/python`。

- 初始 RED：新回归观察到 31 项失败，原因对应省略值丢失、搜索值忽略、非法配置未拒绝及旧指纹可复用。另有导入测试类被重复采集，随后仅调整导入别名。证据 `/private/tmp/comet-492-red.log`。
- A 局部 GREEN：17 passed，证据 `/private/tmp/comet-492-a-green.log`。
- 定向集成：`python -m pytest tests/test_strategy_parameter_contract.py tests/test_models.py tests/test_tree_of_thoughts.py tests/test_task_service.py tests/test_business_checkpoints.py tests/test_experiment.py tests/test_llm_client.py tests/test_api_experiment_benchmark.py -q --no-cov`，340 passed，证据 `/private/tmp/comet-492-targeted.log`。
- Ruff check、Black --check：5 个改动 Python 文件通过。
- Mypy：4 个改动生产模块通过，证据 `/private/tmp/comet-492-mypy.log`。
- `python scripts/find_missing_encoding.py`：0；`git diff --check`：通过。
- `comet classic openspec -- validate fix-strategy-parameter-inheritance --strict`：通过。
- 4 项 HTTP 测试因沙箱禁止本机监听出现环境错误，允许回环监听后全部通过，证据 `/private/tmp/comet-492-loopback.log`。
- broker 不可用测试同样因本机监听权限失败，允许监听后通过，证据 `/private/tmp/comet-492-broker-loopback.log`。

## 补充完整离线回归

`python -m pytest -m 'not online' --no-cov`：4303 passed、44 skipped、5 failed、4 errors，315.71s，日志 `/private/tmp/comet-492-offline.log`。其中两项为下文记录的真实展示入口回归，3 项失败与 4 项错误为环境问题。4 项 HTTP 测试与 1 项 broker 测试允许本机监听后通过；两项可读性测试在临时安装 Flake8 后通过（`/private/tmp/comet-492-readability.log`）。完整初次运行明确未通过，不能用复核结果掩盖真实失败。

预先用未修改 main 副本复核：两项 `test_analyze_clean_code` 因缺少可读性 CLI 失败，`test_unavailable_broker_has_bounded_retry_and_no_result_backend_subscription` 因本机监听权限失败，详见 `/private/tmp/comet-492-baseline.log`。不修改本 issue 范围之外的实现。

## 范围、风险与未执行项

交付文件共 8 个：6 个生产模块、1 个测试文件、README；文件数已获用户明确授权，见 rulings.md，流程产物位于当前 change。无需数据库迁移。历史已存参数值不会被猜测改写；修复前检查点需重新运行，旧结果保留。未调用在线付费供应商；独立审查按已确认 off 配置跳过。

## Verify 返回 Build

两项真实回归：`tests/test_api_monitoring_probes.py::test_strategy_directory_reuses_registry_and_schema_defaults` 和 `tests/test_api_documentation.py::test_documented_metadata_fields_match_public_views`，均已单独复现，日志 `/private/tmp/comet-492-metadata-red.log`。新增修复位置预计为 `api/monitoring/probes.py` 和 `api/files/templates.py`，保持默认值元数据与公开模板契约。用户已批准 8 文件继续 tweak，原需求与风险不变。策略目录改为从 schema 获取展示默认值；模板明确填写原有 0.7/2000 示例值。两项真实失败及相关 API 路径复核已通过。

+
+## 修复后最终复核
+
+- `python -m pytest tests/test_api_monitoring_probes.py tests/test_api_documentation.py tests/test_strategy_parameter_contract.py tests/test_api_files.py -q --no-cov`：177 passed，38.11s，日志 `/private/tmp/comet-492-metadata-green.log`。覆盖完整套件发现的两项真实回归以及所有新增参数契约测试。
+- 最终 Ruff check、Black --check：7 个修改 Python 文件通过；编码扫描与 git diff --check 再次通过。
+- 扩大后的默认 Mypy 检查：5 errors in 3 imported files（celery 缺类型、scipy 缺 stubs、api/monitoring/queue_probe.py:82 既有类型错误），未修改 main 副本以相同命令得到完全相同的 5 项错误。日志 `/private/tmp/comet-492-mypy-final.log` 和 `/private/tmp/comet-492-mypy-baseline.log`。
+- `mypy --follow-imports=silent --disable-error-code=import-untyped` 对 6 个改动生产模块检查通过，日志 `/private/tmp/comet-492-mypy-focused.log`。此前对 4 个核心修改模块的默认 Mypy 也通过。未宣称仓库全量类型检查通过。
+- 独立审查按已确认 off 配置跳过。最终 diff 与 4 requirement / 11 scenario 逐项自检无未解决的本 issue 缺陷。完整套件异常均已解释并复测，无需因两个展示入口的局部修复重复整套测试。
+