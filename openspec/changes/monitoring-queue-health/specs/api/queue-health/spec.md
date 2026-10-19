## ADDED Requirements

### Requirement: 真实且受保护的队列观测
系统 SHALL 仅允许服务端授权管理员读取队列健康和 worker 负载，并通过配置显式启用网络探测。成功 SHALL 来源于实际 Redis PING 或 worker 回复；没有观测到的值 SHALL 为 null。

#### Scenario: 禁用或未经授权
- **WHEN** 未启用网络探测或请求者不具备管理员权限
- **THEN** 不访问 broker；禁用返回 not_checked，未授权请求返回 401/403

#### Scenario: 成功及缺失观测
- **WHEN** broker 和 worker 正常回复，或 worker 没有回复/不支持命令
- **THEN** 返回实际数值和回复范围；无回复为 unknown，不支持为 partial，不虚构零负载或集群完整性

### Requirement: 有界与安全的探测生命周期
系统 SHALL 对整个网络探测施加时间和并发上限，缓存须说明年龄；超时和服务关闭 SHALL 终止并回收进程。探测 SHALL NOT 修改任务状态或泄露连接凭据、参数、任务 ID、原始异常和主机名。

#### Scenario: 卡住、并发和关闭
- **WHEN** 网络调用卡住、多个请求同时刷新，或服务关闭
- **THEN** 请求在配置的预算内结束、单类只运行一个探测，进行中的进程被清理，不持续积累后台任务

#### Scenario: 非可信回复和错误
- **WHEN** worker 回复包含额外敏感字段、非法计数或探测异常
- **THEN** 仅接受有界整数计数和固定状态；不返回自由文本或凭据，不将异常记为健康

### Requirement: 能力与运行状态分开
系统 SHALL 准确说明代码已接入 AlgorithmHarness，且单次健康回复不能证明模型或沙箱执行就绪；指标尚未采集时 SHALL 标明 #157 的待接入范围。

#### Scenario: worker 在线
- **WHEN** worker 回复健康与计数
- **THEN** 仅表明其本次回复及负载，不把它解释为真实 LLM 成功率或执行就绪证明
