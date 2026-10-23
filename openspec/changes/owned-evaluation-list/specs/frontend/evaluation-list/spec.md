## ADDED Requirements

### Requirement: 当前会话的真实评估列表
页面 SHALL 使用既有认证客户端查询评估列表，展示接口提供的 ID、模型、策略、状态、执行进度及费用，不展示 Mock 行或虚构名称。

#### Scenario: 加载和合法空集
- **WHEN** 请求尚未返回或成功返回空页
- **THEN** 分别显示加载状态或带创建入口的空态，不将错误显示为空集

#### Scenario: 非空页和未知状态
- **WHEN** 返回包含未知状态的真实任务页
- **THEN** 保留任务 ID 与服务端进度，明确显示未知状态，详情链接使用 evaluation_id

### Requirement: URL 筛选与分页
列表 SHALL 从 URL 的 status/limit/offset 派生查询，支持刷新、前进后退、状态筛选清零 offset 和超页恢复。

#### Scenario: 筛选和翻页
- **WHEN** 在第二页切换状态
- **THEN** 请求只包含支持的查询参数，新状态 offset 为 0，URL 与页面一致

#### Scenario: 数据缩减造成超页
- **WHEN** 成功响应的 total 不足以覆盖当前 offset
- **THEN** 替换 URL 为最后有效页并请求该页；total 为 0 时回到 offset=0

### Requirement: 异步与身份隔离
加载器 SHALL 取消旧请求并拒绝旧查询、旧身份及已卸载页面的迟到结果；重试 SHALL 保留当前查询。

#### Scenario: 旧查询或旧身份迟到
- **WHEN** 旧 Promise 在新查询或新会话响应之后才完成，即使忽略 AbortSignal
- **THEN** 旧结果不得覆盖或短暂显示在当前页面

#### Scenario: 错误和重试
- **WHEN** 当前请求失败且用户重试
- **THEN** 显示独立错误，重试同一查询，并仅在实际成功后显示数据
