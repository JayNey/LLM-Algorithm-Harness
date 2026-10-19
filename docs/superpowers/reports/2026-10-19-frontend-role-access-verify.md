# frontend-role-access 验证报告

日期：2026-10-19（Asia/Shanghai）。分支：`comet/frontend-role-access`。基线：`b6437098a55eddb40fd13a62e1328a8abbba16c5`。实施提交：`e352332`、`d7aa616`、`78bb65a`。

## 范围和完整性

采用用户确认的单一 tweak 和独立分支。3/3 任务完成；delta spec 增加可信角色来源和前端按角色访问两项需求。完整验证按 change 的简短 `design.md` 对照；tweak 不要求额外 Superpowers Design Doc 或完整实施计划。

`GET /api/v1/users/me` 增加 `role`，与全部监控管理员接口共用 `current_role`；白名单来源保持为 `MONITOR_ADMIN_USER_IDS`。前端角色上下文只存在于已登录路由树，菜单与路由使用相同元数据，系统状态页仅管理员可达。无数据库、注册或角色管理写接口变更，不扩大管理员对他人资源的访问权限。

## 自动验证

- `python3 -m pytest tests/test_api_monitoring.py tests/test_api_auth.py -q --no-cov`：107 passed。
- `python3 -m pytest -m 'not online'`：1751 passed、6 skipped，src 覆盖率 90.46%，达到现有 90% 门槛，退出码 0。日志：`/private/tmp/frontend-role-access-pytest.log`。
- `npm --prefix frontend test`：96 passed，0 failed、0 skipped。包含角色解析、默认拒绝、失败重试、登出卸载忽略响应、并发撤销优先，以及真实 RequireRole / SettingsPage 组件渲染。日志：`/private/tmp/frontend-role-access-final-node.log`。
- `npm --prefix frontend run lint`、`npm --prefix frontend run format:check`、`npm --prefix frontend run build`：退出码 0。生产构建包含独立 SystemPage 代码块。
- Black 检查与 Ruff 检查覆盖本次改动的四个 Python 文件，均通过；`git diff --check` 通过。
- `comet classic openspec -- validate frontend-role-access --type change --strict` 通过。

## 场景映射

- 普通用户、管理员和匿名：真实 HTTP 测试 `test_current_role_matches_live_operator_configuration` 验证 user/admin、401、no-store 以及配置撤销后立即返回 user 和 403。
- 角色伪造：`test_operator_identity_is_not_username_or_token_role` 验证带服务端签名但包含伪造 role 的 Token 仍无管理员权限；`test_profile_update_cannot_grant_role` 验证资料修改不能提权。既有注册输入限制和所有者隔离回归保持通过。
- 会话恢复：RoleAccess 受 RequireSession 保护，每次挂载读取 `/users/me`，不读取浏览器 role 或解析 JWT；加载时 RequireRole 不挂载受限子组件。
- 错误和未知角色：roles 单测验证解析及重试；真实组件测试验证错误、加载时无受限内容；浏览器通过临时 API 故障注入验证角色查询 503 → 错误视图 → 点击重试恢复。
- 普通用户直达：浏览器从匿名 `/settings/system` 进入登录；role_user 登录后回到同一路径并看到无权访问，返回设置只见资料与密钥入口。
- 管理员访问：临时 role_admin 登录后设置出现系统状态入口，页面经真实 API 显示运行时间、评估任务数量和异步任务数量；接口 503 时显示错误，重试恢复。
- 撤销角色：已打开布局中的管理员白名单被临时测试服务撤销，重新访问状态触发后端 403、前端重新查询角色、显示无权访问；返回设置后管理员入口消失。
- 登出隔离：role loader 的 dispose 和版本号测试覆盖迟到响应及旧查询覆盖新角色；浏览器完成普通用户退出、管理员登录，角色与菜单切换正确。
- 响应式：390×844 视口实测系统状态完整可读，`scrollWidth == clientWidth == 390`。检查后恢复默认视口。撤销权限后的截图：`/private/tmp/frontend-role-access-denied.png`。

## 调试记录

先增加 HTTP 测试，复现 `/users/me` 缺少 role 的三个失败，再添加同源判定后通过。前端首先确认角色模块缺失，再实现并运行行为与真实组件测试。

真实组件测试初版虽通过，但 Vite middleware 模式尝试监听 WebSocket，在沙箱中报告 EPERM；本地 Vite 类型定义明确支持 `server.ws=false`，补充禁用 WebSocket 和依赖扫描后，测试不再监听端口。SSR 改用 StaticRouter 消除 MemoryRouter 的 useLayoutEffect 警告，不屏蔽 console。最终前端测试输出无这些错误。

## 审查与结论

最终独立集成审查覆盖 `b643709..78bb65a` 全部差异和 change 产物，未发现 Important 或 Critical；审查者只读检查，未重复运行测试。权限来源、守卫、菜单过滤、登出后的角色响应隔离和失败重试均与规格一致。

审查另核对了挂载期间缓存角色、异常的矛盾授权响应、退出后响应以及普通页加载行为。前者在下一次管理员请求由服务端强制判定，并在 403 后更新角色；矛盾授权需要 `/users/me` 与同源服务端规则相互冲突，正常撤销会返回 user 并停止状态页挂载；异步响应由清理/版本号忽略；普通页面不等待角色是明确需求。这些不构成实现偏差。

结论：PASS。完整性、正确性和设计一致性通过，无未解决的重要问题，可以进入归档前确认。验证时分支仅本地保留。用户随后选择 C，授权归档、推送并创建 PR；Comet 已同步两项新增需求并移动 change。归档后补全主规格 Purpose 对角色控制的说明，同时消除原有的 Purpose 过短校验提示。

## 实测边界

浏览器使用本机临时 SQLite 数据库、临时账号和随机签名/加密密钥；没有修改真实用户或生产配置。故障注入只在 `/private/tmp` 的临时服务脚本内，不进入项目代码。验证结束已关闭浏览器页和两个本机服务。

没有进行在线 LLM 或生产部署验证，角色权限功能不依赖这些服务。后端套件有既有 Pydantic/SQLAlchemy 弃用警告；浏览器存在 Ant Design 静态 message 和 Alert 的 message 属性弃用提示，后者与项目现有表单错误提示使用相同接口，运行与重试正常。
