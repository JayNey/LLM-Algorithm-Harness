## MODIFIED Requirements

### Requirement: 异步进度观察

实验进度 SHALL 经 `GET /tasks/{task_id}` 以固定间隔轮询（3 秒），到达终态（completed/failed/cancelled）SHALL 停止轮询，paused SHALL 停止轮询并保留最后进度；组件卸载、切换实验、切换任务关联或切换身份 SHALL 取消进行中的轮询和终态对账请求；连续轮询失败 SHALL 暂停并提供手动重试。前端 SHALL NOT 使用 WebSocket 观察实验进度（后端 /ws/progress 仅支持 evaluation）。

#### Scenario: 轮询至终态停止

- **WHEN** 任务进度轮询观察到终态状态
- **THEN** 轮询停止且界面立即展示最终状态。失败时展示当前关联任务返回的错误（如有），成功或取消时清除旧错误。前端 SHALL 为本次终态做一次实验详情读取以对账，保留已显示的终态直至服务端详情与当前任务终态一致。手动刷新页面 SHALL 展示服务端持久化的状态与失败原因。

#### Scenario: 迟到响应与当前详情隔离

- **WHEN** 用户切换实验、任务关联或身份，或离开详情页，而旧轮询或旧终态对账尚未结束
- **THEN** 旧响应 SHALL 无法更新当前详情页的状态或错误提示

#### Scenario: 连续失败暂停轮询

- **WHEN** 进度轮询连续多次失败
- **THEN** 轮询暂停并提供手动重试入口

前端 SHALL 优先通过实验响应 task_id 恢复排队任务，兼容旧响应时 SHALL 完整查询 pending/running/paused 分页；任务关联加载中或加载失败时 SHALL 禁止启动。已关联活动任务 SHALL 支持取消并禁止直接删除，终态 SHALL 允许删除。

#### Scenario: 刷新排队实验

- **WHEN** 刷新已提交但尚未执行的实验详情
- **THEN** 恢复原任务、显示等待调度、不可重复启动或直接删除，并可取消

#### Scenario: 旧响应分页与恢复失败

- **WHEN** 旧响应没有 task_id 字段且目标 pending 任务位于第二页，或查询失败
- **THEN** 前者通过完整分页恢复任务；后者显示可重试错误且不可启动
