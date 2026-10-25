# frontend/system-monitoring Specification

## Purpose
TBD - created by archiving change settings-frontend. Update Purpose after archive.

## Requirements

### Requirement: 系统监控面板

admin 设置页 SHALL 聚合展示系统监控：组件健康（数据库/Redis/Workers/沙箱）、资源（CPU/内存/磁盘）、队列长度（pending/reserved）、任务计数、API 统计（请求数/QPS/平均与 P95 响应/错误率，窗口可选）、LLM 调用统计（次数/成功率/平均延迟，窗口可选）与跨 worker 缓存命中。数据 SHALL 全部来自既有只读端点；SHALL 支持手动刷新与可关闭的自动刷新（页面隐藏时暂停）。普通用户 SHALL NOT 可见该面板（角色门禁）。

#### Scenario: 监控分区渲染

- **WHEN** admin 打开系统页
- **THEN** 健康、资源、队列、任务、API、LLM、缓存各分区按端点数据渲染，异常组件状态如实标注

#### Scenario: 统计窗口切换

- **WHEN** admin 切换 API/LLM 统计窗口
- **THEN** 以新窗口参数重新请求并更新展示
