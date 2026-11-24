## ADDED Requirements

### Requirement: 实验与 A/B 列表读取受分页约束

实验与 A/B 列表 SHALL 在数据库中按所有者和可选状态筛选、按 created_at 和 id 升序稳定排序并应用 LIMIT/OFFSET，仅加载当前页业务实体；total SHALL 由相同筛选条件的独立计数查询返回。列表 SHALL 保持现有响应、分页元数据及实验 task_id 关联语义，只查询响应必需字段，并将关联查询限定于当前页资源。

#### Scenario: 大历史中的固定页大小

- **WHEN** 当前用户存在 200 条以上实验或 A/B 记录，以 limit=20 请求一页
- **THEN** 对应业务实体加载数至多为 20，SQL 含分页约束，total 等于全部匹配记录数

#### Scenario: 过滤与稳定排序

- **WHEN** 不同所有者和状态的记录具有相同创建时间，用户筛选状态并分页
- **THEN** 数据库在计数和分页前应用归属与状态筛选，按 id 打破时间平局，后续页及 task_id 正确

#### Scenario: 空页

- **WHEN** 筛选无记录或 offset 超过匹配总数
- **THEN** 返回空列表和准确 total，不加载其他页业务实体或关联任务

### Requirement: 列表配置不读取完整冻结题库

实验和 A/B 列表 SHALL 在数据库查询投影中排除 dataset_snapshot.problems 和 dataset_snapshot.owner_id，仅将公开配置及快照摘要传输到应用；SHALL 保留现有公开字段、空值和无快照旧配置语义。SQLite 与 PostgreSQL SHALL 均支持该查询；列表读取 SHALL NOT 修改持久化配置或影响详情与执行时的完整快照。

#### Scenario: 大快照仅返回摘要

- **WHEN** 当前页实验或 A/B 配置包含完整冻结题目和快照元数据
- **THEN** 数据库返回给应用的配置不含完整题目与所有者，响应保留配置和公开快照摘要，库内原快照完整

#### Scenario: 旧配置与空快照

- **WHEN** 列表记录没有 dataset_snapshot，或其值为 null
- **THEN** 响应保留原有缺失键或 null 语义，无额外逐行查询，也不补出伪造快照
