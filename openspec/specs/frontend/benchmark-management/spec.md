# frontend/benchmark-management Specification

## Purpose
TBD - created by archiving change benchmarks-abtests. Update Purpose after archive.

## Requirements

### Requirement: 基准 Suite 管理

前端 SHALL 提供基准 Suite 的列表（全量返回，不伪造分页参数）、创建（name 与 problems[] 必填、version 默认 1.0、frozen 默认 false）与编辑（PATCH 可选字段）；SHALL 支持对 Suite 启动 run（api_key/dataset_path/model/strategies/budget_cap_usd）并以返回的 task_id 轮询 `GET /tasks/{task_id}` 进度至终态。后端不存在 Suite 删除端点，前端 SHALL NOT 提供删除入口。

#### Scenario: 创建 Suite 并出现在列表

- **WHEN** 用户以合法字段创建 Suite
- **THEN** 新 Suite 出现在列表且创建面板关闭

#### Scenario: 启动 run 后进度可见

- **WHEN** 用户对 Suite 启动 run
- **THEN** 界面以返回的 task_id 轮询进度至终态，并展示 run 的准确率/成本或错误信息

### Requirement: 学习曲线展示

详情页 SHALL 经 learning-curve 端点按模型分组绘制历史 run 的准确率与成本折线，并展示 trends 增长率（不足两条记录时按无趋势呈现）。历史数据来自该端点，前端 SHALL NOT 伪造 run 列表。

#### Scenario: 多模型学习曲线渲染

- **WHEN** Suite 存在多个模型的已完成 run
- **THEN** 折线图按模型分组渲染准确率与成本序列，trends 增长率随之展示
