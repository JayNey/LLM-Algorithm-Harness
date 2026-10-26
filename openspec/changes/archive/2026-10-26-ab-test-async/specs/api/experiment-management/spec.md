## MODIFIED Requirements
### Requirement: A/B 测试管理
系统 SHALL 支持 A/B 测试的创建/详情/异步运行/结果查询，运行经 Celery worker 中的 `ABTestRunner`（client/sandbox 工厂可注入），结果含显著性检验；配置与状态持久化且 owner 隔离。运行接口 SHALL 返回统一任务标识 task_id，详情 SHALL 返回同一关联标识，排队和执行状态 SHALL 可通过已有任务接口查询。

#### Scenario: 跨用户资源隔离
- **WHEN** 用户 B 请求用户 A 的实验/基准/A-B 资源
- **THEN** 返回 404，列表不包含他人资源。

#### Scenario: 运行返回统一任务
- **WHEN** 用户运行自己的 pending A/B 测试
- **THEN** 返回 202 与 task_id，详情保留该标识，任务可通过统一接口查询。
