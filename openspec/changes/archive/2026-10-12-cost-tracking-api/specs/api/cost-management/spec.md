## ADDED Requirements

### Requirement: 成本查询聚合

系统 SHALL 从既有业务表（evaluations/experiments/benchmark_runs/ab_tests）按 owner 作用域聚合成本：按 id 解析单任务成本、按时间段输出用户汇总、按日趋势序列与按来源类型/模型/策略的分解；时间段参数非法时 SHALL 返回 400。

#### Scenario: 跨表任务解析

- **WHEN** 以 benchmark run 的 id 请求任务成本
- **THEN** 返回该 run 的 cost_usd 与状态；以不存在的 id 请求返回 404

#### Scenario: 空时间段返回空序列

- **WHEN** 查询无任何花费记录的时间段
- **THEN** 汇总为 0、趋势与分解为空数组而非错误

### Requirement: 用户预算配置与使用情况

系统 SHALL 为每用户维护一份预算配置（全局上限、按难度分配、阈值行为 pause/downgrade），upsert 语义；使用情况 SHALL 返回全局 used/remaining/percentage 与按难度的比例估计（basis 字段注明估计口径）。

#### Scenario: 未配置预算的用量查询

- **WHEN** 用户未配置预算即查询使用情况
- **THEN** 返回 used 统计且 cap 为 null，而非错误

### Requirement: 预警规则与触发历史

系统 SHALL 支持预警规则的创建/更新/删除/列表（threshold_pct、channel、target），非法通道与越界阈值 SHALL 被拒绝；响应中的 webhook/邮件目标 SHALL 脱敏；触发历史 SHALL 从 alert_events 按 owner 返回。

#### Scenario: 非法规则被拒绝

- **WHEN** 提交 threshold_pct 为 0 或 channel 为未知值的规则
- **THEN** 返回 400 且不落库

#### Scenario: 目标脱敏

- **WHEN** 列出包含 webhook URL 的规则
- **THEN** 响应仅含脱敏后的目标（保留协议与主机）

### Requirement: 定价目录与覆盖版本

系统 SHALL 合并 PricingManager 内置定价、自定义文件与数据库覆盖行（覆盖优先）返回定价目录；自定义覆盖 SHALL 以追加版本方式入库（同 model 多行，最新生效）并支持追溯历史。

#### Scenario: 覆盖生效且可追溯

- **WHEN** 对同一 model 先后提交两次自定义定价
- **THEN** 目录查询返回最新版本，同时可查询到两条历史版本记录
