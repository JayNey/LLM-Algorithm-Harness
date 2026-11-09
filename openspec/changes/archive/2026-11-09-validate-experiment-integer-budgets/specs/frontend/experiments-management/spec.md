## MODIFIED Requirements

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
