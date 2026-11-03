## MODIFIED Requirements

### Requirement: 实验生命周期管理

系统 SHALL 支持创建（校验模型/策略/预算配置与 `api_key_id` 归属）、列出、查看、异步运行固定预算实验，并以 `pending/running/paused/completed/failed/cancelled` 跟踪状态；实验配置与状态 SHALL 持久化，结果分析 SHALL 从跨进程共享且可配置的 `RESULTS_ROOT` 产物根读取。

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

系统 SHALL 从完成的实验产物中返回结果摘要、模型×策略对比（含胜率矩阵与 McNemar 显著性）、以及交互面板数据；产物 SHALL 位于 API 与 Worker 共同可用的 `RESULTS_ROOT` 下，读取 SHALL NOT 依赖发起请求进程的当前工作目录。产物缺失或实验未完成时 SHALL 返回明确错误。

#### Scenario: 未完成实验不可取结果

- **WHEN** 对 running 状态的实验请求对比报告
- **THEN** 返回明确错误而非部分数据

#### Scenario: 分离进程读取结果

- **WHEN** Worker 在共享 `RESULTS_ROOT` 下完成实验，API 进程以不同当前工作目录启动后请求结果、对比与面板
- **THEN** 三个端点均返回该实验的完整产物，而非 artifacts missing

## ADDED Requirements

### Requirement: 实验与 A/B 的跨进程结果和检查点

系统 SHALL 把实验和 A/B 的结果、对比、面板与执行检查点存放到可配置的 `RESULTS_ROOT`，并通过共享卷或等价共享存储让 API 与全部 Worker 访问同一位置；相对历史路径 SHALL 解析到该根而不是发起请求进程的 cwd。启动 SHALL 校验该根可创建且可写，不可写时 SHALL 以明确错误拒绝启动。

#### Scenario: A/B 分离进程读取结果

- **WHEN** Worker 完成 A/B 测试且 API 进程在另一个容器或另一 cwd 中请求该测试结果
- **THEN** 返回包含变体与显著性统计的结果，而不是 artifacts are missing

#### Scenario: 重启或换 Worker 后恢复

- **WHEN** 暂停的实验或 A/B 在 Worker 重启或被另一个 Worker 接续时恢复
- **THEN** 从共享 `RESULTS_ROOT` 读取同一检查点，已提交单元不重复执行

#### Scenario: 结果根不可写

- **WHEN** `RESULTS_ROOT` 无法创建或对当前进程只读
- **THEN** API 或 Worker 启动失败并报告具体路径，不进入任务消费或执行
