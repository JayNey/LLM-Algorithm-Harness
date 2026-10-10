## Purpose

评估任务管理端点为 Web 前端提供完整的 CRUD 操作，支持创建新的评估任务、查询现有任务、更新任务配置、删除任务，以及监控任务执行进度。

## ADDED Requirements

### Requirement: 创建评估任务

系统 SHALL 通过 POST `/api/v1/evaluations` 端点接受新的评估任务定义，包含：
- 题目集合（problem IDs 列表）
- 策略配置（使用的策略名称和参数）
- 预算配置（可选的成本限制）
- 执行参数（超时、并发数等）

#### Scenario: 创建有效的评估任务
- **WHEN** 客户端 POST 包含有效的题目 ID 和策略配置
- **THEN** 系统返回 HTTP 201，包含新任务的 ID 和状态

#### Scenario: 创建任务时参数无效
- **WHEN** 客户端 POST 包含无效的策略名称或缺少必填字段
- **THEN** 系统返回 HTTP 400 和验证错误信息

### Requirement: 查询评估任务

系统 SHALL 通过 GET `/api/v1/evaluations` 端点列出所有评估任务，支持：
- 分页（limit、offset 参数）
- 按状态过滤（pending、running、completed、failed）
- 排序（按创建时间、更新时间）

#### Scenario: 列出所有评估任务
- **WHEN** 客户端 GET `/api/v1/evaluations` 无参数
- **THEN** 系统返回包含所有任务的分页列表，默认返回前 20 条

#### Scenario: 过滤运行中的任务
- **WHEN** 客户端 GET `/api/v1/evaluations?status=running`
- **THEN** 系统返回仅包含运行中状态的任务

### Requirement: 获取单个评估任务详情

系统 SHALL 通过 GET `/api/v1/evaluations/{evaluation_id}` 端点返回特定评估任务的完整信息，包括：
- 任务基本信息（ID、创建时间、状态）
- 配置详情（题目数量、使用的策略）
- 执行进度（已完成题数、总题数）
- 成本统计（已花费金额、预算限制）

#### Scenario: 获取存在的任务详情
- **WHEN** 客户端 GET `/api/v1/evaluations/{valid-id}`
- **THEN** 系统返回 HTTP 200 和任务的完整信息

#### Scenario: 获取不存在的任务详情
- **WHEN** 客户端 GET `/api/v1/evaluations/{invalid-id}`
- **THEN** 系统返回 HTTP 404 和错误消息

### Requirement: 更新评估任务配置

系统 SHALL 通过 PATCH `/api/v1/evaluations/{evaluation_id}` 端点允许更新待执行任务的配置。仅 pending 状态的任务可被编辑。

#### Scenario: 更新待执行任务的预算配置
- **WHEN** 客户端 PATCH 一个 pending 状态任务的成本限制
- **THEN** 系统返回 HTTP 200 和更新后的任务信息

#### Scenario: 无法更新运行中的任务
- **WHEN** 客户端尝试 PATCH 一个 running 或 completed 状态的任务
- **THEN** 系统返回 HTTP 400 和错误消息（任务已无法修改）

### Requirement: 删除评估任务

系统 SHALL 通过 DELETE `/api/v1/evaluations/{evaluation_id}` 端点删除评估任务。仅 pending 或 completed 状态的任务可被删除。

#### Scenario: 删除待执行任务
- **WHEN** 客户端 DELETE 一个 pending 状态的任务
- **THEN** 系统返回 HTTP 204 表示删除成功

#### Scenario: 无法删除运行中的任务
- **WHEN** 客户端尝试 DELETE 一个 running 状态的任务
- **THEN** 系统返回 HTTP 400 和错误消息

### Requirement: 启动评估任务执行

系统 SHALL 通过 POST `/api/v1/evaluations/{evaluation_id}/start` 端点启动任务执行。

#### Scenario: 启动待执行任务
- **WHEN** 客户端 POST 启动请求到 pending 状态的任务
- **THEN** 系统返回 HTTP 200，任务状态变更为 running，开始异步执行

#### Scenario: 无法启动已运行的任务
- **WHEN** 客户端尝试启动一个已经 running 或 completed 的任务
- **THEN** 系统返回 HTTP 400 和错误消息

### Requirement: 监控任务执行进度

系统 SHALL 通过 GET `/api/v1/evaluations/{evaluation_id}/progress` 端点返回实时执行进度，包括：
- 已完成题数 / 总题数
- 当前执行速度（题目/分钟）
- 预计完成时间
- 成本实时统计

#### Scenario: 获取运行中任务的进度
- **WHEN** 客户端 GET 一个 running 状态任务的进度端点
- **THEN** 系统返回 HTTP 200 和进度信息

### Requirement: 取消任务执行

系统 SHALL 通过 POST `/api/v1/evaluations/{evaluation_id}/cancel` 端点取消正在执行的任务。

#### Scenario: 取消运行中的任务
- **WHEN** 客户端 POST 取消请求到 running 状态的任务
- **THEN** 系统返回 HTTP 200，任务状态变更为 cancelled，停止执行
