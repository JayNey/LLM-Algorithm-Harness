## ADDED Requirements

### Requirement: 监控交付状态与部署健康分离
系统 SHALL 保留管理员健康响应的pending_issues数组，在#157列明的代码能力已具备后返回空数组；该数组 SHALL NOT 被当作当前部署健康或完整集群就绪的证明。部署禁用、未检查、不可用和部分回复 SHALL 继续通过各checks和partial/degraded表达，未测模型执行就绪 SHALL 保持null。公开liveness与管理员权限边界 SHALL 保持。

#### Scenario: 未启用外部探测
- **WHEN** 代码能力已交付但队列/沙箱未启用或未检查
- **THEN** pending_issues为空，总体仍为partial，检查仍not_checked且模型就绪仍null

#### Scenario: 依赖实际失败
- **WHEN** 数据库或其他已配置探针报告unavailable/unknown
- **THEN** 总体仍为degraded，空pending_issues不得将其改成healthy，响应不回显原异常
