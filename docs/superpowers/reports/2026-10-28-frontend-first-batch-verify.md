# 第一批前端联合交付验证

日期：2026-10-28。关联：#298、#299、#301。用户确认三个 issue 一起实现并提交一个 PR。

## 实现

- 全局侧栏、顶部、移动抽屉和移动底栏导入操作进入真实题库面板；`import=1` 支持直接访问与刷新，筛选/分页和收起操作保留相应参数。
- 导入提交使用同步锁和非终态 job 状态保护，取消选择不提交，会话切换拒绝旧响应；收起面板在当前题库路由内保留进度。
- 结果详情提供 Markdown、HTML、CSV 即时报告下载，使用结果 run_id。复用配置 API 地址及 Cookie/会话刷新；防重复下载、缺失运行标识、权限错误、文件名回退和对象 URL 回收均有处理。
- 预算提示说明真实渠道、触发条件、worker SMTP 配置与站内 Mock 边界；暂停导入提示说明此页面无恢复/取消入口并显示 job ID。最新 main 已支持后端非评估任务恢复，文案不宣称后端能力缺失。

## 检查结果

- `npm test`：退出 0，288 tests passed，无 skip。
- `npm run lint`：退出 0。仅保留未修改的 BenchmarkDetailPage 两条 useCallback 依赖警告。
- `npm run build`：退出 0，包含 `tsc -b`。保留既有大 chunk 提示。
- 三个 OpenSpec change 的 strict validation：退出 0。
- Prettier 和 `git diff --check`：通过。
- 独立 Bugbot 对联合改动审查：未发现 actionable issues。

## TDD 与浏览器证据

- 导入 URL helper 测试先因缺少实现退出 1，实施后 4/4 通过；提交守卫同样先 RED，实施后 4/4 通过。
- 报告协议测试先因模块未实现退出 1，实施后通过；共享认证客户端回归覆盖 401 刷新、配置 API 地址、Blob 字节、403 状态、RFC 5987 文件名和不安全文件名回退。
- Chromium 桌面与 320px 烟测验证侧栏、顶部和移动入口，直接访问/刷新/收起、筛选保留、键盘焦点和无横向溢出。中英文移动入口均验证。
- 题库 HTTP fixture 烟测实际选择文件并分别触发一次直导、一次异步上传及一次 job 创建；非终态禁止再次开始。
- 报告 Chromium 烟测实际接收三份下载文件，核对 Markdown/HTML/CSV 字节、后备文件名和请求 run_id。浏览器 API 使用受控响应；这证明前端协议和交互，不代表部署环境的真实端到端导入或供应商联调。

## 工作流记录

Comet 的产品任务为 8/8 完成。正式 phase 守卫仍因 Runtime step 与 Classic phase 的投影不一致拒绝 build evidence；期间的构建命令均退出 0。未手改状态、未宣称 Guard/Archive 已通过。保留该流程记录，联合 PR 可先供 CI 和人工审查。

## 2026-10-30 后续收尾

原验证记录保留为历史证据。真实本地 API/Redis/Celery/Chrome 联调、最新 main 合并和当前 Comet 守卫的验证见 `2026-10-30-frontend-first-batch-final-verify.md`。
