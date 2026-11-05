# fix-tot-selected-code 验证报告

日期：2026-11-05。Issue：#347。结论：PASS，可进入归档确认。

## 完整性与一致性

- tasks 2/2 完成；proposal、简要 design 与一个嵌套能力 delta 均已核对。
- 实现仅涉及 src/strategies/tree_of_thoughts.py，测试仅涉及 tests/test_tree_of_thoughts.py；其余为工作流产物。
- tweak 不生成完整 Superpowers Design Doc 或 plan；已按本 change 的 design.md 验证。
- review_mode 为 tweak 默认 off，未派发自动代码审查；仍逐项核对最终 diff 的代码选择、失败状态和边界条件，未发现正确性或安全阻塞。
- 保留探索 iterations；最终结果显式保存选中叶子代码。无可用叶子时清空结果代码并返回 code_extraction_failed。
- 未改变共享结果工厂或 Harness，没有新增 API、依赖、schema 或跨模块协调。

## 规格场景映射

- Return highest scoring leaf：test_result_keeps_best_leaf_across_traversals，覆盖 BFS/DFS、深度 1/3、两种兄弟顺序；直接提取测试同时保护返回代码。
- Handle no valid solution：test_no_usable_leaf_is_extraction_failure 覆盖无分支、全剪枝、空白代码；test_no_leaf_does_not_return_historical_parent 保护无叶子时不回退历史代码；test_empty_high_score_does_not_hide_usable_leaf 保护有效候选不被空候选遮蔽。
- Hidden evaluation uses selected code：test_harness_evaluates_selected_leaf_on_hidden 使用真实 ToT 与 AlgorithmHarness._execute_problem，模型和沙箱为确定性替身，覆盖 hidden 通过/失败及代码一致性。
- Preserve selected code on execution failure：test_public_failure_preserves_selected_code 覆盖公开错误答案和沙箱异常。

## 执行证据

- 修复前既有 ToT：26 passed。
- 新增回归 RED：13 failed、4 passed，失败均指向选中代码未写入结果或空白候选被接受。
- 修复后：python3 -m pytest tests/test_tree_of_thoughts.py tests/test_harness.py --no-cov -q：70 passed。
- black --check src/strategies/tree_of_thoughts.py tests/test_tree_of_thoughts.py：通过。
- ruff check src/strategies/tree_of_thoughts.py tests/test_tree_of_thoughts.py：通过。
- python3 -m compileall -q src/strategies/tree_of_thoughts.py：通过。
- comet classic openspec -- validate fix-tot-selected-code --strict：通过。
- python3 -m pytest -m 'not online'：3825 passed、18 skipped、1 failed、18 errors；退出码 1。失败及错误均为 localhost bind 的 PermissionError，原始日志 /tmp/347-suite.log。
- 以上环境受限项全部在允许本地监听的环境复跑：tests/test_api_cost.py 24 passed；tests/test_deployment_readiness.py 14 passed；tests/test_evaluation_artifacts.py::test_unavailable_broker_has_bounded_retry_and_no_result_backend_subscription 1 passed。三次复跑退出码均为 0，覆盖原运行全部 19 个失败/错误项。
- 全量运行覆盖率 92.96%；src 91.71%（门槛 90%），api 94.78%（门槛 81%）。

## 验证边界

全量命令原始结果并非零错误；环境问题已通过精确复跑确认，无未解决测试失败。现有 Pydantic 弃用、pytest 收集等警告未在本次修改范围内处理。未调用付费模型或真实 Docker 评测；issue 的模型与沙箱契约通过确定性替身验证。

Comet 0.4.0 在 build 阶段设置 verify_mode=full 会报告 tweak build configuration is incomplete；已在 build guard 通过、进入 verify 后使用公开 CLI 成功设置 full。scale 统计工作流元数据共 15 文件且未计入嵌套 delta；本次手工核对实际一个 delta，并执行 full 规格验证。

所有未提交改动均属于当前 change 的状态记录与本报告。测试生成的空 execution lock 已清理；未更改已有任务目录。
