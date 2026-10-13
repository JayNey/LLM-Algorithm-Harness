## ADDED Requirements

### Requirement: 管理员与所有者隔离
系统 SHALL 使用操作者配置的用户 UUID 白名单授权系统级监控，并只允许所有者查询任务日志与自身配额。

#### Scenario: 客户端伪造管理员
- **WHEN** 普通用户修改用户名或 Token 角色为管理员
- **THEN** 系统端点仍返回 403，不提升权限

### Requirement: 真实状态与未配置依赖
系统 SHALL 查询当前认证/文件 SQLite、已有业务 engine、主机资源、Docker 预检和实际 API 统计；已接入但未联网探测的 Redis/worker SHALL 返回 not_checked，尚未采集的真实 LLM 指标 SHALL 明确返回 not_configured/null。

#### Scenario: 无队列后端
- **WHEN** #149 尚未接入
- **THEN** 不报告 Redis/worker 健康或虚构任务负载

#### Scenario: 存在队列基础但执行仍模拟
- **WHEN** main 已有 Celery/AsyncTask，而 worker 仍返回 mock 结果
- **THEN** 保留任务 router/会话生命周期，按来源独立分页与全量计数、关联记录不双计；只返回数值进度，不提交状态或轮询后端；明确未探测网络与模拟评估边界

#### Scenario: 三类新增任务入口
- **WHEN** 导入任务提供 current/total 加自由消息，或实验/基准任务没有数值进度
- **THEN** 只返回校验后的数值对，没有该数值对时为 null，不暴露消息、错误或凭据，不凭状态虚构完成比例；不把任务入口存在当作端到端真实执行可用

#### Scenario: 已接入业务数据库
- **WHEN** #151 已配置业务 engine，任务处于 pending/running
- **THEN** 监控读取连通性/业务表/迁移版本与持久化分页快照，不重新创建服务、不迁移、不改变任务状态，数据库失败返回不可用及空值

### Requirement: 有界查询性能采集
系统 SHALL 从运行中的 SQLAlchemy engine 采集真实查询次数、错误与耗时，明确进程和窗口范围，不保存 SQL/参数/连接凭据，监听故障 SHALL 不影响业务执行。

#### Scenario: 失败与截断窗口
- **WHEN** 实际查询失败，或采集不足/淘汰/采集缺口造成窗口不完整
- **THEN** 保留真实失败测量并原样传递业务异常；不完整窗口主指标为 null，样本另行展示，服务关闭停止采集并释放采集器引用，固定转发监听随 engine 生命周期结束回收

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
