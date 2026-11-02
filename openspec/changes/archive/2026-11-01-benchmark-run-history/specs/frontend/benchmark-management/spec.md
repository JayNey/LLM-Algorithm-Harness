## MODIFIED Requirements

### Requirement: 基准 Suite 管理

前端 SHALL 提供基准 Suite 的列表（全量返回，不伪造分页参数）、创建（name 与 problems[] 必填、version 默认 1.0、frozen 默认 false）与编辑（PATCH 可选字段）；SHALL 支持对 Suite 启动 run（api_key/dataset_path/model/strategies/budget_cap_usd，保留已有个人数据集选择）并以返回的真实 run_id 与 task_id 导航和观察进度至终态。后端不存在 Suite 删除端点，前端 SHALL NOT 提供删除入口。

#### Scenario: 创建 Suite 并出现在列表

- **WHEN** 用户以合法字段创建 Suite
- **THEN** 新 Suite 出现在列表且创建面板关闭

#### Scenario: 启动 run 后进度可见

- **WHEN** 用户对 Suite 启动 run
- **THEN** 界面保存选中的真实运行标识到 URL，以关联 task_id 观察进度，展示该运行的准确率/成本或错误，刷新可恢复

### Requirement: 学习曲线展示

详情页 SHALL 经 learning-curve 端点按模型分组绘制历史 run 的准确率与成本折线，并展示 trends 增长率（不足两条记录时按无趋势呈现）。历史数据来自该端点，前端 SHALL NOT 伪造 run 列表；曲线点 SHALL 可通过后端返回的 run_id 定位对应运行，并提供键盘可访问的等价导航。

#### Scenario: 多模型学习曲线渲染

- **WHEN** Suite 存在多个模型的已完成 run
- **THEN** 折线图按模型分组渲染准确率与成本序列，trends 增长率随之展示

#### Scenario: 选择历史曲线运行

- **WHEN** 用户选择某个曲线点或其等价运行链接
- **THEN** 页面加载该点实际 run_id 的详情，不使用当前历史页第一条或最新完成记录替代

## ADDED Requirements

### Requirement: 真实历史分页与显式运行恢复

前端 SHALL 接入当前所有者的套件历史，提供后端分页、状态筛选、运行选择和真实空态。选中运行 SHALL 保存在可刷新和分享的 URL 中，明确选择的运行 SHALL 独立于当前列表页查询，错误或无权访问 SHALL 明确反馈。运行与任务标识 SHALL 校验当前套件和关联实体，不猜测或替换。

#### Scenario: 默认页外的显式运行

- **WHEN** URL 指向不在当前历史页或当前状态筛选中的合法运行
- **THEN** 页面仍能展示该运行详情和关联进度，筛选或分页不会静默丢弃选择

#### Scenario: 无效或其他套件的链接

- **WHEN** URL 运行不存在、无权访问或不属于当前套件
- **THEN** 页面明确反馈且不展示其他运行作为替代

#### Scenario: 多个活动运行

- **WHEN** 重新进入页面发现多个 pending/running/paused 运行
- **THEN** 页面提供真实活动运行选择和更多记录导航，不将最新 completed 记录作为当前活动运行

### Requirement: 进度观察隔离和终态对账

前端 SHALL 区分 pending/running/paused 与 completed/failed/cancelled；终态停止无效轮询并刷新选中详情、历史和曲线，暂停保留进度且可手动重新核对。观察失败 SHALL 提供重试，账号、路由或运行变化 SHALL 清理旧请求和观察器，旧响应 SHALL NOT 污染当前页面。

#### Scenario: 终态刷新后停止

- **WHEN** 选中运行关联任务进入终态
- **THEN** 页面刷新真实运行结果、历史与曲线，并停止该任务自动轮询，不产生资源刷新循环

#### Scenario: 暂停和账号切换

- **WHEN** 已暂停运行被选中或用户切换账号
- **THEN** 暂停显示真实进度和手动刷新；账号切换清除旧账号运行内容，旧请求即使返回也不展示

#### Scenario: 双语窄屏与键盘操作

- **WHEN** 用户以中文或英文在 320px 窄屏或键盘模式操作历史与曲线
- **THEN** 运行选择、分页、刷新与错误反馈均可用，页面无整体横向溢出
