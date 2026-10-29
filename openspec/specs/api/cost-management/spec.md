# api/cost-management Specification

## Purpose
提供按用户隔离的任务费用查询、时间段汇总、趋势和分项统计，统一 evaluation、benchmark、实验与 A/B 的已知费用及完整性语义，并支持预算配置、执行累计、预警规则和定价覆盖版本追溯。

## Requirements

### Requirement: 成本查询聚合

系统 SHALL 从既有业务表（evaluations/experiments/benchmark_runs/ab_tests）按 owner 作用域聚合成本：按 id 解析单任务成本、按时间段输出用户汇总、按日趋势序列与按来源类型/模型/策略的分解；时间段参数非法时 SHALL 返回 400。实验及 A/B 的实际调用费用 SHALL 按 UTC 发生时间持久化；运行中、暂停、取消和失败任务已发生费用 SHALL 保留，同一事件重放、完成单元恢复及重复消息 SHALL 不重复计费。缓存命中 SHALL 仅产生已知零增量。

#### Scenario: 跨表任务解析

- **WHEN** 以 benchmark run 的 id 请求任务成本
- **THEN** 返回该 run 的 cost_usd 与状态；以不存在的 id 请求返回 404

#### Scenario: 空时间段返回空序列

- **WHEN** 查询无任何花费记录的时间段
- **THEN** 汇总为 0、趋势与分解为空数组而非错误

汇总、趋势、分项、任务报告和预算 SHALL 使用同一 owner 范围内的已知费用；task_count SHALL 按来源和任务去重，已有 evaluation 与 benchmark SHALL 不因新记录而双计。响应 SHALL 保留现有字段及容器，兼容增加已知金额、完整性、未知记录数量和原因；缺价格、缺用量及历史缺口 SHALL 明确未知，完全未知单任务金额 SHALL 为 null，部分已知返回已知小计并标记不完整。

#### Scenario: 持久化至 HTTP 且状态独立
- **WHEN** 实验及 A/B 已发生可定价调用后暂停、取消或失败
- **THEN** HTTP 单任务、汇总、趋势、分项和报告可核对已知费用，其他用户不可见

#### Scenario: 日期与重复执行
- **WHEN** 查询调用发生日期或在完成检查点上恢复，重复投递相同消息或回放相同费用事件
- **THEN** 日期过滤含该日全部 UTC 记录，同一消耗不重复计入；实际新调用作为新消耗记录

#### Scenario: 未知与历史回填
- **WHEN** 响应缺价格或缺用量，或迁移前任务只有总 tokens
- **THEN** 不估算未知金额，已知小计与不完整状态同时返回；历史回填只采用明确保存的金额快照，重复执行回填不重复计费

### Requirement: 用户预算配置与使用情况

系统 SHALL 为每用户维护一份预算配置（全局上限、按难度分配、阈值行为 pause/downgrade），upsert 语义；使用情况 SHALL 返回全局 used/remaining/percentage 与按难度的比例估计（basis 字段注明估计口径）。

#### Scenario: 未配置预算的用量查询

- **WHEN** 用户未配置预算即查询使用情况
- **THEN** 返回 used 统计且 cap 为 null，而非错误

全局预算展示与执行读取 SHALL 采用与费用统计相同的已知累计来源，包含实验及 A/B 在所有任务状态下的已保存费用；执行读取 SHALL 不把未知金额当作已知免费。新增费用有明确难度时 SHALL 按实际加入，原有 evaluation 的展示比例估计 SHALL 保持注明 basis。

#### Scenario: 四来源预算一致
- **WHEN** 同一用户有 evaluation、benchmark、实验和 A/B 费用
- **THEN** 全局预算展示和执行读取的已知累计与不限定日期的费用汇总相等，并保持用户隔离

### Requirement: 预警规则与触发历史

系统 SHALL 支持预警规则的创建/更新/删除/列表（threshold_pct、channel、target），非法通道与越界阈值 SHALL 被拒绝；响应中的 webhook/邮件目标 SHALL 脱敏；触发历史 SHALL 从 alert_events 按 owner 返回。

#### Scenario: 非法规则被拒绝

- **WHEN** 提交 threshold_pct 为 0 或 channel 为未知值的规则
- **THEN** 返回 400 且不落库

#### Scenario: 目标脱敏

- **WHEN** 列出包含 webhook URL 的规则
- **THEN** 响应仅含脱敏后的目标（保留协议与主机）

