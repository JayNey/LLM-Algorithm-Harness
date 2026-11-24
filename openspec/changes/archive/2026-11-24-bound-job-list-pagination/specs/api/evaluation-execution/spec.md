## ADDED Requirements

### Requirement: 评估列表读取受分页约束

系统 SHALL 在数据库中对当前用户的评估应用可选状态筛选、created_at 和 id 升序排序及 LIMIT/OFFSET，仅加载当前页评估实体；匹配 total SHALL 由相同筛选条件的独立计数查询获得。列表 SHALL 仅加载响应必需字段，保留现有成本、进度和操作能力语义，关联查询 SHALL 限定于当前页资源。

#### Scenario: 历史增长不扩大单页实体加载

- **WHEN** 同一用户有 200 条以上评估，以 limit=20 请求一页
- **THEN** 至多加载 20 个评估实体，SQL 包含分页约束，total 为全部匹配记录数，不读取响应无需使用的 problem_ids

#### Scenario: 状态归属及同时间排序

- **WHEN** 数据含不同所有者、不同状态和相同创建时间，用户指定状态并请求后续页
- **THEN** 在分页和计数前应用归属与状态筛选，按 id 打破创建时间平局，total 和现有响应字段正确

#### Scenario: 空结果与越界页

- **WHEN** 筛选无匹配记录，或 offset 超过匹配总数
- **THEN** 返回空列表和真实匹配 total，不加载评估实体，也不查询其他页的关联数据
