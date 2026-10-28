# 仪表盘真实数据接入验收

日期：2026-10-27（Asia/Shanghai）
Change：dashboard-real-data；分支：comet/dashboard-real-data
实现提交：f44f8e1；基线：bfa15c6
结论：PASS，4/4 任务完成，无未解决的 CRITICAL / IMPORTANT 问题。

## 范围和契约

- 首页独立于 Mock BusinessPage，展示当前用户评估总数、running/completed 全量过滤计数、最近最多五条评估和费用。
- 评估列表后端按 created_at、id 正序返回。首页在 total > 5 时读取 offset=total-5 的末页再反转；计数不从最近五条推算。
- 费用来自现有 /costs/summary，无日期限制；CostService._spend_rows 仅包含当前账号 Evaluation.spent_usd 和已完成 BenchmarkRun.cost_usd。页面明确实验与 A/B 未纳入汇总，未记录不代表免费。
- 复用认证 HTTP 客户端与管理员角色上下文；普通用户、角色未知和角色失败时不请求 /system/status。管理员显示整体、数据库、Redis、Workers、沙箱的原始健康含义与运行时间。
- 所有首页业务请求均为 GET。分区独立结算，提供加载、空状态、错误重试、手动刷新；组件按会话 marker 重建，cleanup AbortController 阻止迟到响应写入旧快照。

## 完整性、正确性和一致性

4/4 tasks 已勾选。proposal、design 和 frontend/app-shell delta 已对照实现；本次新增的五个验收场景覆盖如下：

- 超过一页：dashboard.test.ts 验证 total=23、offset=18 及 ID 倒序；浏览器验证全量计数、五条任务与真实详情跳转。
- 空数据与失败恢复：单测覆盖空/短历史、失败不伪装空数据及费用格式非法；浏览器验证真实零值、首次创建跳转、费用与任务失败相互隔离和重试。
- 系统状态：浏览器管理员夹具包含 degraded、unavailable、unknown、not_checked，页面显示降级、不可用、未知、未检查并提供监控链接。
- 非管理员与角色不可用：单测与浏览器断言无管理员监控请求；浏览器验证角色失败提示、重试后管理员状态读取。
- 会话与迟到响应：单测验证 abort 不继续读取末页；浏览器先阻塞旧会话请求再切换 marker，释放旧响应后页面仅展示新用户空状态。加载及刷新请求只读。

外壳的登录守卫、通知、导入及其他创建入口未改动；相关原有场景保持原实现，通过既有认证、角色、外壳测试和 diff 检查核对。本次浏览器没有重新演练全部旧通知/导入交互。首页去除虚构 Pass@1、模型基线、失败原因、Mock 状态预览，帮助页说明同步修正。

Comet tweak 预设按约定省略独立 Superpowers Design Doc 和完整 plan，使用 change/design.md 对照；二者缺省不是遗漏。用户在文件数提示后明确选择继续 tweak，采用 full 验证。公开 scale 将嵌套 delta 计为 0，本次已手工读取并核对实际存在的一份 frontend/app-shell delta，未跳过规格验证。

## 命令与结果

以下命令在最终实现上实际运行，退出码均为 0：

- npm --prefix frontend test：265/265，通过，其中仪表盘读取单测 7 项。
- npm --prefix frontend run build：TypeScript 与 Vite 生产构建通过；保留既有的大 chunk 提示。
- npm --prefix frontend run lint：0 errors；BenchmarkDetailPage.tsx:131、145 两条既有 useCallback 依赖警告，本次未改动该文件。
- npm --prefix frontend run format:check：通过。
- comet classic openspec -- validate dashboard-real-data --strict：通过。
- git diff --check：通过。
- node frontend/scripts/verify-dashboard.mjs（需设置外部 PLAYWRIGHT_MODULE、可选 CHROME_PATH）：28 项检查通过，浏览器 pageerror 为 0。

浏览器矩阵：Orbit、Precision、Studio × light/dark × 320、768、1024、1440，共 24 组；每组验证统计、最近任务、费用口径、Mock 清理及页面无横向溢出。另 4 组交互验证覆盖管理员与局部失败、空数据、角色失败恢复和会话切换。窄屏任务表允许独立区域横向滚动。

## 失败、修复与独立审查

- 首次数据测试因 dashboard.ts 尚未实现而失败，补齐真实读取后 7 项通过。
- 浏览器曾因 Ant Design 双字按钮名称中的空格定位失败，调整验收定位后通过；脚本 lint 的 URL/console globals 声明已补齐。
- 独立 reviewer 审查整个 change，发现唯一 IMPORTANT：费用说明误称覆盖实验与 A/B。核对后端 _spend_rows 确认，verify-fail 返回 build，页面、design、delta 同步修正。
- 费用口径浏览器回归先在旧页面失败，再于修正后完整 28 项通过。原 reviewer 对该修复复核，确认 Important 已解决，没有其他待修复项。
- 审查明确不判断真实后端认证与基础设施可用性；本轮浏览器使用 HTTP fixtures。

## 证据和复现

- [浏览器摘要](assets/dashboard-real-data/browser-summary.json)
- [管理员视图截图](assets/dashboard-real-data/admin-health.png)
- 自动化脚本：frontend/scripts/verify-dashboard.mjs；设置 DASHBOARD_BASE_URL 指向已启动 Vite（默认 http://127.0.0.1:5192），DASHBOARD_QA_DIR 可覆盖产物目录；PLAYWRIGHT_MODULE 指向环境已有 Playwright，CHROME_PATH 可选择 Chrome 可执行文件。

验证层级为真实 React 页面、认证客户端与后端契约核对、HTTP 夹具。未运行真实后端/数据库/Redis/worker/模型供应商联调，未产生模型调用或业务任务；也未覆盖物理移动设备、Safari/Firefox 或屏幕阅读器。分页并发增删不是原子快照，页面标注读取时间并提供刷新。

## 工作区与交付状态

实现、测试、规格与验收证据已提交至绑定分支；此报告及 Comet 验证状态属于当前 change。用户于 2026-10-27 在最终单选中明确选择 C（回复 3）：确认归档、推送当前绑定分支并创建 PR；主 spec 在归档时同步。
