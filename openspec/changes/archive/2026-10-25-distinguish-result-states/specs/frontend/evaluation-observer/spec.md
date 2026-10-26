## ADDED Requirements

### Requirement: 联合结果可用性与错误隔离
前端 SHALL 独立展示任务原因、结果存在性、完整性与请求错误；ResultAvailability SHALL 区分 waiting/partial/paused/failed/cancelled/complete/incomplete/empty，并保留 unknown 表达未确认状态。请求失败 SHALL NOT 被当作 empty。权限错误 SHALL 清除整个资源快照。

#### Scenario: 状态与结果存在性矩阵
- **WHEN** pending/running/paused/failed/cancelled/completed 任务分别具有零条或非零结果
- **THEN** pending/running 无记录显示 waiting、有记录显示 partial；paused/failed/cancelled 保留状态与记录数；completed 零记录 empty、少于预期 incomplete、达到预期 complete

#### Scenario: 请求错误和权限清理
- **WHEN** task200/result503 或任一资源读取403/404
- **THEN** 前者保留任务事实并显示独立结果错误；后者清除整个资源缓存，不发布并行取得的数据，不被旧 bootstrap/live 缓存复活

#### Scenario: 单次终态补读
- **WHEN** 任务与结果的终态读取发生短暂跨事务分歧
- **THEN** 在同一观察周期最多补读一次结果；仍分歧显示未确认并允许手动重试，不能冒充完成或空数据
