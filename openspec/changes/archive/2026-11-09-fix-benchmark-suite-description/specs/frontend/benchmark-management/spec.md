## MODIFIED Requirements

### Requirement: 基准 Suite 管理

前端 SHALL 提供基准 Suite 的列表（全量返回，不伪造分页参数）、创建（name 与 problems[] 必填、version 默认 1.0、frozen 默认 false）与编辑（PATCH 可选字段）；SHALL 支持对 Suite 启动 run（api_key/dataset_path/model/strategies/budget_cap_usd，保留已有个人数据集选择）并以返回的真实 run_id 与 task_id 导航和观察进度至终态。后端不存在 Suite 删除端点，前端 SHALL NOT 提供删除入口。

套件 PATCH SHALL 区分省略描述、显式清空与文本替换。详情页 SHALL 在保存后重新读取服务端详情，并仅允许编辑未冻结的套件。服务端 SHALL 拒绝修改冻结套件。

#### Scenario: 创建 Suite 并出现在列表

- **WHEN** 用户以合法字段创建 Suite
- **THEN** 新 Suite 出现在列表且创建面板关闭

#### Scenario: 启动 run 后进度可见

- **WHEN** 用户对 Suite 启动 run
- **THEN** 界面保存选中的真实运行标识到 URL，以关联 task_id 观察进度，展示该运行的准确率/成本或错误，刷新可恢复

#### Scenario: 清空、保留或更新描述

- **WHEN** 用户对未冻结套件提交 PATCH
- **THEN** 服务 SHALL 保留省略的描述，将显式 `null` 持久化为空，或保存提交的新文本
- **AND** 保存回执与独立 GET SHALL 返回持久化值，详情页保存后及硬刷新后 SHALL 显示服务端当前值

#### Scenario: 冻结套件不可编辑

- **WHEN** 套件处于冻结状态
- **THEN** 详情页 SHALL 隐藏编辑入口与提交表单，服务端 SHALL 拒绝直接 PATCH
