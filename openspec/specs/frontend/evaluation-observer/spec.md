# frontend/evaluation-observer Specification

## Purpose
TBD - created by archiving change evaluation-observer. Update Purpose after archive.

## Requirements

### Requirement: 评估进度观察生命周期

前端 SHALL 提供依赖注入式的进度观察器（`createProgressObserver(deps)`），以 WebSocket 订阅为主通道、HTTP 快照为唯一真值：服务端事件 SHALL 仅触发失效而不直接修改状态；失效 SHALL 在 2 秒合并窗口内至多发起一次快照刷新；任意时刻 SHALL 至多存在一个进行中的快照请求，进行中到达的失效 SHALL 在请求完成后补刷一次。原生 WebSocket SHALL 仅在 React 适配器创建，认证 SHALL 依靠 Cookie 且 token SHALL NOT 出现在连接 URL 中。

#### Scenario: 事件合并为单次刷新

- **WHEN** 观察器处于 live 模式且合并窗口内连续到达多个服务端事件
- **THEN** 窗口到期后至多发起一次快照刷新，且刷新结果经 onChange 以快照事件交付

#### Scenario: 进行中失效补刷一次

- **WHEN** 快照请求进行中到达新的失效
- **THEN** 该请求完成后至多补刷一次，不产生并发请求周期

### Requirement: 受控降级与有限重连

WebSocket 订阅发出后 5 秒未确认 SHALL 视为失败；非 live 模式 SHALL 以 3 秒间隔降级轮询 HTTP 快照；WS 重连 SHALL 按 3/6/12/30 秒退避进行且至多尝试 5 次，成功 SHALL 清零计数，放弃后 SHALL 保持降级轮询；HTTP 429 SHALL 使至少 30 秒内不发起任何请求；live 模式下 15 秒无事件且快照非终态 SHALL 主动刷新一次以收敛漏事件。

#### Scenario: 订阅超时进入退避

- **WHEN** subscribe 发出后 5 秒内未收到 subscribed 帧
- **THEN** 关闭连接，按退避序列计划下一次重连，期间以 3 秒间隔轮询 HTTP 快照

#### Scenario: 漏终态经 HTTP 收敛

- **WHEN** WS 在终态事件发出前断开，live 兜底或降级轮询取得快照
- **THEN** 观察器依据 HTTP 真值识别终态并停止自动观察

### Requirement: 终态、权限与会话生命周期

快照状态到达终态或 paused SHALL 停止自动观察并发出结算事件；WS 4403 或 HTTP 403/404 SHALL 清空数据并停止且不得重试（不存在与否不得成为可判定的 oracle）；401/4401 SHALL 先经 recoverSession 复用既有会话刷新，失败 SHALL 停止并发出未授权事件；隐藏或离线 SHALL 暂停全部定时器与连接，恢复 SHALL 立即刷新并重连且重连计数清零；runMutation SHALL 递增操作纪元使旧周期结果作废；dispose SHALL 保证此后无任何回调。

#### Scenario: 权限拒绝清理数据

- **WHEN** 订阅被 4403 关闭或快照请求返回 403/404
- **THEN** 观察器清空数据、停止观察且不重试，不区分资源不存在与无权限

#### Scenario: 变更纪元作废旧结果

- **WHEN** runMutation 包裹的启动/取消执行期间有旧周期快照返回
- **THEN** 该过期结果被丢弃，不进入 onChange 快照事件

#### Scenario: 卸载后无回调

- **WHEN** dispose 后假时钟推进或假 socket 注入帧
- **THEN** 观察器不产生任何 onChange 回调或网络帧
