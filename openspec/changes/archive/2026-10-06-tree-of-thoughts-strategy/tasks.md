## 1. 数据结构定义

- [x] 1.1 创建 `ThoughtNode` dataclass，包含 depth、thought、code_snippet、quality_score、children、parent 字段，并验证可以实例化节点且字段类型正确
- [x] 1.2 为 `ThoughtNode` 添加 `__repr__` 方法以便调试，并验证打印输出包含关键字段信息

## 2. 核心策略类实现

- [x] 2.1 创建 `TreeOfThoughtsStrategy` 类继承 `StrategyBase`，实现 `__init__` 方法接受 branching_factor、max_depth、search_strategy、pruning_threshold 参数，并验证参数验证逻辑正确（无效值抛出 ValueError）
- [x] 2.2 实现 `execute` 方法作为策略入口，创建根节点并调用搜索，验证方法返回 ExecutionResult 类型
- [x] 2.3 实现 `create_root_node` 方法，根据 Problem 生成初始思考节点，验证返回的根节点 depth=0 且包含问题描述

## 3. 分支生成

- [x] 3.1 实现 `generate_branches` 方法，为给定节点生成 branching_factor 个子节点，每个子节点包含不同的推理方向和代码片段，验证生成的子节点数量正确且 thought 内容不同
- [x] 3.2 在 `generate_branches` 中构造合适的 LLM prompt，要求生成多个候选推理步骤和对应代码，验证 prompt 包含问题描述、父节点思考内容和分支数量要求
- [x] 3.3 实现代码提取逻辑，从 LLM 响应中提取每个分支的 code_snippet，验证使用 `self.extract_code()` 正确提取代码块

## 4. 节点评估

- [x] 4.1 实现 `evaluate_node` 方法，向 LLM 发送评估 prompt 并解析返回的质量分数（0-1 范围），验证返回值在 [0.0, 1.0] 区间内
- [x] 4.2 构造评估 prompt，包含问题描述、节点思考内容、代码片段，要求 LLM 评估逻辑正确性和解决方案质量，验证 prompt 格式清晰且包含评分指引
- [x] 4.3 处理 LLM 返回格式异常情况（如未返回数字），设置默认分数或重试，验证异常情况下不会崩溃

## 5. 剪枝实现

- [x] 5.1 实现 `prune_branches` 方法，过滤掉 quality_score < pruning_threshold 的节点，验证返回的节点列表只包含高于阈值的节点
- [x] 5.2 在 `prune_branches` 中记录被剪枝的节点数量和原因到日志，验证日志输出包含剪枝统计信息

## 6. 搜索算法

- [x] 6.1 实现 `search_tree` 方法框架，根据 search_strategy 参数选择 BFS 或 DFS，验证方法可以调用对应的搜索逻辑
- [x] 6.2 实现 BFS 搜索逻辑，使用 `collections.deque` 维护待扩展节点队列，按层级顺序扩展，验证 BFS 模式下先扩展浅层节点
- [x] 6.3 实现 DFS 搜索逻辑，使用 list 作为栈维护待扩展节点，按深度优先顺序扩展，验证 DFS 模式下先扩展深层分支
- [x] 6.4 在搜索循环中实施 max_depth 限制，停止扩展深度达到上限的节点，验证不会生成深度超过 max_depth 的节点
- [x] 6.5 在搜索过程中记录每次节点扩展、评估、剪枝到 iterations 列表，验证 iterations 记录包含完整的搜索轨迹

## 7. 解决方案提取

- [x] 7.1 实现 `extract_best_solution` 方法，从所有叶子节点中选择 quality_score 最高的节点，验证返回的是分数最高的节点
- [x] 7.2 处理无有效解的情况（所有分支被剪枝或无叶子节点），返回失败的 ExecutionResult，验证失败时返回包含错误信息的结果
- [x] 7.3 从最佳节点提取 code_snippet 作为最终代码，验证返回的代码与该节点的 code_snippet 一致

## 8. 集成与配置

- [x] 8.1 在 `src/strategies/__init__.py` 中导入并注册 `TreeOfThoughtsStrategy`，验证策略可以通过配置文件加载
- [x] 8.2 创建配置示例文件或在现有配置文档中添加 ToT 策略配置模板，验证配置参数完整且格式正确
- [x] 8.3 确保 TreeOfThoughtsStrategy 正确继承和使用 StrategyBase 的 `generate`、`extract_code`、`build_base_prompt` 方法，验证调用基类方法无异常

