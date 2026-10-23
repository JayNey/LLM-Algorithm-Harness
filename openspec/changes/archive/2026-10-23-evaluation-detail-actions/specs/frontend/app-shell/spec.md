## ADDED Requirements

### Requirement: 真实评估详情与受支持操作

已登录用户 SHALL 能直接访问和刷新 `/evaluations/:evaluationId`，通过现有认证客户端读取任务模型、策略、状态、预算、成本、失败原因与服务端进度。页面 SHALL 区分可启动与已入队的 pending、running、paused、completed、failed、cancelled，未知状态 SHALL 保留原值。页面挂载和刷新 MUST NOT 自动启动任务。

#### Scenario: 直接访问与刷新
- **WHEN** 用户直接打开详情或刷新页面
- **THEN** 页面 GET 对应 evaluation_id 的快照并显示真实字段，不依赖创建回执，不发送 POST。

#### Scenario: 按能力启动和取消
- **WHEN** 快照允许 can_start 或 can_cancel 且用户执行对应动作
- **THEN** 页面通过共享协调器互斥执行真实动作，响应后 GET 最新快照，不把 HTTP 接受等同于 running 或 cancelled。

#### Scenario: 动作失败与完成竞争
- **WHEN** 启动或取消失败，或取消与完成竞争
- **THEN** 保留任务 ID，显示失败信息并重新 GET，使用实际终态而非本地模拟成功；启动重试只核对与启动，不重新创建。

#### Scenario: 加载与权限失败
- **WHEN** 初始 GET 失败或返回 403/404
- **THEN** 页面显示可重试错误，不显示伪造数据或动作；同 ID 的暂时刷新失败保留快照并提示其未更新，403/404 清除快照。

#### Scenario: 会话与路由隔离
- **WHEN** 用户更换身份、任务 ID 或卸载页面后旧响应迟到
- **THEN** 旧数据和旧错误不能覆盖新任务或新会话，旧动作不能继续发送请求。
