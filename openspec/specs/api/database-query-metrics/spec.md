# api/database-query-metrics Specification

## Purpose
TBD - created by archiving change complete-database-monitoring-scope. Update Purpose after archive.

## Requirements

### Requirement: 数据库查询采集范围
系统 SHALL 在现有 performance 响应中保留评估统计，并列出当前 API 实例绑定的评估、结果、实验、基准、A/B、成本和异步任务 engine，以及认证/文件共享 SQLite 的查询性能来源；同一个连接对象 SHALL 只注册一次。

#### Scenario: 独立业务来源
- **WHEN** 各服务 engine 执行成功或失败的查询
- **THEN** 对应来源记录执行次数、延迟和错误，且不混入另一来源的统计

#### Scenario: 共享 SQLite 与进程边界
- **WHEN** 认证或文件通过共享 AuthStore 执行查询
- **THEN** 共享来源仅计一次，响应列出用途、backend、进程 ID，并明确不覆盖其他 API/Celery 进程

### Requirement: 采集可靠性与隐私
系统 SHALL 延续有界保留及不完整窗口返回 null 的规则，不保存 SQL、参数、URL、路径或异常正文；采集故障 SHALL 不改变查询结果、事务和原异常。

#### Scenario: 失败与关闭
- **WHEN** SQLite 查询失败、采集记录失败或监控关闭
- **THEN** 原查询语义保持，失败样本或采集缺口可见，关闭后不再记录新查询
