## ADDED Requirements

### Requirement: 用户日月调用计量
系统 SHALL 按可信服务端用户持久化 UTC 自然日/月已成功记录的生成 SDK 尝试，失败与重试分别计数；缓存、列表、连接验证、无用户 CLI SHALL NOT 计入。日/月更新 SHALL 原子且跨进程重启保留，不受监控样本清理影响；采集故障 SHALL NOT 改变模型结果，内部归属 SHALL NOT 通过配置序列化输入输出。

#### Scenario: 重试及隔离
- **WHEN** 甲一次失败后重试成功，乙一次成功
- **THEN** 甲日/月各加二，乙各加一，缓存、列表与验证不增加

#### Scenario: 周期边界与重启
- **WHEN** UTC 午夜、月首、年首前后完成生成且重启
- **THEN** 按完成时间落入左闭右开周期，旧计数保留，新周期从零开始

#### Scenario: 用量查询
- **WHEN** 用户查询现有 quotas
- **THEN** 日/月字段返回整数 used（空时零）、metered、null limit、UTC 时区和起止时间、统计范围与 best-effort 语义，不回填历史

#### Scenario: 故障及隐私
- **WHEN** 存储故障或配置序列化
- **THEN** 原响应或异常不变，无额外请求，私有归属不泄露，聚合表不含提示、响应、凭证
