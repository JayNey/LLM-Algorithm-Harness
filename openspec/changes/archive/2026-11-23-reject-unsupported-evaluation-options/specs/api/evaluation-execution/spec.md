## ADDED Requirements

### Requirement: 入口拒绝尚未实现的执行配置

系统 SHALL 在评估创建请求显式提供 `timeout_seconds` 或 `max_concurrency`，或评估更新请求显式提供 `timeout_seconds` 时返回 HTTP 400 `validation_error`，按对应字段说明配置暂不支持并要求省略。拒绝 SHALL 覆盖任意显式值，包含历史默认值和 null，且 SHALL 在数据库修改与任务发布前发生。普通、异步和个人集合版本创建 SHALL 遵守相同规则。

#### Scenario: 拒绝 Issue 中的自定义参数

- **WHEN** 已认证用户向任一评估创建入口发送合法基本配置并显式提供 `timeout_seconds=123` 或 `max_concurrency=7`，或同时提供两者
- **THEN** 返回 HTTP 400 `validation_error`，错误详情定位到所提供字段，没有新增评估或任务记录，也没有发布任务消息

#### Scenario: 历史默认值与 null 不表示支持配置

- **WHEN** 创建请求显式提供 `timeout_seconds=300`、`max_concurrency=5` 或上述字段的 null 值
- **THEN** 返回字段级 HTTP 400，说明配置暂不支持并要求省略，不持久化也不发布任务

#### Scenario: PATCH 超时不再静默成功

- **WHEN** 用户对本人 pending 评估显式提交 `timeout_seconds`，包含与预算更新组合的请求
- **THEN** 返回字段级 HTTP 400，原评估记录及其预算保持不变，没有发布任务消息

### Requirement: 公开说明当前评估执行配置限制

系统 SHALL 在公开 API 文档和请求 schema 描述中声明上述字段暂不可设置，并将遗留字段标记弃用。示例 SHALL 省略它们。文档 SHALL 区分固定串行执行、默认沙箱的每个测试用例 5 秒时限与独立的模型请求超时；SHALL 明确旧客户端需删除字段，以及显式请求从静默忽略改为拒绝的兼容影响。

#### Scenario: 客户端按公开说明创建评估

- **WHEN** 用户读取 OpenAPI 和 API 使用说明
- **THEN** 能获知两个字段尚未实现、显式提供将返回 400，并能使用省略字段的示例创建评估；文档不将 300 秒或并发 5 宣称为实际默认执行行为

### Requirement: 省略未实现字段的评估维持真实执行语义

系统 SHALL 继续允许省略两个字段的合法创建请求，并通过现有持久化和 worker 路径执行；单评估单元调度 SHALL 保持串行，沙箱 SHALL 使用现有默认测试用例时限。独立的 `generation_timeout_seconds` SHALL 继续按原契约保存和传递，不与未实现的每题超时字段混用。

#### Scenario: API 请求到实际 worker 配置一致

- **WHEN** 用户省略两个未实现字段创建并启动评估
- **THEN** 评估及关联任务正常持久化，真实 worker 使用 `max_workers=1` 和沙箱每个测试用例 5 秒时限，不读取历史请求占位默认值

#### Scenario: 独立模型生成时限继续有效

- **WHEN** 用户省略两个未实现字段并设置合法的 `generation_timeout_seconds`
- **THEN** 创建成功，持久化记录与真实 worker 的模型请求配置使用该生成时限
