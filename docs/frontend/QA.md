# 工作台外壳验证说明

记录日期：2026-10-20。本文件区分脚本的检查范围与已得到的验证证据，避免把待跑项目写成通过。

## 当前证据

已完成的浏览器根页面尺寸检查：Orbit / Precision / Studio × light / dark × 320 / 390 / 768 / 1024 / 1280 / 1440px，共 36 种组合，根页面未出现横向溢出。这只支持相应页面与视口下的溢出结论，不表示所有浮层、子路由、交互、浏览器或设备均已验收。

最终执行 `scripts/verify-shell.mjs` 成功退出：47项浏览器检查通过，其中36项为布局组合。覆盖系统主题、偏好恢复、路由/输入节点/筛选/草稿/通知状态保持、加载/空/错误重试、通知分类与清空、手机导航与Esc焦点恢复、四类可关闭反馈、真实登出客户端、会话隔离、管理员入口及渲染异常边界恢复。主应用页面没有运行异常，也没有请求业务API。身份与登出响应使用浏览器fixture，不表示真实后端端到端已验收。结果见 `../superpowers/reports/assets/issue168/checks.json`。

工程检查：121项前端测试通过；ESLint、Prettier、类型检查和生产构建通过。独立代码审查确认认证按钮对比度回归已修复；独立视觉复验确认字标、手机Mock提示、六套占位文字对比度修正已解决。

## 自动化脚本

脚本位于 `frontend/scripts/verify-shell.mjs`，从 `frontend/` 执行。它使用外部可用的 Playwright 包；仓库未因此增加 Playwright 依赖。先启动开发服务，默认地址为 `http://127.0.0.1:5180`：

```sh
cd frontend
npm run dev -- --host 127.0.0.1 --port 5180
```

另一终端在 `frontend/` 中运行，`PLAYWRIGHT_MODULE` 指向可解析的外部 Playwright 模块或绝对包路径：

```sh
PLAYWRIGHT_MODULE=/absolute/path/to/node_modules/playwright node scripts/verify-shell.mjs
```

若环境已能解析 `playwright`，可省略 `PLAYWRIGHT_MODULE`。`CHROME_PATH` 可选，提供本机 Chrome 可执行文件路径；省略时使用 Playwright 自带的 Chromium。`SHELL_BASE_URL` 可覆盖服务地址，`SHELL_QA_DIR` 可覆盖截图与报告输出目录；默认产物目录为 `docs/superpowers/reports/assets/issue168/`（从仓库根看）。不要将其他开发者机器上的绝对路径写成项目要求。

脚本拦截身份 API 以提供确定的浏览器测试身份，并检查业务 Mock 没有意外请求后端；这些 fixture 只属于验证脚本，不是应用中的角色切换功能。脚本覆盖范围由当前源文件定义，结果以成功退出及实际产物为准；运行失败或只生成了部分截图不能当作通过。

## 工程检查与人工限制

在 `frontend/` 运行 `npm test`、`npm run lint`、`npm run build`；各命令是否通过须查看当次输出。单元测试、构建与浏览器验证各自证明不同范围，不互相替代。

尚不能由本轮证据确认的范围包括真实 iOS/Android 设备、Safari/Firefox 浏览器、屏幕阅读器、真实触摸与软键盘、真实后端登录/刷新/权限与登出全链路、跨设备通知、网络断线和实时消息。视口模拟与身份 fixture 不能替代这些验收。

## 后续真实评估列表（#223）

