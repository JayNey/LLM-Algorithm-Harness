# Issue #230：认证与完整离线集成验收

日期：2026-10-27。Change：`evaluation-auth-integration`。分支：`codex/issue-230-evaluation-auth-integration`。

## 基线与范围

开始前已 `git fetch origin`；本地 main 与 origin/main 一致，基线为 `f507b568caf21abd7e325a88a7851afce5a37a03`（PR #282，前置 #229 已关闭）。本次复用 main 已接通的接口、共享客户端、Cookie/CSRF 中间件、SQLite、队列 drain 和 worker task body，不引入 schema、API 或独立认证客户端。

实现与回归共涉及 5 个源码/测试文件：`tests/integration/test_api_workflows.py`、`frontend/scripts/verify-evaluations.mjs`、`frontend/scripts/verify-shell.mjs`、`frontend/src/auth/http.ts`、`frontend/src/store/auth.ts`。Issue 提及的 `tests/test_api_evaluation_options.py`、`tests/test_evaluation_workflow_contract.py` 保留既有断言，并与本次 HTTP 测试一起执行。

2026-10-27 用户已明确选择继续 tweak，接受 JSON、截图及工作流产物超过文件提示阈值。没有扩大产品需求。

## 行为与 RED / GREEN

- Cookie 登录通过真实响应收集 CSRF，未使用 Authorization。覆盖 create → start → pending → worker running → results completed，区分 evaluation ID、AsyncTask ID、可为空的 public run_id 与 worker checkpoint key。
- 排队和运行中取消后仍为 cancelled，旧队列消息或后续 worker 回写不能变成 completed；排队取消不会调用模型。
- Cookie 变更请求缺少 header、错误 header 或缺少 CSRF cookie 均返回 403，创建/启动/取消不会产生副作用。身份 GET 可重新引导 CSRF，合法 refresh 轮换后可取消、注销；缺少 access cookie 可通过真实 refresh 恢复，注销后重放旧 cookie 的访问与刷新均为 401。
- 第二个真实 Cookie 用户的列表不包含第一个用户的任务；其 evaluation/task/results 及 start/cancel 均为 404。普通身份访问管理资源为 403。
- 浏览器使用真实共享 Axios 客户端，两次并发 401 只刷新一次，各重试一次；refresh 使用旧 CSRF，后续写请求使用轮换后的 CSRF。刷新失败不重放业务请求，清除两种存储并跳回登录，保留规范化的来源 URL；403 不刷新、不清除会话。
- 新增迟到 identity 200 场景实际复现源码缺陷：旧响应覆盖新 marker、用户名和 CSRF。修复为在 HTTP 接收 CSRF、处理 401、重试前检查请求所属 marker；登录身份回写及失败清理同样检查 marker。200 和 401 场景均要求新内存/存储会话保持完全一致，旧 401 不触发 refresh。
- 独立进程仅在内存中把 `csrf_matches` 替换为始终 True，新增 wrong-CSRF 测试由 403 变成 201 而失败（退出码 1）。未改动生产文件；恢复正常进程后相关测试全部通过。
- Shell 按请求发起页面区分 Mock 仪表盘/帮助与真实创建页：前者业务零请求，后者允许明确列出的只读选项请求；未知请求为零。

RED 原始证据：[identity 检查 JSON](assets/issue230/red/security.json)、[identity 失败输出](assets/issue230/logs/red.txt)、[CSRF mutation 失败输出](assets/issue230/logs/red-csrf.txt)。CSRF mutation 是断言敏感性检验，不是生产中间件缺陷。

## 已执行验证

以下命令从仓库根执行；前端命令在 `frontend/` 执行。Python 聚焦运行显式使用 `-o addopts=`，未套用全仓库 90% coverage 门槛，也不声称全 Python 套件已运行。

- `python3 -m pytest tests/integration/test_api_workflows.py tests/test_api_evaluation_options.py tests/test_evaluation_workflow_contract.py tests/test_api_auth.py -o addopts= -q`：199 passed，退出码 0；[输出](assets/issue230/logs/http-full.txt)。
- `npm test`：257 passed，退出码 0；[输出](assets/issue230/logs/frontend-tests.txt)。
- `npm run build`：类型检查及生产构建通过，退出码 0；[输出](assets/issue230/logs/build.txt)。
- `npm run lint`：0 errors、2 个既有 BenchmarkDetailPage hook dependency warnings，退出码 0；本次 4 个前端文件的定向 ESLint 无 warning；[输出](assets/issue230/logs/lint.txt)。
- `npx prettier --check scripts/verify-evaluations.mjs scripts/verify-shell.mjs src/auth/http.ts src/store/auth.ts`：通过，退出码 0；[输出](assets/issue230/logs/format.txt)。
- `python3 -m black --check tests/integration/test_api_workflows.py`、`python3 -m ruff check tests/integration/test_api_workflows.py`、`git diff --check`：通过。
- `python3 -m pip wheel . --no-deps --no-build-isolation --wheel-dir /private/tmp/issue230-wheel`：wheel 构建通过，退出码 0；[输出](assets/issue230/logs/wheel.txt)。
- `node scripts/verify-evaluations.mjs --scenario all`：149 项主流程断言通过；其子进程完整 appearance 矩阵 216 项断言通过（3 风格 × 2 主题 × 4 宽度及状态/键盘检查）。未知 API 请求与未处理页面异常均为空；[all JSON](assets/issue230/all/all.json)、[appearance JSON](assets/issue230/all/appearance/appearance.json)。
- `node scripts/verify-shell.mjs`：51 项检查通过，未知请求与主应用页面异常均为空；[shell JSON](assets/issue230/shell/checks.json)。异常边界 fixture 的指定故意异常被捕获并恢复，不作为主页面未处理异常。
- 独立 `node scripts/verify-evaluations.mjs --scenario security`：8 项检查通过，退出码 0；[security JSON](assets/issue230/security/security.json)、[输出](assets/issue230/logs/security.txt)。

