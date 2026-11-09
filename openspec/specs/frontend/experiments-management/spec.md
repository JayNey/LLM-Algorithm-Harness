# frontend/experiments-management Specification

## Purpose
TBD - created by archiving change experiments-frontend. Update Purpose after archive.

## Requirements

### Requirement: 实验创建与启动

前端 SHALL 提供实验创建页：多模型与多策略动态表单、预算（max_calls/max_tokens/max_seconds 至多其一）、重复次数、serial|parallel 执行与 max_workers，字段校验 SHALL 与后端 schema 对齐（models/strategies ≥1、max_workers 1–16、温度 0–2、重复次数 ≥1、调用次数和 Token 上限为正整数、时间预算为有限正数）；创建成功 SHALL 导航至详情页，启动 SHALL 经 `POST /experiments/{id}/run` 并以返回的 task_id 关联异步进度。校验不通过的草稿 SHALL 指出具体字段错误且不发起网络请求。

#### Scenario: 非法草稿被本地拒绝

- **WHEN** 用户提交缺少模型或预算同时填写多型的草稿
- **THEN** 表单展示对应字段错误且无网络请求发出

#### Scenario: 创建后进入详情并可启动

- **WHEN** 创建请求成功返回
- **THEN** 应用导航到该实验详情页，用户可启动并得到异步任务关联

#### Scenario: 整数预算无效时拦截创建

- **WHEN** 用户选择调用次数或 Token 上限，并提交小数、零、负数、非法文本或留空
- **THEN** 表单在预算限制值字段展示正整数提示，且不发送创建请求

#### Scenario: 发送选定预算

- **WHEN** 其余字段合法，用户提交正整数调用次数、正整数 Token 上限或有限正数时间预算
- **THEN** 创建请求的预算对象只包含所选类型，且其值为数字

#### Scenario: 不设置预算

- **WHEN** 用户选择无预算并提交
- **THEN** 创建请求的预算值为 `null`

### Requirement: 实验列表与生命周期操作

实验列表 SHALL 服务端分页（limit 1–100 默认 20）并支持状态白名单筛选且筛选状态可经 URL 恢复；删除 SHALL 带确认且后端拒绝时原样展示错误；排队、运行或暂停的实验 SHALL 可取消——优先使用实验关联 task_id，旧响应缺少关联时完整查询 pending/running/paused 任务索引后调用 `DELETE /tasks/{task_id}`；已知活动任务 SHALL 不提供直接删除操作。列表 SHALL NOT 提供关键词搜索（后端无该参数），也不得伪造克隆入口（后端无克隆端点）。

#### Scenario: 取消确认可用键盘操作

- **WHEN** 用户在列表或详情用键盘激活排队、运行或暂停实验的取消按钮
- **THEN** 前端 SHALL 打开取消确认弹窗
- **AND** 用户按 Esc 或选择返回时，前端 SHALL 关闭弹窗且不发送取消请求

#### Scenario: 运行中实验取消

- **WHEN** 用户确认取消实验，包括在取消请求未完成时重复确认
- **THEN** 前端 SHALL 仅通过该实验的关联 task_id（或兼容查询恢复的标识）调用一次任务取消接口

#### Scenario: 取消尝试后读取服务端状态

- **WHEN** 取消请求成功、失败或因实验先完成被拒绝
- **THEN** 前端 SHALL 重新读取服务端状态，据此显示实验状态及允许的操作
- **AND** 请求失败时 SHALL 显示操作错误

#### Scenario: 运行中删除被后端拒绝时如实展示

- **WHEN** 用户删除一个运行中的实验且后端返回错误
- **THEN** 界面原样展示该错误且列表状态不变

#### Scenario: 启动异常后重新同步

- **WHEN** 启动请求报错但后端可能已经创建任务
- **THEN** 前端重新读取实验和任务关联，按持久化状态决定是否可启动、取消或删除

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

### Requirement: 对比分析与可视化

详情页 SHALL 提供对比报告（组合指标表、胜率矩阵热力图、McNemar 显著性标注、成本效益表）与面板（雷达/散点/柱状直绘 panel 数据）；SHALL 支持将 comparison 报告作为输入调用帕累托分析与成本优化建议并展示前沿点、预算建议与三目标排名。分析类数据 SHALL 惰性加载，任何字段形状不符 SHALL 显式报错而非静默绘制。

#### Scenario: 胜率矩阵与显著性展示

- **WHEN** 实验完成后用户打开对比报告
- **THEN** 胜率矩阵热力图渲染，显著性组合带 p 值标注，成本效益表按性价比展示

#### Scenario: 帕累托分析惰性加载

- **WHEN** 用户首次进入帕累托 Tab
- **THEN** 才发起分析请求并渲染前沿点与预算建议，形状不符时展示明确错误
