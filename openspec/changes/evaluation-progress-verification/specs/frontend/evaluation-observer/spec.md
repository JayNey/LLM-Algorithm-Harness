## MODIFIED Requirements

### Requirement: 终态、权限与会话生命周期

快照状态到达终态或 paused SHALL 停止自动观察并发出结算事件；WS 4403 或 HTTP 403/404 SHALL 清空数据并停止且不得重试（不存在与否不得成为可判定的 oracle）；401/4401 SHALL 先经 recoverSession 复用既有会话刷新，失败 SHALL 停止并发出未授权事件；隐藏或离线 SHALL 暂停全部定时器与连接，恢复 SHALL 立即刷新并重连且重连计数清零；runMutation SHALL 递增操作纪元使旧周期结果作废；dispose SHALL 保证此后无任何回调。React 显示层 SHALL 同步清除已拒绝数据，且手动刷新和动作后的 HTTP 真值 SHALL 不被旧 live 快照遮蔽。

#### Scenario: 权限拒绝清理数据

- **WHEN** 订阅被 4403 关闭或快照请求返回 403/404
- **THEN** 观察器清空数据、停止观察且不重试，不区分资源不存在与无权限

#### Scenario: 变更纪元作废旧结果

- **WHEN** runMutation 包裹的启动/取消执行期间有旧周期快照返回
- **THEN** 该过期结果被丢弃，不进入 onChange 快照事件

#### Scenario: 卸载后无回调

- **WHEN** dispose 后假时钟推进或假 socket 注入帧
- **THEN** 观察器不产生任何 onChange 回调或网络帧

#### Scenario: React 权限清理
- **WHEN** 已展示的详情随后收到HTTP403/404或WS4403
- **THEN** 旧的一次性和live数据均不得继续显示，动作入口撤下，显式重试仅使用新HTTP结果，成功恢复pending/running后重新订阅并继续自动更新，paused/终态仍停止

#### Scenario: 页面动作与刷新协调
- **WHEN** 页面手动刷新、启动或取消
- **THEN** 活动观察器协调刷新与动作纪元，旧请求不可覆盖动作后的新HTTP状态；终态或尚未启动观察时保留一次性读取
