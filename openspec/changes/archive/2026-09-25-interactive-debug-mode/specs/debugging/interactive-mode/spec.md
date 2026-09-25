## Purpose

提供交互式调试模式，允许开发者单步执行单个问题的求解过程，实时查看和干预模型推理，以便深入理解模型行为和快速验证策略改进。

## ADDED Requirements

### Requirement: 单题运行模式
系统 SHALL 支持通过 CLI 命令运行单个问题的调试会话，指定问题、策略和模型。

#### Scenario: 启动调试会话
- **WHEN** 用户执行 `harness debug --problem <problem_id> --strategy <strategy_name> --model <model_name>`
- **THEN** 系统启动交互式调试会话，显示问题信息和初始提示

#### Scenario: 无效问题 ID
- **WHEN** 用户指定的问题 ID 不存在
- **THEN** 系统显示错误信息并列出可用的问题 ID

### Requirement: 逐步显示执行过程
系统 SHALL 在每轮迭代中显示 prompt、LLM 响应、代码执行结果和测试反馈。

#### Scenario: 显示迭代详情
- **WHEN** 策略完成一轮迭代
- **THEN** 系统按顺序显示该轮的 prompt 内容、LLM 完整响应、执行的代码、执行结果和测试用例反馈

#### Scenario: 格式化输出
- **WHEN** 显示各类执行信息
- **THEN** 系统使用清晰的分隔符和标题区分不同部分，代码部分使用语法高亮

### Requirement: 断点控制
系统 SHALL 支持在策略关键步骤（生成代码后、执行测试前、收到反馈后）设置断点暂停执行。

#### Scenario: 在断点暂停
- **WHEN** 执行到达已启用的断点位置
- **THEN** 系统暂停执行并显示断点信息，等待用户命令

#### Scenario: 启用和禁用断点
- **WHEN** 用户执行 `break <location>` 或 `unbreak <location>` 命令
- **THEN** 系统启用或禁用指定位置的断点，其中 location 可以是 `generate`、`execute` 或 `feedback`

### Requirement: 单步执行命令
系统 SHALL 支持单步执行命令：`next`（执行下一步）、`continue`（继续到下一断点）、`skip`（跳过当前步骤）。

#### Scenario: 执行 next 命令
- **WHEN** 用户在暂停状态输入 `next`
- **THEN** 系统执行一个步骤并再次暂停，显示执行结果

#### Scenario: 执行 continue 命令
- **WHEN** 用户在暂停状态输入 `continue`
- **THEN** 系统继续执行直到遇到下一个断点或完成

#### Scenario: 执行 skip 命令
- **WHEN** 用户在暂停状态输入 `skip`
- **THEN** 系统跳过当前步骤，继续执行下一步

### Requirement: 手动编辑 prompt
系统 SHALL 允许用户在暂停时编辑下一轮的 prompt 内容。

#### Scenario: 编辑 prompt
- **WHEN** 用户执行 `edit-prompt` 命令
- **THEN** 系统打开默认编辑器显示当前 prompt，用户保存退出后使用修改后的 prompt 继续

#### Scenario: 编辑器不可用
- **WHEN** 系统无法打开编辑器
- **THEN** 系统在终端内提供多行输入模式，允许用户输入新的 prompt

### Requirement: 调整策略参数
系统 SHALL 支持在调试会话中动态修改策略参数（如 temperature、max_rounds）。

#### Scenario: 设置参数
- **WHEN** 用户执行 `set <param> <value>` 命令
- **THEN** 系统更新指定参数并确认修改，后续执行使用新参数值

#### Scenario: 无效参数
- **WHEN** 用户设置的参数名称不存在或值类型不匹配
- **THEN** 系统显示错误信息和该参数的有效值范围

### Requirement: 插入自定义提示
系统 SHALL 允许用户在下一轮执行前注入额外的提示文本。

#### Scenario: 注入提示
- **WHEN** 用户执行 `inject "<text>"` 命令
- **THEN** 系统将该文本添加到下一轮 prompt 的末尾，并在发送前显示完整 prompt 预览

### Requirement: 执行轨迹可视化
系统 SHALL 在调试过程中持续显示推理链路摘要，包括轮次、操作、结果状态。

#### Scenario: 显示轨迹摘要
- **WHEN** 用户执行 `trace` 命令
- **THEN** 系统显示所有已完成轮次的摘要，包括轮次编号、操作类型（Generate/Execute/Refine）和结果状态（Passed/Failed/Error）

#### Scenario: 查看轮次详情
- **WHEN** 用户执行 `trace <round_number>` 命令
- **THEN** 系统显示指定轮次的完整详情，包括 prompt、响应、执行结果和用户干预记录

### Requirement: 轨迹导出
系统 SHALL 支持将完整执行轨迹导出为 JSON 文件，包括所有轮次的 prompt、响应、执行结果和用户干预。

#### Scenario: 导出轨迹
- **WHEN** 用户执行 `export <filepath>` 命令或启动时指定 `--trace-output <filepath>`
- **THEN** 系统将完整轨迹保存为 JSON 文件，包含结构化的轮次数据和元信息

#### Scenario: 导出路径无效
- **WHEN** 指定的导出路径不可写
- **THEN** 系统显示错误信息并建议有效的导出位置

### Requirement: 退出调试会话
系统 SHALL 支持退出命令，并在退出前询问是否保存轨迹。

#### Scenario: 正常退出
- **WHEN** 用户执行 `exit` 或 `quit` 命令
- **THEN** 系统询问是否保存轨迹，根据用户选择保存后退出

#### Scenario: 策略完成后自动提示
- **WHEN** 策略执行完成（成功或达到最大轮次）
- **THEN** 系统显示完成信息和最终结果，询问用户是否退出或重新运行
