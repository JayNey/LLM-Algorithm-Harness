## Why
Web 已保存成本预警规则，但评估 worker 未读取或投递；用户无法收到真实预算通知。

## What Changes
- 复用 CLI 通道发送逻辑，在 Web 评估运行开始和单元成本提交后检查用户规则。
- 按个人全局预算及已知累计成本判断阈值，成功写入现有历史并去重。
- SMTP 连接由服务端环境配置，规则 target 为收件地址；失败脱敏且不影响评估。

## Capabilities
### New Capabilities
无。
### Modified Capabilities
- `api/cost-management`: 预警规则接入运行期投递。

## Impact
成本预警发送器、Web 成本服务、Celery 评估回调、测试和通知配置文档。无数据库迁移或新增 HTTP API。用户选择新建分支并继续 tweak（BA），允许此次跨模块通知链路接线。
