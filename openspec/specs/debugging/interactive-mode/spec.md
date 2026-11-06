# debugging/interactive-mode Specification

## Purpose
提供交互式调试模式，允许开发者单步执行单个问题的求解过程，实时查看和干预模型推理，以便深入理解模型行为和快速验证策略改进。

## Requirements

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
系统 SHALL 支持在生成响应后、调用沙箱前、收到沙箱反馈后设置断点暂停执行。

#### Scenario: 在断点暂停
- **WHEN** 执行到达已启用的断点位置
- **THEN** 系统暂停并展示该轮可用的响应、代码或反馈，等待用户命令

#### Scenario: 启用和禁用断点
- **WHEN** 用户执行 `break <location>` 或 `unbreak <location>` 命令
- **THEN** 系统启用或禁用 `generate`、`execute` 或 `feedback` 断点

### Requirement: 单步执行命令
系统 SHALL 支持从初始提示启动单步执行，并在运行时单步、继续或跳过暂停点对应的处理。

#### Scenario: 执行 next 命令
- **WHEN** 用户在初始提示或断点输入 `next`
- **THEN** 系统启动或推进策略至下一个调试位置并暂停，策略已结束时返回初始提示

#### Scenario: 执行 continue 命令
- **WHEN** 用户在断点输入 `continue`
- **THEN** 系统继续至下一个已启用的断点或策略结束

#### Scenario: 执行 skip 命令
- **WHEN** 用户在生成、执行或反馈断点输入 `skip`
- **THEN** 系统分别跳过当前响应的后续处理、当前沙箱调用或当前反馈暂停，并继续运行

### Requirement: 手动编辑 prompt
系统 SHALL 允许用户在暂停时编辑下一轮的 prompt 内容。

#### Scenario: 编辑 prompt
- **WHEN** 用户执行 `edit-prompt` 命令
- **THEN** 系统打开默认编辑器显示当前 prompt，用户保存退出后使用修改后的 prompt 继续

#### Scenario: 编辑器不可用
- **WHEN** 系统无法打开编辑器
- **THEN** 系统在终端内提供多行输入模式，允许用户输入新的 prompt

### Requirement: 调整策略参数
系统 SHALL 支持调试会话内覆盖 `temperature` 和 `max_tokens`，以及为支持多轮反馈的策略设置 `max_rounds`。

#### Scenario: 设置参数
- **WHEN** 用户设置受支持的参数
- **THEN** 新采样参数从下一次模型请求起持续生效，`max_rounds` 从下一次策略启动起生效

#### Scenario: 无效参数
- **WHEN** 用户设置不支持的参数或提交无效值
- **THEN** 系统显示有效参数及其范围，并保留已有覆盖值

### Requirement: 插入自定义提示
系统 SHALL 允许用户在下一轮执行前注入额外的提示文本。

#### Scenario: 注入提示
- **WHEN** 用户执行 `inject "<text>"` 命令
- **THEN** 系统将该文本添加到下一轮 prompt 的末尾，并在发送前显示完整 prompt 预览

### Requirement: 执行轨迹可视化
系统 SHALL 显示实际模型调用和随后发生的沙箱操作，每次模型请求开始一个轮次。

#### Scenario: 显示轨迹摘要
- **WHEN** 用户执行 `trace` 命令
- **THEN** 系统显示已记录的轮次、操作和状态，包括断点处进行中的轮次

#### Scenario: 查看轮次详情
- **WHEN** 用户执行 `trace <round_number>` 命令
- **THEN** 系统显示该轮已取得的提示、完整响应、沙箱结果、反馈和用户干预，按项目规则脱敏

### Requirement: 轨迹导出
系统 SHALL 将真实模型调用、相关沙箱结果及用户干预作为结构化轮次记录，显示和导出前使用项目的凭据脱敏规则。

#### Scenario: 导出轨迹
- **WHEN** 用户执行 `export <filepath>` 命令或启动时指定 `--trace-output <filepath>`
- **THEN** 系统将轨迹保存为 JSON 文件，包含已取得的提示、响应、代码、沙箱结果、反馈、干预与元信息

#### Scenario: 导出路径无效
- **WHEN** 指定的导出路径不可写
- **THEN** 系统显示错误信息并提示指定可写路径

### Requirement: 退出调试会话
系统 SHALL 支持从初始提示或任一断点退出整个会话。

#### Scenario: 正常退出
- **WHEN** 用户输入 `exit` 或 `quit`
- **THEN** 系统停止会话且不再调用模型或沙箱，存在轨迹时按用户选择保存，已指定自动导出路径时直接保存

#### Scenario: 策略完成后自动提示
- **WHEN** 策略执行完成
- **THEN** 系统显示完成信息并返回初始提示，允许查看轨迹或重新运行

### Requirement: 运行结果摘要
调试会话 SHALL 区分策略正常返回和策略抛出异常。正常返回时，摘要显示结果的成功状态和实际迭代轮数。

#### Scenario: 成功或答错
- **WHEN** 用户执行 `run` 且策略正常返回成功或答错的结果
- **THEN** 会话显示执行完成、成功状态和实际迭代轮数，随后可查询和导出执行轨迹

#### Scenario: 零轮结果
- **WHEN** 用户执行 `run` 且策略正常返回未发生迭代的结果
- **THEN** 会话显示执行完成、结果的成功状态和零轮

#### Scenario: 策略抛出异常
- **WHEN** 用户执行 `run` 且策略抛出异常
- **THEN** 会话显示执行失败和脱敏后的异常信息，并返回调试提示符
