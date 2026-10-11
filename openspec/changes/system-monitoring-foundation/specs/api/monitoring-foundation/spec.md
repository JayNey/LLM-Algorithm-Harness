## ADDED Requirements

### Requirement: 管理员与所有者隔离
系统 SHALL 使用操作者配置的用户 UUID 白名单授权系统级监控，并只允许所有者查询任务日志与自身配额。

#### Scenario: 客户端伪造管理员
- **WHEN** 普通用户修改用户名或 Token 角色为管理员
- **THEN** 系统端点仍返回 403，不提升权限

### Requirement: 真实状态与未配置依赖
系统 SHALL 查询当前 SQLite、主机资源、Docker 预检和实际 API 统计；尚未配置的业务数据库、Redis、worker 和真实 LLM 指标 SHALL 明确返回 not_configured/null。

#### Scenario: 无队列后端
- **WHEN** #149 尚未接入
- **THEN** 不报告 Redis/worker 健康或虚构任务负载

### Requirement: 持久化安全日志
系统 SHALL 在入库前脱敏日志，支持级别、时间、搜索、分页与下载，并限制保留期、行数和记录大小。

#### Scenario: 秘钥与跨用户日志
- **WHEN** 可信 worker 提交包含凭据的用户 A 任务事件
- **THEN** 存储与下载均脱敏，用户 B 无法读取该任务日志

### Requirement: 统计完整性
系统 SHALL 使用实际最终响应统计 API，并明确样本保留/窗口是否完整；无法推导的指标 SHALL 为 null。

#### Scenario: 截断窗口
- **WHEN** 请求样本淘汰或采集时间短于查询窗口
- **THEN** 标记不完整，不把保留样本伪装为完整请求率
