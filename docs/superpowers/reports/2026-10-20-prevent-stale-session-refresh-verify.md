# 迟到刷新会话隔离验证报告

- Change：`prevent-stale-session-refresh`
- 日期：2026-10-20
- 关联：issue #161 核对发现的登出竞态
- 分支：`comet/prevent-stale-session-refresh`
- 基线：`ab0497e1bdfda6def69d8d556b14c7ec84da1c96`
- 实现提交：`5546afc`
- 结论：PASS

## 问题与根因消除

刷新完成时无条件写入凭证，会恢复已经登出的前端会话；刷新失败时无条件 clear，也会清除后来登录的新会话。

`frontend/src/auth/http.ts` 在刷新开始时保存 accessToken、refreshToken，只有当前凭证仍与之匹配，才允许成功写回或失败清除。过时的成功结果以 ApiClientError 拒绝，不继续重试原受保护请求；过时的失败也不改变当前会话。无会话时不再发起刷新。按凭证值比较兼容存储反序列化产生新对象，原有正常刷新与并发合并保持通过。

根因消除检查确认成功路径与失败路径均有当前会话校验；原无条件 write/clear 入口已被保护。没有改变公共接口、后端、存储格式或路由，恢复的是既有 `frontend/auth-session` 登出语义，故无 delta spec。

## RED 证据

修复前执行：

- `node --experimental-strip-types --test --test-name-pattern='迟到刷新隔离' frontend/src/auth/http.test.ts`：8 failed，覆盖提前刷新/401 × 清除/新会话 × 成功/失败。失败表现为请求仍成功、旧刷新覆盖新会话或清除新会话。日志 `/tmp/stale-refresh-red.log`。
- `node --experimental-strip-types --test --test-name-pattern='刷新晚于' frontend/src/store/auth.test.ts`：4 failed，覆盖 clear/logout × localStorage/sessionStorage；真实 store 与 HTTP 客户端在迟到刷新后恢复会话。日志 `/tmp/stale-refresh-store-red.log`。

用受控 Promise 暂停网络响应，等待刷新确实开始后才清除或替换会话，不使用 sleep 推测顺序。store 集成测试保留真实登出调用，并验证当前 Bearer 头、本地两类存储和原请求发送次数。

## GREEN 与最终验证

工作目录 `frontend/`，提交前与提交后均执行：

- `npm test`：**108 passed，0 failed，0 skipped**，包括全部新增 12 个回归，以及正常刷新、并发刷新、401 重试、刷新失败清理、登录/登出等既有回归。
- `npm run lint`：通过。
- `npm run format:check`：全部匹配文件符合 Prettier。
- `npm run build`：TypeScript 与 Vite 生产构建通过。
- 仓库根 `git diff --check` 与 `comet classic openspec -- validate prevent-stale-session-refresh --strict`：通过。

最终测试日志 `/tmp/stale-refresh-final-test.log`，最终构建日志 `/tmp/stale-refresh-final-build.log`。

## 六项轻量验证

- [x] tasks.md 单项任务完成且已提交。
- [x] 实现范围与任务一致：仅 HTTP 模块及两份测试，共 3 个源码/测试文件。
- [x] TypeScript 检查和生产构建通过。
- [x] 原 bug 的失败测试转绿，前端全量 108 项测试通过。
- [x] 未引入真实凭证、外部调用、权限扩展或 Token 格式变化。
- [x] 按 hotfix 默认 `review_mode: off` 跳过自动独立代码审查；已检查最终 diff、两条副作用路径与回归覆盖。

规模脚本统计 15 个文件，其中 12 个为本 change 产物与自动元数据；实际为 1 项任务、3 个源码/测试文件、零 delta spec，因此按允许的覆盖机制采用 light。未命中运行时能力、公共 API、架构或数据库升级信号。

本次验证针对前端 HTTP 竞态，未重复运行后端 Python 套件或真实提供商调用；未进行浏览器视觉验收。用户已选择 C，授权归档、推送并创建 PR。报告与 Comet 验证状态纳入本次归档提交；归档目录为 `openspec/changes/archive/2026-10-20-prevent-stale-session-refresh`，归档完整性守卫通过。
