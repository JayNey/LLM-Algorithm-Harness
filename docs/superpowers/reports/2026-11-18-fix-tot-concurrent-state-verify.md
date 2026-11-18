# 验证报告：fix-tot-concurrent-state

## 结论
Issue #493 的实现与已批准方案一致。任务 3/3、增量需求 1/1、验收场景 2/2 已覆盖，未发现阻断问题；可进入归档决定。

## 完整性与正确性
- `src/strategies/tree_of_thoughts.py` 的 `_SearchState` 包含调用迭代、响应、类型/深度与预算停止原因。每次 `search_tree` 创建独立状态并在 finally 恢复，所有记账与结果提取使用当前状态；无共享可变默认值。
- `tests/test_harness.py::test_tot_shared_runtime_isolates_problem_state` 通过真实 Harness task-service、生产工厂、ToT 与 host sandbox 验证。断言两次执行使用同一个策略实例；Barrier/Event 确定性交错，不使用 sleep。覆盖两题正常、模型异常、预算停止，及对应串行情形。
- 正常两题各保留两次逻辑调用，token 为 30/60，总量 90；各自提示、响应、reasoning 和定价归属正确。异常或预算拒绝题的零用量不影响另一题的 60 token 及成功终态。
- 两题各自选中代码通过公开和隐藏判题；从 TaskService store 重读的结果与 Harness 结果相同。
- `tests/test_tree_of_thoughts.py::test_search_context_restored_after_result_exception` 验证结果构建意外抛错仍恢复上下文，下一次执行独立记账。既有多层 BFS/DFS、剪枝、选中叶子、失败记账与预算测试仍通过。

## 实际检查
工作目录均为 `/Users/verstappen/LLM-Algorithm-Harness`。
- RED：`/tmp/harness-review-env/bin/python -m pytest tests/test_harness.py -k tot_shared_runtime --no-cov -q`：旧实现 3 个并行失败、3 个串行通过；日志 `/tmp/493-red.log`。
- GREEN：同一命令修复后 6/6 通过；日志 `/tmp/493-green.log`。
- 最终：`/tmp/harness-review-env/bin/python -m pytest tests/test_tree_of_thoughts.py tests/test_harness.py tests/test_task_service.py --no-cov -q`：110 passed，3 条既有收集/弃用 warning；日志 `/tmp/493-targeted-final.log`。
- `/tmp/harness-review-env/bin/ruff check src/strategies/tree_of_thoughts.py tests/test_harness.py tests/test_tree_of_thoughts.py`：通过。
- 同三文件 `ruff format --check`：通过；`git diff --check`：通过。
- `comet classic openspec -- validate fix-tot-concurrent-state --strict`：通过。

## 一致性、范围与限制
实现遵循 ContextVar + 每次搜索状态 + finally reset 设计，公开方法签名、结果结构和工厂生命周期保持兼容。交付源码/测试共 3 文件，范围适合 tweak。独立审查按当前配置 reviewMode=off 跳过，未把实现者检查称为独立审查。未运行在线供应商调用或仓库全量测试；本次局部改动的验收项全部由上述检查覆盖。
