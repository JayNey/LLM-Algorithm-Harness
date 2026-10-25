## ADDED Requirements

### Requirement: 用户评估并发额度查询
系统 SHALL 在现有 GET /api/v1/quotas 和 GET /api/v1/quotas/usage 中向已认证用户返回 evaluation_concurrency.limit、used、remaining。limit SHALL 使用准入配置 MAX_CONCURRENT_EVALUATIONS_PER_USER；used SHALL 仅计当前用户持久化 AsyncTask 中 task_type=evaluation 且状态为 pending/running 的任务；remaining SHALL 等于 max(limit-used,0)。查询 SHALL 只读且不轮询 Celery，不通过请求参数选择其他用户，不把数据库失败伪装成零用量。

#### Scenario: 空闲与自定义限额
- **WHEN** 用户无活动评估且配置限额为 3
- **THEN** 两个配额别名均返回 limit=3、used=0、remaining=3

#### Scenario: 状态与所有者隔离
- **WHEN** 存在本人 pending/running 评估及其他用户任务、其他类型任务、草稿、paused/completed/failed/cancelled 任务
- **THEN** 仅本人 pending/running 评估占用额度，身份参数不能更改查询所有者

#### Scenario: 状态变化与超限历史
- **WHEN** 任务进入暂停或终态后重新查询，或已有活动任务数超过当前配置
- **THEN** 查询反映已提交状态；超限时 used 保留真实值且 remaining=0

#### Scenario: 未认证及只读查询
- **WHEN** 未认证调用配额别名，或已认证用户查询
- **THEN** 未认证返回 401；已认证查询不修改任务、不调用 Celery，响应禁用缓存
