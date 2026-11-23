## MODIFIED Requirements

### Requirement: 受控降级与有限重连

WebSocket 订阅发出后 5 秒未确认 SHALL 视为失败；同步连接失败（包括初始化期间报告错误或构造抛错）与异步失败 SHALL 统一进入 degraded，SHALL NOT 永久停在 connecting 或向调用方抛出构造异常。非 live 模式 SHALL 以 3 秒间隔降级轮询 HTTP 快照；WS 重连 SHALL 按 3/6/12/30 秒退避进行且至多尝试 5 次，成功 SHALL 清零计数，放弃后 SHALL 保持降级轮询；HTTP 429 SHALL 使至少 30 秒内不发起任何请求；live 模式下 15 秒无事件且快照非终态 SHALL 主动刷新一次以收敛漏事件。失败连接 SHALL 释放可用资源，失效连接后续事件 SHALL NOT 改变当前观察状态；dispose 后 SHALL 清理轮询和重连定时器。

#### Scenario: 订阅超时进入退避

- **WHEN** subscribe 发出后 5 秒内未收到 subscribed 帧
- **THEN** 关闭连接，按退避序列计划下一次重连，期间以 3 秒间隔轮询 HTTP 快照

#### Scenario: 漏终态经 HTTP 收敛

- **WHEN** WS 在终态事件发出前断开，live 兜底或降级轮询取得快照
- **THEN** 观察器依据 HTTP 真值识别终态并停止自动观察

#### Scenario: 初始化同步报告失败

- **WHEN** 连接初始化在返回连接句柄前同步报告错误
- **THEN** 进入 degraded，以 HTTP 轮询继续更新并按退避有限重连，返回的失败句柄被关闭

#### Scenario: 连接构造抛错

- **WHEN** 连接初始化直接抛出构造异常
- **THEN** 启动调用不抛出该异常，观察器进入 degraded，继续轮询并有限重连

#### Scenario: 失败通知去重与恢复

- **WHEN** 失败连接继续发出错误、关闭、打开或消息事件，随后一次重连正常订阅成功
- **THEN** 旧事件不重复计入失败或污染当前状态，新连接进入 live 并停止降级轮询

#### Scenario: 同步失败后卸载

- **WHEN** 同步失败已启动降级后执行 dispose，再推进时间或交付旧连接事件
- **THEN** 所有降级与重连定时器被清理，不再产生请求、连接、回调或网络帧
