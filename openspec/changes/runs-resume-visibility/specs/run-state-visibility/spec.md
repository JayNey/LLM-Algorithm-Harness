# run-state-visibility Specification

## Purpose

让断点续传的运行状态可运维：列出输出目录下的任务运行及其完成进度与累计成本，在启动新评估时提示指纹匹配的未完成运行，并提供已完成运行状态文件的清理命令。TaskService 的持久化与 resume 语义不变。

## ADDED Requirements

### Requirement: 运行列表

系统 SHALL 提供 `harness runs list`：输出输出目录下各任务运行的 run_id、状态、完成进度（completed/total）、累计已知定价成本、最近更新时间，按更新时间倒序；默认仅显示未完成（可恢复）的运行，`--all` 显示全部；成本仅累计定价与 usage 已知的调用，usage 未知的结果单独计数呈现。

#### Scenario: 列出可恢复运行

- **WHEN** 输出目录存在一个完成与一个中断（paused）的运行
- **THEN** 默认列表仅含中断运行及其进度、成本与更新时间，`--all` 时两者都出现

#### Scenario: 成本口径

- **WHEN** 某运行的已完成单元中存在 usage 未知的结果
- **THEN** 其成本只累计已知定价部分，unknown 计数单独呈现

### Requirement: 启动时未完成运行提示

`harness run` 在未指定 `--resume` 启动新评估时，系统 SHALL 检测输出目录中 config 与 dataset 指纹均匹配的未完成运行，并打印提示（run_id、进度与恢复命令建议）；提示 SHALL NOT 阻塞或改变执行行为。

#### Scenario: 提示匹配的未完成运行

- **WHEN** 以与某中断运行相同的配置和题库启动新评估
- **THEN** 启动输出包含该 run_id、其进度与 `--resume --run-id` 建议，评估照常开始

#### Scenario: 无匹配不提示

- **WHEN** 不存在指纹匹配的未完成运行
- **THEN** 启动输出不含恢复提示

### Requirement: 已完成运行清理

系统 SHALL 提供 `harness runs clean`：仅删除已完成（completed）运行的任务状态文件；未完成运行 SHALL 不被删除；默认逐个确认，`--force` 跳过确认。

#### Scenario: 清理范围

- **WHEN** 存在已完成与未完成的运行并执行 `harness runs clean --force`
- **THEN** 仅已完成运行的状态文件被删除，未完成运行的保留且仍可 `--resume`

#### Scenario: 确认模式

- **WHEN** 无 `--force` 且用户对每个文件应答 N
- **THEN** 不删除任何文件
