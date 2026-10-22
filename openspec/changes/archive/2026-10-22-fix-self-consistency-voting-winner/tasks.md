## 修复任务

- [x] 1. 新增并运行回归测试，记录返回末尾候选而非投票胜者的失败证据。
- [x] 2. 传递并使用选中代码，验证成功/回退边界、完整候选记录和统计，确认根因消除。
- [x] 3. 运行相关测试、静态检查与构建，记录验证证据供 verify 阶段报告使用。

## 构建阶段证据

- RED：新回归测试 6 failed、4 passed，失败断言均为错误的 `generated_code`。
- GREEN：Self-Consistency 两个测试文件 18 passed；扩大到 `tests/strategies`、`tests/test_strategies.py`、`tests/test_harness.py` 后 79 passed。
- `ruff check`、`black --check`、`mypy` 对涉及文件检查均通过；`python3 scripts/find_missing_encoding.py` 报告 0 项。
- `python3 -m pip wheel . --no-deps --no-build-isolation --wheel-dir /private/tmp/self-consistency-voting-winner-dist` 成功生成 wheel。
- 根因消除：投票的成功与回退分支都返回 `selected_code`，`execute()` 使用该值覆盖通用构造器的末尾候选默认值；未调整迭代顺序、token 汇总或投票逻辑。
- 全量离线测试在后台运行，最终结果由 verify 阶段记录。
