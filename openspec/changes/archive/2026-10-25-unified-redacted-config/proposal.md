## Why

现有配置查询分散且没有统一的运行配置视图。管理员需要在不暴露凭据和部署路径的前提下查看当前 API 进程已经加载的配置。

## What Changes

- 新增只读管理员接口 `GET /api/v1/system/config`，使用现有认证、响应信封和 no-store 策略。
- 按 api/auth/files/monitoring 四组显式白名单提取生效配置；不暴露凭据、连接串、本地路径、管理员身份列表或任意扩展字段。
- 补充权限、环境覆盖、未知字段排除和无外部探测的回归测试及 API 文档。

## Capabilities

### New Capabilities
- `api/system-config`: 统一脱敏的生效配置查询。

### Modified Capabilities

无。

## Impact

仅涉及现有监控配置模块、监控路由、接口文档及测试，无数据库或依赖变更。用户已选择继续 tweak 与新建分支。
