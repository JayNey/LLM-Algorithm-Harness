## ADDED Requirements

### Requirement: 实际任务耗时与成功率统计
系统 SHALL 记录真实业务任务首次开始与终态结束时间，状态及进度更新均支持记录，重复通知不得覆盖已有时间；任务重新 running SHALL 清除旧结束时间。管理员性能接口 SHALL 基于持久化业务 AsyncTask 返回全部任务与评估任务统计，明确累计范围、样本数与秒单位。耗时 SHALL 仅使用 completed/failed 且开始结束有效的记录；成功率 SHALL 为实际开始的 completed/(completed+failed)，取消、未执行任务不计入。耗时包含暂停和重试间隔，排除首次排队时间。

#### Scenario: 时间记录与重试
- **WHEN** 任务通过状态或进度进入 running 后结束，或结束后重新进入 running
- **THEN** 首次开始与终态结束被记录，重复通知保留时间，重新 running 清空旧结束时间

#### Scenario: 真实任务聚合
- **WHEN** 存在已执行的成功、失败任务及取消、未执行或时间无效的任务
- **THEN** 性能接口按上述口径返回平均执行秒数、成功率和样本数，评估子集不包含其他类型

#### Scenario: 空样本与不可用
- **WHEN** 没有有效样本或任务数据库不可用
- **THEN** 无样本指标返回 null，数据库不可用返回 unavailable 且不暴露异常内容
