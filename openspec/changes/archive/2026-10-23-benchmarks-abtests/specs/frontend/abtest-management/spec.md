## ADDED Requirements

### Requirement: A/B 测试创建与列表

前端 SHALL 提供 A/B 测试创建页：单模型、单策略、恰好两个 prompt 变体（id 必填）、seed ≥0、max_workers 1–20、api_key 与 dataset_path 必填，校验 SHALL 与后端 schema 对齐且非法草稿不发起网络请求；列表 SHALL 分页并支持状态筛选与删除。

#### Scenario: 变体数量不满足时本地拒绝

- **WHEN** 用户提交缺少任一变体 id 的草稿
- **THEN** 表单指出变体字段错误且无网络请求

#### Scenario: 启动后仅状态可查

- **WHEN** 用户启动一个 A/B 测试
- **THEN** 界面轮询测试状态至终态（无 task 通道、无进度百分比），错误时展示 error_message

### Requirement: A/B 结果统计展示

测试完成后详情页 SHALL 展示 results 报告的消费子集：sample 与 formal 两组的 baseline/treatment 通过率与 ci95 区间、检验方法三态（fisher_exact/chi_square/unavailable）及其 p 值与 Welch t p 值、失败分类。任何字段形状不符 SHALL 显式报错；未完成或产物缺失 SHALL 按后端错误如实展示。

#### Scenario: 完成后统计表渲染

- **WHEN** 测试完成后用户打开详情页
- **THEN** 两组比率与置信区间、检验方法与 p 值、失败分类以表格呈现，可空字段以「—」呈现
