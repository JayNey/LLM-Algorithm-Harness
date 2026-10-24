## MODIFIED Requirements
### Requirement: 用户日月调用计量
系统 SHALL 按可信服务端用户持久化 UTC 自然日/月生成 SDK 尝试，失败与重试分别计数；缓存、列表、连接验证、无用户 CLI SHALL NOT 计入。系统 SHALL 支持服务端每日和每月非负整数额度，默认无限，零禁止调用。任一额度启用时 SHALL 在每次 SDK 尝试前原子检查两周期并同时计数，任一耗尽时 SHALL 不发请求、不重试该拒绝、不增加任一计数。数据库故障 SHALL 阻止启用限额的调用。无限时保持完成后 best-effort 计量且采集故障不影响结果。计数 SHALL 跨进程重启保留；私有归属和准入回调 SHALL NOT 序列化。

#### Scenario: 重试及隔离
- **WHEN** 甲一次失败后重试成功，乙一次成功且额度充足
- **THEN** 甲日/月各加二，乙各加一，缓存、列表与验证不增加

#### Scenario: 并发与双周期限额
- **WHEN** 多个连接或进程同时调用，日或月仅剩一次
- **THEN** 仅一次准入，其余以 QUOTA_EXCEEDED 拒绝，两周期保持一致

#### Scenario: 重试与失败
- **WHEN** 已准入 SDK 失败并重试，下一次额度不足
- **THEN** 首次失败耗一次，重试不发 SDK 请求且不耗额度

#### Scenario: 周期边界与重启
- **WHEN** UTC 午夜、月首、年首前后准入且重启
- **THEN** 按准入时间落入左闭右开周期，旧计数保留，新周期从零开始

#### Scenario: 用量查询
- **WHEN** 用户查询 quotas
- **THEN** 返回自身 used、UTC 和起止时间；无限周期保留 metered/null limit，有限周期返回 enforced、limit 和非负 remaining，并标明准入计数语义

#### Scenario: 故障及隐私
- **WHEN** 存储故障或配置序列化
- **THEN** 限额启用时服务不可用且不发请求，无限时原模型结果不变；私有归属不泄露，聚合表不含提示、响应、凭证
