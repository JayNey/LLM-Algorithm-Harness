# frontend/experiments-management Specification

## Purpose
TBD - created by archiving change experiments-frontend. Update Purpose after archive.

## Requirements

### Requirement: 实验创建与启动

前端 SHALL 提供实验创建页：多模型与多策略动态表单、预算（max_calls/max_tokens/max_seconds 至多其一）、重复次数、serial|parallel 执行与 max_workers，字段校验 SHALL 与后端 schema 对齐（models/strategies ≥1、max_workers 1–16、温度 0–2、重复次数 ≥1）；创建成功 SHALL 导航至详情页，启动 SHALL 经 `POST /experiments/{id}/run` 并以返回的 task_id 关联异步进度。校验不通过的草稿 SHALL 指出具体字段错误且不发起网络请求。

#### Scenario: 非法草稿被本地拒绝

- **WHEN** 用户提交缺少模型或预算同时填写多型的草稿
- **THEN** 表单展示对应字段错误且无网络请求发出

#### Scenario: 创建后进入详情并可启动

- **WHEN** 创建请求成功返回
- **THEN** 应用导航到该实验详情页，用户可启动并得到异步任务关联

### Requirement: 实验列表与生命周期操作

实验列表 SHALL 服务端分页（limit 1–100 默认 20）并支持状态白名单筛选且筛选状态可经 URL 恢复；删除 SHALL 带确认且后端拒绝（运行中）时原样展示错误；运行中实验 SHALL 可取消——经任务通道（查询 running 任务索引后 `DELETE /tasks/{task_id}`）。列表 SHALL NOT 提供关键词搜索（后端无该参数），也不得伪造克隆入口（后端无克隆端点）。

#### Scenario: 运行中实验取消

- **WHEN** 用户对 running 状态的实验点击取消并确认
- **THEN** 前端查询该实验的 running 任务并调用任务取消接口，随后刷新列表状态

#### Scenario: 运行中删除被后端拒绝时如实展示

- **WHEN** 用户删除一个运行中的实验且后端返回错误
- **THEN** 界面原样展示该错误且列表状态不变

### Requirement: 异步进度观察

实验进度 SHALL 经 `GET /tasks/{task_id}` 以固定间隔轮询（3 秒），到达终态（completed/failed/cancelled）SHALL 停止轮询，paused SHALL 停止轮询并保留最后进度；组件卸载或切换实验 SHALL 取消进行中的轮询请求；连续轮询失败 SHALL 暂停并提供手动重试。前端 SHALL NOT 使用 WebSocket 观察实验进度（后端 /ws/progress 仅支持 evaluation）。

#### Scenario: 轮询至终态停止

- **WHEN** 任务进度轮询观察到终态状态
- **THEN** 轮询停止且界面展示最终状态与错误信息（如有）

#### Scenario: 连续失败暂停轮询

- **WHEN** 进度轮询连续多次失败
- **THEN** 轮询暂停并提供手动重试入口

### Requirement: 对比分析与可视化

详情页 SHALL 提供对比报告（组合指标表、胜率矩阵热力图、McNemar 显著性标注、成本效益表）与面板（雷达/散点/柱状直绘 panel 数据）；SHALL 支持将 comparison 报告作为输入调用帕累托分析与成本优化建议并展示前沿点、预算建议与三目标排名。分析类数据 SHALL 惰性加载，任何字段形状不符 SHALL 显式报错而非静默绘制。

#### Scenario: 胜率矩阵与显著性展示

- **WHEN** 实验完成后用户打开对比报告
- **THEN** 胜率矩阵热力图渲染，显著性组合带 p 值标注，成本效益表按性价比展示

#### Scenario: 帕累托分析惰性加载

- **WHEN** 用户首次进入帕累托 Tab
- **THEN** 才发起分析请求并渲染前沿点与预算建议，形状不符时展示明确错误
