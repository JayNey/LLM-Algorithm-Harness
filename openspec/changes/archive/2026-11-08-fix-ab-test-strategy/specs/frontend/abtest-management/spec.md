## MODIFIED Requirements

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