已知工具输出：5 类既有 Pydantic 配置弃用警告、前述 2 个 ESLint warnings、Vite 大 chunk 提示；均不影响命令成功。最初 fixture 运行曾因错误 WebSocket 环境路径失败，改用下述文档路径后 all 通过。生产文件热更新会导致既有隔离 HTML fixture 导入不同 HMR module 实例；本次最终运行使用重新启动的 Vite。

## 可复现浏览器命令

Node `v26.8.1`，Python `3.11.16`。本次使用本机 Google Chrome 的 Chromium 自动化，未验证 Safari、Firefox 或真机。Playwright 包由执行环境提供，不添加项目依赖。

先在 `frontend/` 启动一个全新的 Vite 服务：

```sh
VITE_API_BASE_URL=/api/v1 \
VITE_WS_URL=ws://127.0.0.1:5180/api/v1/ws/progress \
VITE_APP_NAME=Harness \
npm run dev -- --host 127.0.0.1 --port 5180
```

另一个终端在 `frontend/` 执行，先设置 `PLAYWRIGHT_MODULE` 为可用包路径；若需系统 Chrome，设置 `CHROME_PATH` 为其可执行文件路径：

```sh
EVALUATION_QA_DIR=../docs/superpowers/reports/assets/issue230/all \
node scripts/verify-evaluations.mjs --scenario all

EVALUATION_QA_DIR=../docs/superpowers/reports/assets/issue230/security \
node scripts/verify-evaluations.mjs --scenario security

SHELL_QA_DIR=../docs/superpowers/reports/assets/issue230/shell \
node scripts/verify-shell.mjs
```

## 验证层级与限制

- **离线 HTTP**：真实 FastAPI ASGI 路由、认证、HttpOnly Cookie 发放、CSRF 中间件、SQLite、评估与 AsyncTask 服务、策略、checkpoint 与结果报告。模型生成、Docker 沙箱执行、Celery 发送/状态查询/revoke 传输、Redis progress publish 被替换；真实 worker `.run()` 由已有 drain 在进程内调用。
- **浏览器 fixture**：真实 React、StrictMode、路由、认证存储、共享 HTTP 客户端、评估页面与状态；HTTP 响应及 WebSocket 帧由 Playwright route 替换。隔离 lifecycle 场景另外替换其 store HTTP 依赖。浏览器未连接真实后端，不能证明 browser ↔ FastAPI Cookie、SameSite/Secure/CORS 或 Set-Cookie 竞态。
- **未验证**：真实 Redis/Celery 网络及远端 revoke、供应商调用、Docker 沙箱执行、上游 WebSocket、Safari/Firefox 与真机。本次通过只覆盖 #230 的离线验收；整体质量、真实联调和交付汇总分别由 #231/#232/#233 跟踪。

## 集成审查与结论

按 requesting-code-review 技能完成一次独立只读集成审查，覆盖基线到全部源代码/测试改动：无 CRITICAL / IMPORTANT。审查确认 HTTP 响应归属检查先于 CSRF 接收及 401 恢复，store 检查覆盖迟到成功和失败；Cookie 测试保留真实中间件、数据库及 worker。

审查提出最终回跳截图需要等待 lazy 登录表单就绪，已增加登录标题与用户名输入框可见检查。审查不认证真实 browser/backend Cookie 传输、真实外部服务，也不扩展到既有的其他并发 login/logout 竞态。

最终结论：本地实现与离线验收 PASS。最终 all 证据对应源码提交 `45d910fa92dd737ee562973fd24342d02ea50db4`；security 8 项通过，回跳截图已人工确认显示完整登录表单。命令退出码与文件 SHA-256 清单见 [commands.json](assets/issue230/commands.json)。归档、推送和 PR 按 Comet 归档前最终确认执行；PR 目标为 main，验收清单与本报告关联 Issue #230。


完整性：build 任务 3/3 完成；所有要求均有对应测试或交付材料。正确性：上述命令均成功，实际 identity RED 修复后通过，CSRF mutation 能触发失败。设计一致性：复用现有离线 fixture，不引入新服务；无 delta spec，因此 skip_specs: true；tweak 预设不要求独立 Superpowers Design Doc/plan。独立集成审查通过，无需接受正确性或安全偏差。

归档前工作区归因：全部源码已提交，剩余报告、截图/JSON、Comet 状态与交付草稿均属于本 change；未混入用户修改。远端推送、PR 和 Issue 更新尚未执行，不能将本地 PASS 视为 Issue 已交付。

## Comet 完整验证

规模评估选择 full（91 个变更文件主要为证据和流程产物），已按 openspec-verify-change 对照完整产物验证：3/3 build 任务完成，proposal 目标与 design 决策一致；无 delta spec，因现有行为回归使用 skip_specs，未产生规格漂移。tweak 预设明确跳过独立 Superpowers Design Doc/plan，该项不适用。

源码集成审查及截图定点复审均通过，无 CRITICAL / IMPORTANT。`comet classic openspec -- validate evaluation-auth-integration --strict` 通过；全部浏览器 JSON、零未知请求/页面异常与证据 SHA-256 逐项校验通过。verify 阶段独立重跑 `npm run build` 成功（退出码 0），已记录 verify check，与 build 阶段证据分开保存。验证结论 PASS，分支状态保持 pending，等待归档前最终确认。
