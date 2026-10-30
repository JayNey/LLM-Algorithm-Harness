## MODIFIED Requirements

### Requirement: 基准 Suite 与运行管理

系统 SHALL 支持基准 Suite 的列出/创建/详情/更新（frozen 的 Suite SHALL 拒绝更新与删除），运行 SHALL 经 `BenchmarkExecutor` 异步执行并把结果（模型、accuracy、cost）持久化为 run 记录。

系统 SHALL 提供 `GET /api/v1/benchmarks/suites/{suite_id}/runs`，以 limit（默认 20，范围 1..100）、offset（默认 0，非负）分页，支持可选单一状态 pending/running/paused/completed/failed/cancelled；非法参数 SHALL 返回现有格式的 400 错误。系统 SHALL 在分页前筛选状态，按 created_at 和 id 倒序稳定排序，返回 items、匹配总数 total、limit、offset、has_more。

每条历史记录 SHALL 提供 id、suite_id、task_id、status、model、created_at、updated_at、started_at、completed_at、accuracy、cost_usd、error_message 和现有数据集摘要。未知指标、时间与任务关联 SHALL 为 null，真实零值 SHALL 保留。详情 SHALL 返回同一运行及安全的 task_id。

系统 SHALL 校验套件和运行均属于当前用户，任务关联 SHALL 同时匹配当前用户、benchmark 类型及运行实体；存在多条时取 created_at 和 id 倒序的最新关联。缺失或他人资源 SHALL 返回 404，未经认证 SHALL 不可枚举资源。

#### Scenario: frozen Suite 拒绝变更

- **WHEN** 对 frozen 的 Suite 提交更新
- **THEN** 返回错误且数据不变

#### Scenario: 状态过滤和稳定分页

- **WHEN** 用户分页查询自己的套件并指定状态，多个记录创建时间相同
- **THEN** 在分页前筛选状态，以 id 倒序打破时间平局，返回匹配总数和准确的 has_more；空套件或越界页返回有效空页

#### Scenario: 标识导航与空值

- **WHEN** 查询包含活动和终态运行的历史
- **THEN** 每条 id 可用于详情，存在安全关联时 task_id 可用于进度查询；未知数据保持 null，零准确率和费用保持 0

#### Scenario: 资源和关联归属

- **WHEN** 用户查询他人或不存在的套件/运行，或自己的套件含不匹配用户的异常记录/任务
- **THEN** 他人或缺失资源返回 404，历史不包含他人运行，也不返回他人或其他类型任务的关联 ID

### Requirement: 学习曲线追踪

系统 SHALL 按 Suite 聚合当前用户已完成的历史 run 时间序列（timestamp、model、accuracy、cost_usd），并给出原有趋势指标；每个点 SHALL 兼容增加正确的 run_id，可用于现有运行详情查询；非完成或他人运行 SHALL 不进入曲线，无历史数据时返回空序列而非错误。

#### Scenario: 空历史返回空曲线

- **WHEN** 查询尚无 run 记录的 Suite 学习曲线
- **THEN** 返回 200 与空 data 数组

#### Scenario: 曲线与历史详情一致

- **WHEN** 套件含多种状态及其他所有者的异常运行
- **THEN** 曲线只包含当前用户 completed 记录，其 run_id 对应历史与详情中的 id，保留原有指标及趋势计算