2026-10-22 的真实列表接入与独立验证见 [#223 验证报告](../superpowers/reports/2026-10-22-owned-evaluation-list-verify.md)。列表页面使用实际认证客户端；对应浏览器测试替换身份和列表响应，因此它证明前端行为，尚未证明真实后端端到端。公开 [fixture 结果](assets/evaluations/list/list.json) 包含 22 组断言及 390/1440px 截图索引。此前外壳证据仍只适用于其记录版本；全局入口/Mock 标记后续由 #228 处理，完整外观矩阵由 #229 处理。

## 页面浏览器验收（#400）

以下七个脚本统一使用 Vite dev。先从仓库根启动开发服务。

```sh
cd frontend
npm run dev -- --host 127.0.0.1 --port 5180 --strictPort
```

另开终端，从仓库根执行。先将 `PLAYWRIGHT_MODULE` 设为本机可用的 Playwright 包路径，按需设置 `CHROME_PATH`。

```sh
cd frontend
export PLAYWRIGHT_MODULE=/absolute/path/to/node_modules/playwright
DASHBOARD_BASE_URL=http://127.0.0.1:5180 node scripts/verify-dashboard.mjs
node scripts/verify-experiments.mjs all
node scripts/verify-experiment-queue.mjs
node scripts/verify-benchmarks.mjs all
BENCHMARK_BASE_URL=http://127.0.0.1:5180 node scripts/verify-benchmark-history.mjs
node scripts/verify-problems.mjs all
node scripts/verify-settings.mjs all
```

脚本用 fixture 拦截身份、持久化通知读取和各场景声明的业务 API，未声明的 API 请求会导致失败。逐条检查退出码。仪表盘默认把报告和截图写到 `/tmp/dashboard-qa`，实验、基准、题库和设置页写到 `docs/superpowers/reports/assets/<页面>/fixture/`。运行时可用 `DASHBOARD_QA_DIR`、`EXPERIMENT_QA_DIR`、`BENCHMARK_QA_DIR`、`PROBLEM_QA_DIR` 和 `SETTINGS_QA_DIR` 覆盖。实验队列和基准历史在终端输出结果。

生产构建的静态样式与直接加载由下文 `verify-direct-load.mjs` 使用 Vite preview 单独验收。

实验页支持单跑 `create`（创建与详情导航）、`list`（列表与筛选）、`detail`（详情与启动入口）。基准与 A/B 页支持 `suites`（套件列表）、`curve`（学习曲线）、`abtests`（A/B 列表与详情）。

### 题目管理（#163、#399）

支持单跑 `list`（列表与来源筛选）、`import`（同步导入报告）、`history`（评估历史抽屉）。

个人题库文件导入的验收范围为 JSON（`.json`）和 CSV（`.csv`）。表单应提示这两种格式。用两种格式分别核对 5 MiB 以内（含）的同步校验报告和超过 5 MiB 的异步作业进度。选择 `.yaml` 或 `.yml` 后提交时，页面应提示支持的格式，且不发送上传或导入请求。直接调用同步导入，或用通用上传得到的 YAML 文件 ID 请求异步导入时，服务端也应拒绝。服务端入口见 [文件服务指南](../api-files.md)。

### 设置与系统管理（#167）

支持单跑 `monitor`（系统监控面板）、`budgets`（预算与预警）、`pricing`（定价目录）、`logs`（日志查询）。

## 评估详情实时进度与权限清理（#225 补验收）

2026-10-24 实际运行 `node scripts/verify-evaluations.mjs --scenario all`：90 组断言通过，覆盖 create/security/list/detail/progress。[公开 JSON](assets/evaluations/progress-verification/all.json) 保留干净源码头、请求记录、替换依赖、截图索引及进度时序。先等待初始 snapshot 对账结束，再投递 50% WS 事件，验证新 HTTP 请求返回的 60% 成为页面真值；同时覆盖 HTTP403 和 WS4403 后隐藏旧详情/动作。

运行方式与 shell fixture 相同；变量使用 `EVALUATION_BASE_URL`、`EVALUATION_QA_DIR`，支持 `--scenario progress` 或 `detail/create/list/all`。先启动 Vite，再在 frontend 运行：

```sh
PLAYWRIGHT_MODULE=/absolute/path/to/node_modules/playwright \
EVALUATION_BASE_URL=http://127.0.0.1:5180 \
node scripts/verify-evaluations.mjs --scenario all
```

这是 Chromium HTTP/WS fixture，真实 React/路由/会话适配器/观察器/客户端参与，身份、HTTP、WS 均被替换；没有连接真实 Redis/Celery、供应商或沙箱。详情 3 风格×2 主题×320/1440px 的截图保留，人工抽查 progress 桌面、Orbit 深色手机及 Studio 浅色桌面；不外推为真机或全流程外观验收。工程结果与独立审查详见 [补验收报告](../superpowers/reports/2026-10-24-evaluation-progress-verification-verify.md)。

## 真实评估结果列表与详情（#226）

结果列表使用 `client.results`，详情通过 evaluation ID 使用 `client.get` 与 `client.result` 联合读取，run_id=null不阻止访问。策略汇总来自服务端全量统计，单题独立分页；活动详情复用同一个ProgressObserver，不另起结果轮询。结果普通失败与任务失败分别展示，401/429交给既有会话恢复/限流处理。

从frontend启动Vite，另终端运行 `PLAYWRIGHT_MODULE=/absolute/path/to/playwright node scripts/verify-evaluations.mjs --scenario results`；地址/输出用 `EVALUATION_BASE_URL`、`EVALUATION_QA_DIR` 覆盖。外部Playwright包由环境提供，不增加项目依赖。`all`也会运行results及既有创建、列表、详情、进度、安全回归。

[验证报告](../superpowers/reports/2026-10-25-evaluation-results-verify.md) 与 [公开浏览器JSON](assets/evaluations/results/all.json) 记录实际源码、断言、请求时序和截图索引。fixture替换HTTP/WS/测试身份，不能代替真实Redis/Celery、供应商、沙箱或真实账号端到端；完整外观矩阵及真实联调由#229/#232跟踪。

## 真实评估外观矩阵（#229）

前置 #228 已通过 PR #278 合并。本轮在 PR #282 合并 `main`@`b8ff9fd` 后验收统一外壳及评估页面。先在 `frontend/` 启动 Vite，再运行：

```bash
PLAYWRIGHT_MODULE=/absolute/path/to/playwright \
EVALUATION_BASE_URL=http://127.0.0.1:5180 \
node scripts/verify-evaluations.mjs --scenario appearance
```

`PLAYWRIGHT_MODULE`、可选 `CHROME_PATH` 的含义与其他浏览器场景一致。`EVALUATION_QA_DIR` 可覆盖输出目录，默认保存到 `docs/frontend/assets/evaluations/appearance/`；统一 `all` 场景也执行完整外观矩阵：设置 `EVALUATION_QA_DIR` 时，矩阵报告放在其输出目录的 `appearance/` 子目录；未设置时仍保存到上述公开 assets 目录。`EVALUATION_APPEARANCE_QA_DIR` 的优先级最高，可单独覆盖矩阵输出路径。保留独立命令 `node scripts/verify-evaluation-appearance.mjs`，它可自动启动和清理自己的 Vite，也支持 `EVALUATION_APPEARANCE_BASE_URL` 指向已有服务。

矩阵覆盖 Orbit、Precision、Studio × light、dark × 320、390、768、1440px，共 24 种组合。每种组合检查创建、任务列表/详情、结果列表/详情：

- 创建页：两页题目选择、密钥/模型/策略/预算切换后保留，提交 payload 精确匹配两页选择及受支持字段，创建和启动各请求一次。
- 列表：可见筛选值和完整 URL 保留，外观切换不触发额外列表请求。
- 五类页面：主要按钮及表格滚动区域可由 Tab 到达，页面无横向溢出；表格容器允许自身滚动。
- 全部宽度：通知抽屉可通过键盘打开、Esc 关闭，焦点返回触发按钮。320/390/768px 另验证移动抽屉的 Esc/焦点和真实创建入口；仅 320/390px 显示的底部导航另验键盘进入结果页，不将隐藏的平板底栏记作通过。

### #229 验收证据与截图索引

本轮完整矩阵 216 组检查通过（24 组合，0 失败、0 未声明 API）；统一 `all` 的 143 组主场景检查及前端 257 项单元测试通过。

[公开矩阵 JSON](assets/evaluations/appearance/appearance.json) 记录实际源码提交、工作区状态、精确页面与组合、请求/提交 payload、检查结果和限制；[本轮验证报告](../superpowers/reports/2026-10-27-evaluation-appearance-verify.md) 记录命令、退出码和最终审查。

代表性截图均由同一矩阵运行生成，并人工查看：

- [创建页 · Orbit / light / 320px](assets/evaluations/appearance/create-orbit-light-320.png)
- [任务列表 · Precision / dark / 390px](assets/evaluations/appearance/task-list-precision-dark-390.png)
- [任务详情 · Studio / light / 768px](assets/evaluations/appearance/task-detail-studio-light-768.png)
- [结果详情 · Studio / dark / 1440px](assets/evaluations/appearance/result-detail-studio-dark-1440.png)

验证层级为 Chromium 的桌面浏览器视口模拟，真实 React 页面、路由、状态和 HTTP 客户端参与执行；身份及业务 HTTP 响应由 fixture 替换，通知使用外壳本地示例数据。未执行真实账号/Cookie/CSRF、用户隔离、离线 HTTP 服务端、Redis/Celery、供应商、沙箱、真机、Safari/Firefox 或屏幕阅读器验证。fixture 返回完成状态仅供前端显示与交互检查，不证明真实评估执行成功；真实联调由 #232 跟踪。

## 直接加载视觉 smoke（共享工作流样式）

`src/evaluations/workflow.css` 由共享布局 `AppLayout` 导入，随应用入口 CSS 下发；页面组件不再各自导入。`scripts/verify-direct-load.mjs` 针对**生产构建**直接打开工作流路由（不走站内导航），确认共享样式在首屏可用。

先构建，再在 `frontend/` 运行：

```bash
npm run build
PLAYWRIGHT_MODULE=/absolute/path/to/playwright \
CHROME_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
node scripts/verify-direct-load.mjs
```

未设置 `DIRECT_LOAD_BASE_URL` 时脚本会自动启动并清理 `vite preview`（默认 `http://127.0.0.1:5191`）；设置为已有服务地址时复用该服务。`DIRECT_LOAD_QA_DIR` 覆盖截图与报告目录，默认 `docs/frontend/assets/direct-load/`。`PLAYWRIGHT_MODULE`、`CHROME_PATH` 与其它浏览器脚本一致，不新增项目依赖；缺少 `dist/index.html` 时脚本会提示先执行 `npm run build`。

脚本断言分三层：

- 静态层：入口 CSS 文件包含 `.evaluation-list-table` 与 `.evaluation-panel` 规则；`src/pages/**` 不再出现 `workflow.css` 导入。
- 计算样式层：在 `/experiments`、`/experiments/new`、`/experiments/:id`、`/ab-tests`、`/ab-tests/new`、`/benchmarks/:suiteId` 直接加载后，表格 `border-collapse: collapse`、`min-width: 760px`、单元格内边距 16px/12px，面板内边距 24px（390px 下 16px），`.evaluation-workflow` 为 `min-width: 0`。
- 布局层：1440px 与 390px 下页面无横向溢出、无 `pageerror`、无未声明或失败请求。

结果写入 `docs/frontend/assets/direct-load/report.json`，每个路由各保留一张截图（`/experiments` 与 `/experiments/new` 另含 390px 版本）。身份与业务响应全部由 fixture 替换，因此该 smoke 证明直接加载的样式与布局，不证明真实后端或生产部署。

## 关键页面窄屏、键盘与焦点验收（#446）

`scripts/verify-responsive-keyboard.mjs` 针对**生产构建**（`npm run build` + `vite preview`）覆盖题库、设置（预算）、监控（系统状态）、基准历史四类页面。先构建，再在 `frontend/` 运行：

```bash
npm run build
node scripts/verify-responsive-keyboard.mjs all
```

未设置 `RESPONSIVE_BASE_URL` 时脚本使用 `http://127.0.0.1:5194`，需自行启动 `node node_modules/vite/bin/vite.js preview --host 127.0.0.1 --port 5194 --strictPort`；设置后复用已有服务。`RESPONSIVE_QA_DIR` 覆盖截图与报告目录，默认 `docs/frontend/assets/v06/`。场景可选 `responsive` / `keyboard` / `forms` / `all`。

三层场景共 78 项断言（2026-11-09，HEAD 记录于 `assets/v06/all.json`，0 失败、0 未声明请求）：

- 视口矩阵：320 / 390 / 768 / 1024 / 1440px × 四页面，断言无整页横向滚动；所有可见 `.evaluation-list-table` 有滚动容器且容器可滚到表格末尾；关键操作（题库「评估历史」、预算「编辑」、系统「立即刷新」、运行历史「下一页」）可达。390px 档以英文 + 深色运行，覆盖中英文与外观组合。
- 键盘与焦点：skip-link 是首个可见停靠点，聚焦即入视口且 Enter 进入主内容；通知抽屉 Esc 关闭后焦点回到触发按钮；分页按钮可 Tab 到达且 Enter 翻页（第二页内容可见）；320px 下表格行操作可达、Esc 关闭历史抽屉。
- 表单可访问性：登录/注册在 320 与 1440px × 中英文下可访问名称齐全；空提交显示字段错误且控件带 `aria-invalid`；应用内切换语言与深浅主题后已填内容保留、焦点可继续输入。

配套源码修复：`.evaluation-list-table{min-width:760px}` 的 12 处表格（实验详情 6、A/B 详情 2、题库 2、A/B 列表与基准列表各 1）包进 `.evaluation-list-scroll`，RunHistory 的内联 overflow 改为同一容器并补 `运行记录` 标签，与设置表格既有模式一致（#453）。

截图：320px 与 1440px 全页面 + 390px 英文深色（四页面各一）+ 注册深色 320px，共 13 张，见 `docs/frontend/assets/v06/`。

未执行范围：真实 iOS/Android 设备、Safari/Firefox、屏幕阅读器、真实触摸与软键盘、真实后端链路。视口模拟（Chromium）与 fixture 身份/业务响应不能替代这些验收。
