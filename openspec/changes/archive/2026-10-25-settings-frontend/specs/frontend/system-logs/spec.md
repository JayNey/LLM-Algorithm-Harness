## ADDED Requirements

### Requirement: 系统日志查询

admin SHALL 能查询系统日志：按级别（INFO/WARNING/ERROR）、时间范围、关键词搜索并分页；不支持实时流与下载时 SHALL NOT 提供假入口。非 admin SHALL NOT 可见该页。

#### Scenario: 日志筛选查询

- **WHEN** admin 选择级别与时间范围并搜索关键词
- **THEN** 列表按条件分页展示匹配日志

#### Scenario: 无结果如实展示

- **WHEN** 查询无匹配
- **THEN** 页面展示无结果提示而非空表
