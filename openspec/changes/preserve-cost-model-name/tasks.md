## 修复任务

- [x] 1. 添加并运行成本拆分与优化报告的失败回归测试，记录根因证据。
- [x] 2. 修复真实模型名传递及模型/策略聚合，确认回归转绿。
- [x] 3. 运行相关测试、格式与构建验证，记录根因消除结果。

## 验证证据

- RED：两项新增 API 测试均以业务断言失败（详见 proposal.md）。
- GREEN：相同命令 2 passed。
- 相关回归：`pytest tests/test_api_cost.py tests/test_cost_optimizer.py tests/test_pricing.py tests/test_cost_alert.py tests/test_cost_estimation.py tests/test_pareto.py --no-cov -q`，113 passed。
- `black --check api/services/cost_service.py tests/test_api_cost.py`、`ruff check api/services/cost_service.py tests/test_api_cost.py`、`git diff --check` 均通过。
- 构建：`python3 -m pip wheel . --no-deps --no-build-isolation --wheel-dir /tmp/preserve-model-wheel` 成功。环境没有可调用的 `python3 -m build`，使用现有 pip/setuptools 完成真实 wheel 构建。
- 根因消除：两处硬编码模型输出均移除，评估优化聚合键包含模型和策略。只有 model 缺失时回退 evaluation-run；无 schema/API 变更。
- Comet task 上下文插件因全局 state.json.lock 写入权限不足不可用；按 hotfix 协议不阻断修复。
