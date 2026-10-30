# PR #313 最终集成验证

日期：2026-10-30。对应 F1 #298、F4 #299、F8 #301。主 change 为 `global-problem-import`，联合交付 `evaluation-report-downloads` 和 `budget-import-guidance`。

## 本轮补齐

- 在原分支 `tweak/20261028/global-problem-import` 合入最新 `origin/main`（`22e7233a6b31e6e75301bd1a524f6276515856eb`），保留两份翻译资源的双方新增键，消除合并冲突。合并提交：`48662a1`。
- main 新帮助页仍将全局导入和报告下载描述为未实现，已按本 PR 实际行为同步修正中英文。没有修改任务恢复或通知投递能力。
- 新增可复跑的 `scripts/verify_frontend_first_batch.py` 与 `frontend/scripts/verify-first-batch-live.mjs`，补齐原先只有 HTTP fixture 的集成证据。
- 当前检出缺少原本的 change 状态，使用公开 `comet state init` 恢复三个 tweak change 的分支绑定。通过实际运行构建并使用 `record-check` 记录证据，处理根目录没有可自动推断的 frontend 构建命令这一问题；没有手改 phase、运行时 step 或伪造验证结果。

## 实际检查与结果

- `npm --prefix frontend test`：退出 0；297/297 通过，无 skip。
- `npm --prefix frontend run lint`：退出 0；0 error，保留 BenchmarkDetailPage 两条既有 hook 依赖 warning。
- `npm --prefix frontend run build`：退出 0，包含 `tsc -b`；保留既有大 chunk 提示。
- `python3 -m pytest tests/test_api_files.py tests/test_api_evaluation_results.py tests/test_import_task.py --no-cov -q`：退出 0；86/86 通过。此为定向测试，不代表本轮执行了全后端测试或全仓覆盖率门槛。首次使用默认 coverage 配置时用例全通过，但因定向运行低于全仓覆盖率门槛返回失败，故改用明确的定向无覆盖率命令。
- `python3 -m ruff check scripts/verify_frontend_first_batch.py` 及 `ruff format --check`：退出 0。
- 新脚本及 Help/i18n 文件 Prettier 检查：退出 0。
- 三个 change 分别 `comet classic openspec -- validate <name> --strict`：退出 0。
- 最终 `git diff --check`：退出 0。
- 独立集成审查：核对原 PR、两份新增 QA 脚本、Help 与翻译合并，未发现明确的正确性、安全或核心验收阻塞。

## 真实本地联调

执行：

```sh
FIRST_BATCH_BROWSER_CHANNEL=chrome PLAYWRIGHT_MODULE=/path/to/playwright \
  python3 scripts/verify_frontend_first_batch.py
```

Python 使用项目 Python 依赖；frontend 需已安装 npm 依赖；PATH 需包含 Redis 和 Node。Playwright 默认使用安装的 Chromium，也可通过上述 channel 使用本机 Chrome。此脚本仅启动监听 127.0.0.1 的独立临时服务，自动选择端口、生成一次性凭据并隔离 auth/business SQLite、uploads、tasks 和 Redis broker/backend；结束后关闭浏览器和服务。失败时临时目录保留诊断日志，报告有显式 `passed` 标志。

[机器可读浏览器证据](assets/pr313-live/report.json) 的 `passed` 为 true，page errors 为空。所有 HTTP 请求来自真实 API，没有 `page.route`/HTTP 响应替身。

- F1：真实 Cookie 登录；桌面侧栏和顶部快速入口；URL 直达/刷新/筛选保留；提交前收起不发请求；快速双击只发一次直导请求；真实文件校验和库存结果。
- F1：大于 5MiB 的文件经过实际上传、Redis 入队、Celery worker 导入及进度轮询，最终 `completed`，新导入 1 条、累计库存 2 条；仅创建一个后台任务。整库替换的取消不提交，确认后真实库存变为 1 条。320px 移动入口可用且无横向溢出。
- F4：完整和失败运行各下载 Markdown、HTML、CSV，共 6 份真实报告；检查格式、运行 ID、文件名、内容及浏览器文件与 API 响应一致。Chromium 对响应正文去除 UTF-8 BOM，比较时仅规范化这一前导标记。主动移除 access cookie 后触发真实刷新并成功下载；另一账号的运行返回 404。
- F8：真实预算页面中英文渠道配置与 Mock 边界说明均呈现；新帮助页和已实现的导入/下载一致。
- 既有自动回归继续覆盖迟到会话响应、文件名安全、权限状态码、缺失 run_id、非终态导入防重及双语资源。

本地报告数据行由脚本预置到隔离数据库，报告正文由真实后端生成；没有调用付费模型，也没有连接生产部署。这里的真实联调结论限于本地服务环境，不声称已验证生产 SMTP/Slack 投递、生产部署或供应商模型链路。

## 生命周期状态

三个 change 的构建与验证证据独立记录，验证报告共用本文。归档前保持 `branch_status: pending`；仅在公开阶段守卫成功后记录通过，不绕过守卫。正式归档、主 spec 同步和远端交付在最终归档决策后执行，本文不提前宣称已归档或已推送。
