# 业务列表的有界读取

## Context

动机见 proposal.md。三个服务均使用 SQLAlchemy，业务数据库支持 SQLite 和 PostgreSQL。列表排序已经是 created_at/id 升序；实验和 A/B 的 config 为 JSON，public_dataset_config 目前在完整配置加载后才移除冻结题目和所有者。

## Goals / Non-Goals

实现 delta specs 定义的数据库分页、独立计数和必要字段投影，保持既有响应。无需迁移或前端改动，不调整详情与 worker 读取路径，不改变已有分页参数校验。

## Decisions

1. 各服务复用同一组 owner/status 筛选条件，分别执行 COUNT 与带 ORDER BY/LIMIT/OFFSET 的页查询。保留现有排序，避免先加载全部实体和 Python 切片。
2. 评估列表通过 ORM 字段投影仅加载响应及能力计算依赖的属性，尤其不读取 problem_ids。成本和异步任务查询保持当前页约束，空页跳过关联查询。
3. 为实验和 A/B 复用一个数据库公开配置表达式，SQLite 用 JSON 路径删除，PostgreSQL 用 JSONB 路径删除并保持 SQLAlchemy JSON 解码。只移除快照内的 problems/owner_id，保留其余配置及未知公开字段；不采用固定字段白名单，以免破坏旧配置与将来扩展字段。
4. 实验与 A/B 使用必要字段投影及公开配置表达式，避免 ORM 再次惰性读取完整 config。JSON 转换限于列表 SELECT，不 UPDATE 原始配置。现有 public_dataset_config 可继续作为响应裁剪的兼容保障。

## Risks / Trade-offs

- COUNT 仍须统计匹配历史，OFFSET 仍有数据库扫描成本；本次约束应用层实体数量及快照传输，不宣称数据库总扫描量恒定。
- 两次查询之间并发写入可能使 total 与页短暂变化，沿用既有分页一致性级别，不引入额外隔离或锁。
- JSON 删除表达式有方言差异：SQLite 做真实查询与结果验证；PostgreSQL 做方言编译验证，有可用独立测试库时补真实执行，并如实记录验证边界。
- 精简字段可能触发惰性加载：监听 SQL/ORM load 事件验证无额外逐行读取，覆盖成本、操作能力及实验任务关联已有回归。

## Validation

使用隔离 SQLite 数据库，在同一创建时间插入至少 200 条本人记录及其他用户/状态记录。监听 before_cursor_execute 和实体 load，验证 SQL 分页、20 条实体上界、COUNT、offset、稳定排序、过滤、空页、必要字段和快照数据库返回内容。覆盖无快照/null 快照、列表与既有安全详情一致、原始快照未改写。运行相关评估/实验/A-B 回归、ruff 和 OpenSpec 严格校验；不调用真实付费模型。
