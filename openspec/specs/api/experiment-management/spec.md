# api/experiment-management Specification

## Purpose
为固定预算实验、基准 Suite 和 A/B 提示测试提供创建、异步执行、结果分析与学习曲线查询，并以持久化状态和所有者隔离管理其生命周期。

## Requirements

### Requirement: 实验生命周期管理

系统 SHALL 支持创建（校验模型/策略/预算配置与 `api_key_id` 归属）、列出、查看、异步运行固定预算实验，并以 `pending/running/paused/completed/failed/cancelled` 跟踪状态；实验配置与状态 SHALL 持久化，结果分析 SHALL 从实验产物目录读取。

#### Scenario: 创建时校验密钥归属

- **WHEN** 用户提交引用他人 `api_key_id` 的实验配置
- **THEN** 返回错误且不落库；归属合法时配置以脱敏形式持久化并返回实验 ID

#### Scenario: 运行与状态迁移

- **WHEN** 仅 pending 的实验被启动，后台执行完成后
- **THEN** 状态经历 running → completed，产物目录路径落库；执行异常标记 failed 并附原因；运行中任务不可删除

系统 SHALL 原子地保证同一实验最多提交一个执行任务，重复启动返回明确错误；详情及列表 SHALL 返回所属用户的 task_id，未提交时为 null。已排队或暂停的实验 SHALL 不可直接删除。发布失败 SHALL 返回错误并同步失败状态，不留假排队状态；已被 Worker 或取消请求推进的状态 SHALL 不被迟到发布异常覆盖。

#### Scenario: 重复或并发启动

- **WHEN** 同一实验收到连续或不同进程并发的启动请求
- **THEN** 最多创建并发布一个有效任务，重复请求返回明确错误

#### Scenario: 排队删除与提交竞争

- **WHEN** 实验有 pending/running/paused 任务或与启动竞争删除
- **THEN** 活动任务对应的实验不可删除；若删除先完成，启动返回不存在且不发布任务

#### Scenario: 关联与用户隔离

- **WHEN** 所有者刷新实验详情或列表
- **THEN** 返回同一个 task_id；其他用户不能读取、启动或删除该实验，也不能看到其任务关联

#### Scenario: 发布失败与取消保持

- **WHEN** 消息发布失败且任务仍 pending
- **THEN** 任务与实验均变为 failed 并保存错误，允许删除；若取消已完成，继续保持 cancelled 和原结束时间

### Requirement: 实验结果分析

系统 SHALL 从完成的实验产物中返回结果摘要、模型×策略对比（含胜率矩阵与 McNemar 显著性）、以及交互面板数据；产物缺失或实验未完成时 SHALL 返回明确错误。

#### Scenario: 未完成实验不可取结果

- **WHEN** 对 running 状态的实验请求对比报告
- **THEN** 返回明确错误而非部分数据

### Requirement: 帕累托与成本优化分析

系统 SHALL 提供无状态的帕累托前沿分析与成本优化端点，直接调用 `src/pareto.py` 与 `src/cost_optimizer.py`，输入不合法时返回 400 级错误而非 500。

#### Scenario: 非法分析输入

- **WHEN** 提交缺少必要比较数据的帕累托分析请求
- **THEN** 返回 400 与可读错误信息

### Requirement: 基准 Suite 与运行管理

系统 SHALL 支持基准 Suite 的列出/创建/详情/更新（frozen 的 Suite SHALL 拒绝更新与删除），运行 SHALL 经 `BenchmarkExecutor` 异步执行并把结果（模型、accuracy、cost）持久化为 run 记录。

#### Scenario: frozen Suite 拒绝变更

- **WHEN** 对 frozen 的 Suite 提交更新
- **THEN** 返回错误且数据不变

### Requirement: 学习曲线追踪

系统 SHALL 按Suite 聚合历史 run 的时间序列（timestamp、model、accuracy、cost），并给出趋势指标；无历史数据时返回空序列而非错误。

#### Scenario: 空历史返回空曲线

- **WHEN** 查询尚无 run 记录的 Suite 学习曲线
- **THEN** 返回 200 与空 data 数组

### Requirement: A/B 测试管理
系统 SHALL 支持 A/B 测试的创建/详情/异步运行/结果查询，运行经 Celery worker 中的 `ABTestRunner`（client/sandbox 工厂可注入），结果含显著性检验；配置与状态持久化且 owner 隔离。运行接口 SHALL 返回统一任务标识 task_id，详情 SHALL 返回同一关联标识，排队和执行状态 SHALL 可通过已有任务接口查询。

#### Scenario: 跨用户资源隔离
- **WHEN** 用户 B 请求用户 A 的实验/基准/A-B 资源
- **THEN** 返回 404，列表不包含他人资源。

#### Scenario: 运行返回统一任务
- **WHEN** 用户运行自己的 pending A/B 测试
- **THEN** 返回 202 与 task_id，详情保留该标识，任务可通过统一接口查询。
