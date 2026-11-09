## Why

[#431](https://github.com/JayNey/LLM-Algorithm-Harness/issues/431) 中，管理员首页和系统页只显示常规监控的「未检查」，需要从页面按需验证 Docker 沙箱是否可用。

## What Changes

- 在管理员首页和系统页提供沙箱检查操作，显示未检查、检查中、正常、不可用和请求失败。
- 请求失败后允许在当前页面重试。同一控件仅允许一个在途请求。
- 常规监控刷新继续读取轻量快照。诊断使用既有管理员端点。

## Capabilities

### Modified Capabilities

- `frontend/system-monitoring` 增加管理员按需诊断的要求。

## Impact

涉及前端两处监控视图、共用控件、监控客户端、双语文案和浏览器验证。继续沿用既有服务端权限和探针缓存。用户确认保持 tweak 流程，相关文件共同交付同一项诊断功能。
