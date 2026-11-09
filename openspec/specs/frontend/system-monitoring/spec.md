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

### Requirement: 管理员按需检查沙箱

首页与系统页 SHALL 为已确认的管理员提供按需沙箱检查。操作 SHALL 调用既有受保护的沙箱健康端点，并分别显示未检查、检查中、正常、不可用及请求失败。请求在途时 MUST NOT 重复提交。普通用户 MUST NOT 看到操作，其直接请求 SHALL 由服务端拒绝。

#### Scenario: 读取诊断结果

- **WHEN** 管理员在任一页面点击检查沙箱
- **THEN** 页面显示检查中并禁用检查操作，收到响应后如实显示正常或不可用及可用说明

#### Scenario: 请求失败后重试

- **WHEN** 检查请求超时或失败
- **THEN** 页面显示请求失败并允许管理员就地重试

#### Scenario: 常规刷新

- **WHEN** 管理员打开页面或触发手动或自动监控刷新
- **THEN** 只读取常规监控快照，沙箱探针只由独立诊断操作触发，已有诊断结果保留在当前页面

#### Scenario: 普通用户访问

- **WHEN** 普通用户打开首页、尝试访问系统页或直接调用沙箱健康端点
- **THEN** 界面无检查操作，直接诊断请求返回 403
