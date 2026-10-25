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

## 实验管理页验证（issue #166 第①步）

```bash
npm run dev -- --host 127.0.0.1 --port 5180
# 另开终端：
PLAYWRIGHT_MODULE=/absolute/path/to/node_modules/playwright \
  node scripts/verify-experiments.mjs all
```

场景：`create`（创建→详情导航）、`list`（列表渲染与筛选）、`detail`（详情配置摘要与启动入口）、`all`。
浏览器 fixture 层验证（不连真实后端）；报告与截图写入
`docs/superpowers/reports/assets/experiments/fixture/`。

## 基准与 A/B 测试页验证（issue #166 第②步）

```bash
npm run dev -- --host 127.0.0.1 --port 5180
PLAYWRIGHT_MODULE=/absolute/path/to/node_modules/playwright \
  node scripts/verify-benchmarks.mjs all
```

场景：`suites`（套件列表）、`curve`（学习曲线趋势）、`abtests`（AB 列表）、`all`。
报告与截图写入 `docs/superpowers/reports/assets/benchmarks/fixture/`。

## 题目管理页验证（issue #163）

```bash
npm run dev -- --host 127.0.0.1 --port 5180
PLAYWRIGHT_MODULE=/absolute/path/to/node_modules/playwright \
  node scripts/verify-problems.mjs all
```

场景：`list`（列表与来源筛选）、`import`（同步导入报告）、`history`（评估历史抽屉）。
报告与截图写入 `docs/superpowers/reports/assets/problems/fixture/`。

## 评估详情实时进度与权限清理（#225 补验收）

2026-10-24 实际运行 `node scripts/verify-evaluations.mjs --scenario all`：90 组断言通过，覆盖 create/security/list/detail/progress。[公开 JSON](assets/evaluations/progress-verification/all.json) 保留干净源码头、请求记录、替换依赖、截图索引及进度时序。先等待初始 snapshot 对账结束，再投递 50% WS 事件，验证新 HTTP 请求返回的 60% 成为页面真值；同时覆盖 HTTP403 和 WS4403 后隐藏旧详情/动作。

运行方式与 shell fixture 相同；变量使用 `EVALUATION_BASE_URL`、`EVALUATION_QA_DIR`，支持 `--scenario progress` 或 `detail/create/list/all`。先启动 Vite，再在 frontend 运行：

```sh
PLAYWRIGHT_MODULE=/absolute/path/to/node_modules/playwright \
EVALUATION_BASE_URL=http://127.0.0.1:5180 \
node scripts/verify-evaluations.mjs --scenario all
```

这是 Chromium HTTP/WS fixture，真实 React/路由/会话适配器/观察器/客户端参与，身份、HTTP、WS 均被替换；没有连接真实 Redis/Celery、供应商或沙箱。详情 3 风格×2 主题×320/1440px 的截图保留，人工抽查 progress 桌面、Orbit 深色手机及 Studio 浅色桌面；不外推为真机或全流程外观验收。工程结果与独立审查详见 [补验收报告](../superpowers/reports/2026-10-24-evaluation-progress-verification-verify.md)。

## 设置与系统管理页验证（issue #167）

```bash
npm run dev -- --host 127.0.0.1 --port 5180
PLAYWRIGHT_MODULE=/absolute/path/to/node_modules/playwright \
  node scripts/verify-settings.mjs all
```

场景：`monitor`（系统监控面板）、`budgets`（预算与预警）、`pricing`（定价目录）、`logs`（日志查询）。
报告与截图写入 `docs/superpowers/reports/assets/settings/fixture/`。

## 真实评估结果列表与详情（#226）

结果列表使用 `client.results`，详情通过 evaluation ID 使用 `client.get` 与 `client.result` 联合读取，run_id=null不阻止访问。策略汇总来自服务端全量统计，单题独立分页；活动详情复用同一个ProgressObserver，不另起结果轮询。结果普通失败与任务失败分别展示，401/429交给既有会话恢复/限流处理。

从frontend启动Vite，另终端运行 `PLAYWRIGHT_MODULE=/absolute/path/to/playwright node scripts/verify-evaluations.mjs --scenario results`；地址/输出用 `EVALUATION_BASE_URL`、`EVALUATION_QA_DIR` 覆盖。外部Playwright包由环境提供，不增加项目依赖。`all`也会运行results及既有创建、列表、详情、进度、安全回归。

[验证报告](../superpowers/reports/2026-10-25-evaluation-results-verify.md) 与 [公开浏览器JSON](assets/evaluations/results/all.json) 记录实际源码、断言、请求时序和截图索引。fixture替换HTTP/WS/测试身份，不能代替真实Redis/Celery、供应商、沙箱或真实账号端到端；完整外观矩阵及真实联调由#229/#232跟踪。