系统 SHALL 在 Web 评估开始及单元成本提交后按 owner 检查启用规则，以个人全局预算和已知累计成本触发 Slack、HTTPS Webhook、SMTP 或 log。成功投递 SHALL 写入现有历史；同一规则、阈值与上限的成功通知 SHALL 在后续单元及任务恢复时去重。失败 SHALL 有界重试且脱敏，不阻断评估或预算动作；下一次 worker 恢复允许重试。

#### Scenario: Web 规则真实发送
- **WHEN** 用户保存启用的 Slack、Webhook 或邮件规则且累计已知成本达到阈值（含 100%）
- **THEN** worker 向规则目标发送预算摘要并记录该用户成功历史

#### Scenario: 恢复去重与失败隔离
- **WHEN** 成功规则再次达到相同上限阈值或 worker 恢复，另一个渠道发送失败
- **THEN** 成功规则不重复发送，失败不影响其他规则、评估结果或预算暂停，恢复时可重试失败规则

#### Scenario: 未启用和其他用户规则
- **WHEN** 规则禁用、属于其他用户、无个人全局预算或尚未达到阈值
- **THEN** 不发送该规则且不产生成功历史

### Requirement: 定价目录与覆盖版本

系统 SHALL 合并 PricingManager 内置定价、自定义文件与数据库覆盖行（覆盖优先）返回定价目录；自定义覆盖 SHALL 以追加版本方式入库（同 model 多行，最新生效）并支持追溯历史。既有保存和历史接口 SHALL 接受含斜杠的完整模型 ID，URL 编码只解码一次，目录键、保存响应及历史归属 SHALL 保持模型原值；普通模型地址、认证、200 字符长度上限与价格校验 SHALL 保持兼容。

#### Scenario: 覆盖生效且可追溯

- **WHEN** 对同一 model 先后提交两次自定义定价
- **THEN** 目录查询返回最新版本，同时可查询到两条历史版本记录

#### Scenario: 含斜杠模型的真实 HTTP 往返

- **WHEN** 已认证用户经真实 HTTP 向 Qwen/Qwen2.5-7B-Instruct 的编码地址追加两次定价并查询历史
- **THEN** 保存响应与目录键保留完整模型名，历史按最新优先返回该模型的两个版本

#### Scenario: 编码与历史路径不混淆

- **WHEN** 分别保存普通模型、含多层斜杠、末尾 history、字面 %2F 或 URL 特殊字符的模型并查询各自历史
- **THEN** 各模型原值独立保存，历史只属于所请求模型，百分号不会重复解码

#### Scenario: 扩展路径保留认证与校验

- **WHEN** 对含斜杠模型未认证访问或提交过长模型名、空模型名或非法价格
- **THEN** 请求被拒绝且不新增定价记录

### Requirement: 个人预算执行控制

系统 SHALL 在每个 Web 评估单元派发前按所有者读取个人预算及已知累计成本，达到全局上限或该单元难度上限时执行 pause/downgrade。全局用量 SHALL 覆盖用户评估累计成本、已完成基准运行成本以及实验和 A/B 所有状态下已持久化的已知调用成本；分难度执行用量 SHALL 采用已持久化评估结果的实际已知成本，不将展示用比例估计视作精确结算。缺少可归属难度的结果仅参与全局用量。控制 SHALL 在单元边界生效，不中断在途调用、不预留跨任务并发额度。

#### Scenario: 全局触顶后暂停
- **WHEN** 已保存 pause，用户已知累计支出达到全局上限
- **THEN** 评估在下一单元前持久化 paused，未开始单元不执行，已完成结果和成本保留

#### Scenario: 分难度触顶
- **WHEN** 某难度实际已知成本达到其上限，其他难度未触顶
- **THEN** 只有执行该难度单元时触发动作，其他难度继续使用原策略

#### Scenario: 降级实际执行并可追溯
- **WHEN** 已保存 downgrade，某单元适用的个人上限已达到
- **THEN** 该单元实际采用 vanilla，持久化结果记录 executed_strategy 和 cost_downgraded，保留原单元身份避免结果冲突

#### Scenario: 单任务上限及手动暂停优先
- **WHEN** 个人配置 downgrade，但单任务上限已达到或用户请求暂停
- **THEN** 任务暂停而不派发下一单元

#### Scenario: 恢复重新检查
- **WHEN** 预算暂停后用户调整预算并恢复评估
- **THEN** 按最新预算重新判断，仅执行未完成单元，不重复累计成本；预算仍不足则继续暂停

#### Scenario: 用户隔离与未配置兼容
- **WHEN** 当前用户未保存预算，或只有其他用户的支出与预算
- **THEN** 评估沿用原策略和单任务约束，不受其他用户影响
