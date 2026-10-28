## MODIFIED Requirements

### Requirement: 异步进度观察

实验进度 SHALL 经 `GET /tasks/{task_id}` 以固定间隔轮询（3 秒），到达终态（completed/failed/cancelled）SHALL 停止轮询，paused SHALL 停止轮询并保留最后进度；组件卸载或切换实验 SHALL 取消进行中的轮询请求；连续轮询失败 SHALL 暂停并提供手动重试。前端 SHALL NOT 使用 WebSocket 观察实验进度（后端 /ws/progress 仅支持 evaluation）。

#### Scenario: 轮询至终态停止

- **WHEN** 任务进度轮询观察到终态状态
- **THEN** 轮询停止且界面展示最终状态与错误信息（如有）

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

### Requirement: 实验列表与生命周期操作

实验列表 SHALL 服务端分页（limit 1–100 默认 20）并支持状态白名单筛选且筛选状态可经 URL 恢复；删除 SHALL 带确认且后端拒绝时原样展示错误；排队、运行或暂停的实验 SHALL 可取消——优先使用实验关联 task_id，旧响应缺少关联时完整查询 pending/running/paused 任务索引后调用 `DELETE /tasks/{task_id}`；已知活动任务 SHALL 不提供直接删除操作。列表 SHALL NOT 提供关键词搜索（后端无该参数），也不得伪造克隆入口（后端无克隆端点）。

#### Scenario: 运行中实验取消

- **WHEN** 用户对 running 状态的实验点击取消并确认
- **THEN** 前端通过该实验的关联 task_id（或兼容查询恢复的标识）调用任务取消接口，随后刷新列表状态

#### Scenario: 运行中删除被后端拒绝时如实展示

- **WHEN** 用户删除一个运行中的实验且后端返回错误
- **THEN** 界面原样展示该错误且列表状态不变

#### Scenario: 启动异常后重新同步

- **WHEN** 启动请求报错但后端可能已经创建任务
- **THEN** 前端重新读取实验和任务关联，按持久化状态决定是否可启动、取消或删除
