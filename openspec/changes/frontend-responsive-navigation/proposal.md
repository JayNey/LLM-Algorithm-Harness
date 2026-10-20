## Why

Issue #168 需要将已经确认的 Frontier 品牌与三套可运行设计接入真实前端。现有外壳只有顶部文字导航，尚缺分组侧栏、移动底栏、通知中心及可持久化的即时风格切换。

## What Changes

- 接入 Frontier SVG，保留 Orbit、Precision、Studio 三套风格与各自浅色、深色、跟随系统偏好。
- 扩展现有 UI store；切换风格保持路由、筛选、表单草稿与通知状态。
- 共享导航元数据，提供桌面折叠侧栏、平板/手机抽屉、手机底栏、面包屑、快捷操作与用户菜单。
- 基于 Ant Design 实现本地 Mock 通知、业务示例、加载/空/错误与重试、页面异常边界。
- 增加基准测试、帮助入口；复用现有认证、账号设置、管理员权限与真实登出。

## Capabilities

### New Capabilities

无。扩展现有 `frontend/app-shell`，不引入后端 API 或数据库能力。

### Modified Capabilities

- `frontend/app-shell`：完善导航、响应式外壳、外观偏好、通知与公共状态的验收行为。

## Impact

仅修改前端及对应规格/验证文档，不新增依赖，不变更认证和权限策略。业务与通知为显式标注的 Mock；既有个人资料、API 密钥、系统监控仍使用现有服务。独立分支为 `codex/issue-168-responsive-navigation`。