## 9. 单元测试 - 数据结构

- [x] 9.1 测试 ThoughtNode 创建和字段访问，验证所有字段可以正确读写
- [x] 9.2 测试 ThoughtNode 的父子关系链接，验证 parent 和 children 引用正确建立

## 10. 单元测试 - 配置验证

- [x] 10.1 测试 branching_factor < 1 时抛出 ValueError，验证错误消息清晰
- [x] 10.2 测试 max_depth < 1 时抛出 ValueError，验证错误消息清晰
- [x] 10.3 测试 search_strategy 为无效值时抛出 ValueError，验证错误消息清晰
- [x] 10.4 测试 pruning_threshold 超出 [0, 1] 范围时抛出 ValueError，验证错误消息清晰

## 11. 单元测试 - 分支生成

- [x] 11.1 测试 generate_branches 生成正确数量的子节点，验证返回列表长度等于 branching_factor
- [x] 11.2 测试生成的子节点 depth 正确递增，验证子节点 depth = 父节点 depth + 1
- [x] 11.3 测试子节点的 parent 引用指向正确的父节点，验证 parent 字段正确设置
- [x] 11.4 使用 mock LLM 响应测试分支生成，验证可以从 mock 响应中提取 thought 和 code_snippet

## 12. 单元测试 - 节点评估

- [x] 12.1 测试 evaluate_node 返回 0-1 范围内的分数，验证使用不同 mock LLM 响应时分数在有效范围内
- [x] 12.2 测试评估 prompt 包含必要信息（问题、思考、代码），验证 prompt 构造逻辑完整
- [x] 12.3 测试 LLM 返回非数字时的异常处理，验证不会崩溃且有合理的回退行为

## 13. 单元测试 - 剪枝

- [x] 13.1 测试 prune_branches 正确过滤低分节点，验证返回列表不包含低于阈值的节点
- [x] 13.2 测试所有节点都被剪枝的边界情况，验证返回空列表且不崩溃
- [x] 13.3 测试剪枝日志记录，验证日志包含被剪枝节点数量

## 14. 单元测试 - 搜索算法

- [x] 14.1 测试 BFS 按层级顺序扩展节点，验证深度 N 的所有节点在深度 N+1 之前扩展
- [x] 14.2 测试 DFS 按深度优先顺序扩展节点，验证优先扩展一条完整路径
- [x] 14.3 测试 max_depth 限制生效，验证不会扩展超过最大深度的节点
- [x] 14.4 测试搜索过程记录到 iterations，验证 iterations 列表包含所有扩展步骤

## 15. 单元测试 - 解决方案提取

- [x] 15.1 测试从多个叶子节点中选择最高分节点，验证选中节点的 quality_score 最高
- [x] 15.2 测试无有效解时返回失败结果，验证 ExecutionResult 的 success=False 且包含错误信息
- [x] 15.3 测试最终代码提取正确，验证返回的代码与最佳节点的 code_snippet 一致

## 16. 单元测试 - 端到端

- [x] 16.1 测试完整的 execute 流程（使用 mock LLM），验证返回 ExecutionResult 且包含 iterations 记录
- [x] 16.2 测试 BFS 和 DFS 模式下的完整执行，验证两种模式都能正常完成搜索
- [x] 16.3 测试预算耗尽时的处理，验证能够正确捕获 BudgetExhausted 异常并返回结果

## 17. 测试覆盖率验证

- [x] 17.1 运行 pytest 并生成覆盖率报告，验证 tree_of_thoughts.py 的测试覆盖率 >= 90%
- [x] 17.2 检查未覆盖的分支和行，添加必要的测试用例覆盖边界情况，验证覆盖率达标

## 18. 代码质量检查

- [x] 18.1 运行 mypy 类型检查，验证无类型错误
- [x] 18.2 运行 ruff 或项目配置的 linter，验证代码符合项目风格规范
- [x] 18.3 运行 radon 复杂度分析（如果项目启用），验证关键方法复杂度在合理范围内

## 19. 文档与示例

- [x] 19.1 在 tree_of_thoughts.py 中添加模块和类的 docstring，验证文档清晰描述策略用途和参数
- [x] 19.2 为关键方法添加 docstring，说明参数、返回值和行为，验证 docstring 完整且格式正确
- [x] 19.3 创建或更新配置示例文档，展示 ToT 策略的配置方式，验证示例配置可以被项目正确解析
