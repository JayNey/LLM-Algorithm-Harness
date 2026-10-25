## ADDED Requirements

### Requirement: 基础 API 就绪检查
服务 SHALL 提供无需认证的 GET /api/v1/health/ready，只返回 status，值为 ready 或 not_ready，分别对应 HTTP 200 或 503，响应 SHALL 禁止 HTTP 缓存。就绪 SHALL 复用实际数据库探测，要求认证、文件与业务数据库和业务迁移全部通过；异常和不确定证据 SHALL 判定未就绪。Redis、worker、沙箱 SHALL 不参与基础 API 判定。

#### Scenario: 数据库通过
- **WHEN** 必需数据库与迁移均为 ok，其他可选诊断禁用
- **THEN** 返回 200 和 {"status":"ready"}，不执行其他探测

#### Scenario: 数据库故障与未知
- **WHEN** 任一必需库不可用、缺表、迁移不匹配、未知或探测异常
- **THEN** 返回 503 和 {"status":"not_ready"}，不泄露详情，存活检查仍为 200

### Requirement: 有界探测与短缓存
服务 SHALL 使用 1 秒探测响应预算和 1 秒单调时钟进程内结果缓存；成功和失败均缓存；同一实例最多一个在途探测。超时 SHALL 返回 503，不复用旧成功或迟到成功，不允许阻塞探测导致后台线程持续增长。

#### Scenario: 缓存与过期
- **WHEN** 重复请求位于缓存有效期内或缓存到期
- **THEN** 有效期内复用结果，到期重新探测，不使用过期成功

#### Scenario: 并发和超时
- **WHEN** 并发请求遇到缓慢或阻塞探测
- **THEN** 合并为单个在途探测，请求在预算内返回未就绪；迟到结果不得恢复就绪，下次新探测成功才能恢复

#### Scenario: 实例隔离
- **WHEN** 两个 API 实例依赖状态不同
- **THEN** 缓存与在途状态互不影响
