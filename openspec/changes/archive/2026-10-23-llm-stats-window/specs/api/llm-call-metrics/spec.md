## ADDED Requirements

### Requirement: 按统计窗口查询模型调用
系统 SHALL 在现有管理员 GET /api/v1/metrics/llm-stats 接受可选整数 window_seconds，范围 1–86400。指定时 SHALL 按完成时间位于 [查询时间-window_seconds, 查询时间] 的已记录尝试聚合 total_calls、successful_calls、failed_calls、success_rate（成功/全部）及 avg_latency_ms（全部尝试耗时均值）；省略时 SHALL 保持累计统计。重试分别计数，缓存与验证排除，独立用量登记与验证计数保持累计口径。

#### Scenario: 时间窗口和边界
- **WHEN** 管理员指定窗口，存在窗口前、恰好起点、窗口内、恰好终点与未来的记录
- **THEN** 仅包含起点至终点内的记录，返回窗口大小和起止时间，成功率及耗时按这些记录计算

#### Scenario: 空窗口与参数权限
- **WHEN** 完整窗口内没有记录
- **THEN** 计数为零、成功率及平均延迟为 null；非法窗口返回 400，未认证返回 401，普通用户返回 403

### Requirement: 窗口记录保留边界
系统 SHALL 有界保留窗口记录，跨进程连接及重启保持一致。系统 SHALL 不用旧累计计数伪造历史窗口；当窗口超出窗口采集起点或包含被清理记录时 SHALL 返回 window_complete=false、主指标 null，并通过 retained_sample 提供保留样本。响应 SHALL 明确 best-effort 范围；累计统计 SHALL 不受窗口清理影响。

#### Scenario: 采集启动与旧库升级
- **WHEN** 旧数据库已有累计调用，窗口采集刚初始化
- **THEN** 累计值保持不变，覆盖采集前的窗口标记为不完整，历史调用不回填

#### Scenario: 清理与重启
- **WHEN** 行数或时限清理丢弃窗口内记录后重启或更换查询连接
- **THEN** 删除水位仍可见，窗口保持不完整；后续不包含删除记录的窗口可完整聚合

## MODIFIED Requirements

### Requirement: 采集故障隔离与隐私
系统 SHALL 保证采集初始化、计时或持久化失败不改变原请求结果或重试策略；采集 SHALL 仅持久化固定键的聚合数值，以及窗口所需的完成时间、成功标志与耗时数值，不保存提示、响应、凭证、端点或异常正文。未配置服务端认证的 CLI 请求 SHALL 正常执行。累计统计 SHALL NOT 声称覆盖采集前历史、未配置客户端或采集故障时遗漏的请求。

#### Scenario: 写入失败或计时失败
- **WHEN** 模型成功或失败，同时采集不可用
- **THEN** 原响应或异常继续返回，不产生监控引起的额外请求，统计明确为已成功记录的请求范围

#### Scenario: 敏感内容
- **WHEN** 请求或异常中含提示、响应和凭证
- **THEN** 采集存储只含固定聚合键与数值、完成时间、成功标志和耗时数值，不包含这些内容
