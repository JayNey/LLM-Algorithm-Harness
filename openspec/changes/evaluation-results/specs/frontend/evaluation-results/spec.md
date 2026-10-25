## ADDED Requirements

### Requirement: 当前用户真实结果列表
前端 SHALL 使用共享认证客户端的results接口展示当前用户结果，以返回id作为evaluation ID导航，run_id SHALL NOT 为详情入口的必要条件。状态筛选及limit/offset SHALL 保存在URL，筛选变更清零offset；加载、合法空页、失败与重试 SHALL 分别呈现，旧查询或旧账号响应不得替换当前数据。

#### Scenario: 筛选与分页
- **WHEN** 用户翻页、筛选状态并刷新
- **THEN** 请求只使用现有接口字段，URL和页面保持一致，筛选后回到首页

#### Scenario: 未关联run仍可访问
- **WHEN** 列表条目的run_id为null
- **THEN** 仍可通过evaluation ID访问和刷新结果详情

### Requirement: 全量策略汇总与单题分页
结果详情 SHALL 直接展示服务端全量strategies汇总，与当前problems页独立；单题记录 SHALL 以problem_id和strategy联合标识并显示实际状态。百分率 SHALL 乘100，执行耗时 SHALL 使用秒，null指标 SHALL 显示未知，未知成本 SHALL 明确标记未知部分。页面 SHALL NOT 推造代码、输出或单题错误。

#### Scenario: 跨页统计不截断
- **WHEN** 仅当前单题页变化
- **THEN** 策略总量、成功率和费用保持服务端全量统计，同题不同策略记录均存在

#### Scenario: 缺失度量
- **WHEN** 单题指标为null或策略unknown_cost_count非零
- **THEN** 区分未知与零，已知费用不冒充完整费用，原始未知状态仍可读

### Requirement: 联合快照与异步隔离
活动结果详情 SHALL 复用同一ProgressObserver，以一个周期并行读取任务和当前结果页，服务端事件只触发失效；周期 SHALL 遵守既有合并/无并发/退避规则。结果读取失败 SHALL 保留独立resultError而不丢弃成功任务；权限拒绝、换页、换任务/账号和卸载 SHALL 不显示迟到或被拒绝的数据。手动重试成功后 SHALL 恢复活动任务观察。

#### Scenario: 事件刷新两个接口
- **WHEN** WS事件合并窗口到期
- **THEN** 同周期获取任务与结果HTTP真值，周期不重叠且WS载荷不直接改结果

#### Scenario: 结果独立失败与恢复
- **WHEN** 结果接口失败而任务请求成功
- **THEN** 页面保留任务事实，显示结果错误，显式重试可恢复结果

#### Scenario: 分页和权限清理
- **WHEN** 旧分页/任务/账号请求迟到，或任务HTTP403/404/WS4403拒绝访问
- **THEN** 旧结果不出现在新上下文，被拒绝任务和结果均被清除
