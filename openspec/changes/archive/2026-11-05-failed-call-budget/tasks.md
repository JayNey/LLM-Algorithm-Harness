## 1. 修复与验证

- [x] 1.1 修复准入调用记账和 Self-Consistency 停止语义，补充字段与实验指南口径；通过成功、异常、缓存、重试与真实策略入口回归测试。
- [x] 1.2 运行实验、策略相关测试、格式与静态检查及构建；核对 delta spec 并记录验证证据。

## 验证证据

- RED：5 项新增核心回归按预期失败，分别展示准入未计数、重试后漏记、多候选继续越限。
- GREEN：`pytest tests/test_experiment.py -o addopts='' -q`，44 passed；`pytest tests/strategies tests/test_llm_client.py -o addopts='' -q`，67 passed。
- 缓存测试最初误用不存在的替身方法名，修正为 `_call_openai` 后全量通过；未为此修改业务实现。
- `black --check`、`ruff check` 对全部改动 Python 文件通过；`mypy src/budget.py src/strategies/self_consistency.py` 通过；`git diff --check` 通过。
- `python3 -m build` 模块未安装；使用现有 pip/setuptools 的 `python3 -m pip wheel . --no-deps --no-build-isolation --wheel-dir /tmp/issue350-dist` 成功构建 wheel。
- 变更为 5 个业务/测试/说明文件，单一既有预算能力，无架构或公共 API 扩展。按含 delta 的 tweak 规则采用 full 验证。
