## MODIFIED Requirements

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

