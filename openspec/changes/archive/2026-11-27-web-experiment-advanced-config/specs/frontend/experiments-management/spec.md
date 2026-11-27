## MODIFIED Requirements

### Requirement: 实验创建与启动

前端 SHALL 提供实验创建页：多模型与多策略动态表单、可组合的每题预算（max_calls/max_tokens/max_seconds）、重复次数、serial|parallel 执行与 max_workers，字段校验 SHALL 与后端 schema 对齐（models/strategies ≥1、max_workers 1–16、温度 0–2、重复次数 ≥1、调用次数和 Token 上限为正整数、时间预算为有限正数）；创建成功 SHALL 提供详情页入口，启动 SHALL 经 `POST /experiments/{id}/run` 并以返回的 task_id 关联异步进度。校验不通过的草稿 SHALL 指出具体字段错误且不发起网络请求。

#### Scenario: 非法草稿被本地拒绝

- **WHEN** 用户提交缺少模型或包含非法预算值的草稿
- **THEN** 表单展示对应字段错误且无网络请求发出

#### Scenario: 创建后进入详情并可启动

- **WHEN** 创建请求成功返回
- **THEN** 应用提供该实验详情页入口，用户可启动并得到异步任务关联

#### Scenario: 整数预算无效时拦截创建

- **WHEN** 用户填写调用次数或 Token 上限为小数、零、负数或非法文本
- **THEN** 表单在对应预算字段展示正整数提示，且不发送创建请求

#### Scenario: 发送选定预算

- **WHEN** 其余字段合法，用户填写一个或多个正整数调用次数、正整数 Token 上限或有限正数时间预算
- **THEN** 创建请求的预算对象包含全部已填写维度，且其值为数字
- **AND** 各维度进入共享每题预算逻辑，任一限制触发时按既有语义停止后续调用

#### Scenario: 不设置预算

- **WHEN** 用户未填写任何预算并提交
- **THEN** 创建请求的预算值为 `null`

## ADDED Requirements

### Requirement: 高级策略参数配置与继承

实验创建页 SHALL 允许为每个策略设置 max_tokens、system_prompt 和白名单内的已有 custom_params。max_tokens SHALL 为 100–8000 整数；custom_params SHALL 校验对象格式、支持键、类型、范围及枚举。空高级字段 SHALL 省略并保持既有默认及参数继承。页面 SHALL NOT 开放服务器路径、base_url 或沙箱部署配置。

#### Scenario: 高级参数贯穿业务逻辑

- **WHEN** 用户为实际读取 custom_params 的策略提交有效高级参数
- **THEN** 请求、持久化配置和执行器收到的有效参数一致，真实策略按该参数执行
- **AND** 详情回显实际高级配置

#### Scenario: 空配置与旧任务兼容

- **WHEN** 用户不填写高级参数，或打开缺少这些字段的旧任务
- **THEN** 创建沿用现有默认与继承，旧任务仍可读取并展示

#### Scenario: 高级输入错误可修正

- **WHEN** 用户输入非法 JSON、非对象、不支持键或类型、范围、枚举错误
- **THEN** 页面定位到具体策略及参数，阻止请求，保留输入供用户修正后重试

### Requirement: 实验题目筛选与范围回显

实验创建页 SHALL 提供已有 difficulty、tags、problem_ids 和 limit 筛选，省略空条件并校验正整数 limit。标签 SHALL 任一匹配，各条件 SHALL 取交集并最后按原数据集顺序截取 limit。页面 SHALL 在提交前、创建成功后及持久化详情显示选择条件和范围语义，不虚构匹配数量。

#### Scenario: 组合筛选实际生效

- **WHEN** 用户提交难度、标签、题目 ID 和数量上限的组合条件
- **THEN** 请求与持久化配置保留条件，实际执行题目符合交集和最后截取规则
- **AND** 提交前后及刷新后的详情展示对应筛选条件

#### Scenario: 未筛选与错误修正

- **WHEN** 用户留空筛选或填写非法 limit
- **THEN** 留空时沿用全部题目，非法 limit 时定位字段错误、保留输入且不提交
