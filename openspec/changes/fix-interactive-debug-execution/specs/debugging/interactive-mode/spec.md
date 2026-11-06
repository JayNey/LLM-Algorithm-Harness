## MODIFIED Requirements

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

### Requirement: 调整策略参数
系统 SHALL 支持调试会话内覆盖 `temperature` 和 `max_tokens`，以及为支持多轮反馈的策略设置 `max_rounds`。

#### Scenario: 设置参数
- **WHEN** 用户设置受支持的参数
- **THEN** 新采样参数从下一次模型请求起持续生效，`max_rounds` 从下一次策略启动起生效

#### Scenario: 无效参数
- **WHEN** 用户设置不支持的参数或提交无效值
- **THEN** 系统显示有效参数及其范围，并保留已有覆盖值

### Requirement: 轨迹导出
系统 SHALL 将真实模型调用、相关沙箱结果及用户干预作为结构化轮次记录，显示和导出前使用项目的凭据脱敏规则。

#### Scenario: 导出轨迹
- **WHEN** 用户执行 `export <filepath>` 命令或启动时指定 `--trace-output <filepath>`
- **THEN** 系统将轨迹保存为 JSON 文件，包含已取得的提示、响应、代码、沙箱结果、反馈、干预与元信息

#### Scenario: 导出路径无效
- **WHEN** 指定的导出路径不可写
- **THEN** 系统显示错误信息并提示指定可写路径

### Requirement: 执行轨迹可视化
系统 SHALL 显示实际模型调用和随后发生的沙箱操作，每次模型请求开始一个轮次。

#### Scenario: 显示轨迹摘要
- **WHEN** 用户执行 `trace` 命令
- **THEN** 系统显示已记录的轮次、操作和状态，包括断点处进行中的轮次

#### Scenario: 查看轮次详情
- **WHEN** 用户执行 `trace <round_number>` 命令
- **THEN** 系统显示该轮已取得的提示、完整响应、沙箱结果、反馈和用户干预，按项目规则脱敏

### Requirement: 退出调试会话
系统 SHALL 支持从初始提示或任一断点退出整个会话。

#### Scenario: 正常退出
- **WHEN** 用户输入 `exit` 或 `quit`
- **THEN** 系统停止会话且不再调用模型或沙箱，存在轨迹时按用户选择保存，已指定自动导出路径时直接保存

#### Scenario: 策略完成后自动提示
- **WHEN** 策略执行完成
- **THEN** 系统显示完成信息并返回初始提示，允许查看轨迹或重新运行
