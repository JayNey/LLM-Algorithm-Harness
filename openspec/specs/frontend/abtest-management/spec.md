# frontend/abtest-management Specification

## Purpose
TBD - created by archiving change benchmarks-abtests. Update Purpose after archive.

## Requirements

### Requirement: A/B 测试创建与列表

前端 SHALL 提供 A/B 测试创建页：单模型、单策略、恰好两个 prompt 变体（id 必填）、seed ≥0、max_workers 1–20、api_key 与 dataset_path 必填，校验 SHALL 与后端 schema 对齐且非法草稿不发起网络请求；列表 SHALL 分页并支持状态筛选与删除。

创建表单 SHALL 默认使用 `vanilla`，并仅允许提交评估选项目录中存在的策略。目录不可用时 SHALL 阻止提交。

#### Scenario: 变体数量不满足时本地拒绝

- **WHEN** 用户提交缺少任一变体 id 的草稿
- **THEN** 表单指出变体字段错误且无网络请求

#### Scenario: 启动后仅状态可查

- **WHEN** 用户启动一个 A/B 测试
- **THEN** 界面轮询测试状态至终态（无 task 通道、无进度百分比），错误时展示 error_message

#### Scenario: 使用有效的默认策略

- **WHEN** 策略目录包含 `vanilla`，用户填写其他必填项并提交
- **THEN** 创建请求的策略为 `vanilla`

#### Scenario: 无法核对策略

- **WHEN** 目录不可用或当前策略不在目录中
- **THEN** 表单不发送创建请求

### Requirement: A/B 结果统计展示

测试完成后详情页 SHALL 展示 results 报告的消费子集：sample 与 formal 两组的 baseline/treatment 通过率与 ci95 区间、检验方法三态（fisher_exact/chi_square/unavailable）及其 p 值与 Welch t p 值、失败分类。任何字段形状不符 SHALL 显式报错；未完成或产物缺失 SHALL 按后端错误如实展示。

#### Scenario: 完成后统计表渲染

- **WHEN** 测试完成后用户打开详情页
- **THEN** 两组比率与置信区间、检验方法与 p 值、失败分类以表格呈现，可空字段以「—」呈现

### Requirement: 状态轮询失败提示与恢复

详情页状态轮询 SHALL 区分暂时性故障与权限或资源终止：暂时性故障（5xx、断网等）SHALL 显示可见错误并标明保留状态可能过期，提供就地重试，重试或自动重试成功后清除错误并刷新快照；403/404 SHALL 停止轮询，不再渲染过期的执行状态与启动、删除等操作入口，并如实反馈失败原因。终态停止与既有身份、路由隔离 SHALL 保持不变。

#### Scenario: 暂时性故障可见且可重试

- **WHEN** 运行中状态轮询返回 5xx 或请求失败
- **THEN** 页面显示错误与重试入口，并标注保留状态可能过期；重试成功后错误清零并读取最新状态

#### Scenario: 权限或资源终止停止轮询

- **WHEN** 状态轮询返回 403 或 404
- **THEN** 轮询停止，页面不再显示过期的执行状态与操作入口，并显示失败原因

#### Scenario: 正常终态与请求隔离保持

- **WHEN** 测试到达 completed/failed/cancelled 终态，或切换测试、切换账号、卸载页面
- **THEN** 终态停止轮询并可查看报告；旧请求与旧身份的响应不得更新当前页面
