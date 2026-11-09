# 前端源码与契约审查覆盖（V07 / issue #447）

- 基线：`review/20261109/frontend-coverage-v07`，HEAD `73e7050a`（2026-11-09 核验，工作树干净）
- 范围：frontend/src 全部 80 个源文件（约 26000 行）、layouts 样式（约 2944 行）、21 个浏览器验收脚本与 fixture、以及被前端消费的对应后端路由/服务契约
- 方法：按五个模块组并行通读（评估域、实验/AB/基准域、题库/预算/定价/监控/设置域、auth/store/i18n/样式横切面、验收脚本与契约），汇总后对全部 P1 与关键 P2 发现逐条人工复核源码；发现状态按「已复核（人工确认）／静态确认（已给出 file:line 证据链但未运行）／待运行验证」三级标注
- 结论索引：已复核缺陷单独登记为 issue（见 §4）；本文不重复展开

## 1. 覆盖矩阵

状态：●=全文已读，◐=部分读（注明段落），○=未读（注明理由）。

### 1.1 评估域（evaluations + pages/Evaluations + pages/Results）

| 文件 | 状态 | 说明 |
|---|---|---|
| evaluations/client.ts、analytics.ts、observer.ts、analysis.tsx、useEvaluation.ts、creation.ts、results.ts、components.tsx、optionFields.tsx、optionCatalog.ts | ● | 全文；严格解析器、观察器纪元/退避/限速、代际守卫逐分支核对 |
| pages/Evaluations/*.tsx（3 个）、pages/Results/*.tsx（2 个） | ● | 全文；越界回页、信号守卫、锚点渲染期同步、forbidden/unauthorized 清理 |
| evaluations/dashboard.ts、reports.ts、charts/CompareCharts.tsx | ○ | 主路径已由前轮独立审查覆盖；dashboard.ts 本批 F01（#423）刚修复 |
| 对照后端：api/routes/{evaluations,evaluation_results,evaluation_options,tasks,ws}.py、api/services/{evaluation_service,evaluation_results_service,evaluation_options_service}.py、src/reporting/capability_profiler.py、src/tasks/evaluation.py | ◐ | 仅契约核对段落 |

### 1.2 实验 / A/B / 基准域

| 文件 | 状态 | 说明 |
|---|---|---|
| experiments/ 全部 8 个源文件（client.ts 780 行全文）、abtests/ 全部 7 个、benchmarks/ 全部 7 个（含 history.ts、SuiteForm.tsx） | ● | 全文；任务进度解析、轮询停止策略、创建流状态机逐分支核对 |
| pages/Experiments/*.tsx（3 个）、pages/ABTests/*.tsx（3 个）、pages/Benchmarks/*.tsx（2 个） | ● | 全文 |
| 对照后端：api/experiment_models.py、api/routes/{experiments,ab_tests,benchmarks,tasks}.py、api/services/{experiment_service,ab_test_service,benchmark_service}.py、src/{task_manager,experiment,ab_testing,cost_optimizer,experiment_report}.py | ◐ | 契约相关段落（进度写入、claim/pause/cancel、报告形状） |

### 1.3 题库 / 预算 / 定价 / 监控 / 日志 / 仪表盘域

| 文件 | 状态 | 说明 |
|---|---|---|
| problems/ 全部 6 个源文件、budgets/ 全部 3 个、pricing/ 全部 3 个、monitoring/ 全部 4 个（client.ts 468 行全文）、systemlogs/ 全部 3 个（含补读 client.ts） | ● | 全文 |
| pages/Problems/ProblemsPage.tsx、pages/Settings/*.tsx（8 个）、pages/Dashboard/DashboardPage.tsx | ● | 全文 |
| 对照后端：api/routes/{files,costs,monitoring}.py、api/cost_models.py、api/files/{store,service,parsing}.py、api/services/{cost_service,cost_alert_service,spend_records}.py、api/monitoring/{probes,service,store,queue_probe,dependencies,capabilities}.py、src/cache.py | ◐ | 契约相关段落 |

### 1.4 auth / store / i18n / 路由 / 样式横切面

| 文件 | 状态 | 说明 |
|---|---|---|
| auth/ 全部 10 个源文件（http.ts 358 行全文）、store/ 全部 3 个（notifications.ts 382 行全文）、i18n/ 全部 4 个（两字典 2900+ 行）、routes.tsx、App.tsx、main.tsx、config/env.ts、hooks/useResource.ts、components/Auth/ 3 个、layouts/ 5 个 tsx | ● | 全文 |
| layouts/shell.css（2579 行）、evaluations/workflow.css（332 行）、index.css | ● | 全文；断点清单见 §3 |
| pages/Auth/LoginPage.tsx、components/common/Feedback.tsx、api/auth/{csrf,cookies,service,store}.py、api/routes/{auth,notifications}.py、api/services/in_app_notification_service.py | ◐ | 取证（深链接、错误边界、CSRF 轮换、通知语义） |

### 1.5 验收脚本与 fixture

21 个 `frontend/scripts/*.mjs` 全部逐个通读；fixture 漂移对照 api/routes、api/services 当前实现。结论见 §5。

### 1.6 未读与排除

- 各域 `*.test.ts` 单元测试：不属源码审查范围；仅在核对 fixture/契约假设时抽查（problems/client.test.ts、budgets/client.test.ts、monitoring/client.test.ts、experiments/client.test.ts、abtests/statusPolling.test.ts、resources.test.ts）。
- components/charts/*：图表渲染属主路径，前轮已覆盖（本轮仅 analysis.tsx 内消费分支）。
- node_modules 内 react-router 运行时片段：仅取证 `useNavigate` 卸载后行为。

## 2. 发现清单

严重度：P1=错误展示/数据损坏/安全或强可用性影响；P2=边界条件下错误行为；P3=健壮性与一致性改进。除标注「已复核」外均为静态确认（证据链在表内 file:line，未运行复现）。**P1 与高价值 P2 已单独登记 issue（见 §4 链接），此处仅列标题与位置。**

### 2.1 P1（全部已人工复核）

| # | 位置 | 问题 | 状态 | issue |
|---|---|---|---|---|
| P1-1 | pages/Settings/BudgetsPage.tsx:292-306、509-517；api/services/cost_service.py:49-59、594、649 | 编辑预警规则预填脱敏 target 且保存无条件回传，真实投递地址被 `https://host/***` 覆盖，之后全部外发投递静默失效 | 已复核（前后端证据链闭合） | §4-A |
| P1-2 | budgets/client.ts:34-39、89；api/services/cost_service.py:525-529 | `nullableFloat` 拒绝负数，而 `remaining_usd = cap - used` 无下限；超支时整个 `/budgets/usage` 解析失败且重试恒败——恰在最需要看用量的时刻不可见 | 已复核 | §4-B |
| P1-3 | auth/http.ts:277-281 | 刷新失败不区分错误类型：网络中断/5xx/429 时 `options.clear()` 一律清会话，笔记本唤醒后后台预刷新即误登出（服务端 refresh token 仍有效） | 已复核 | §4-C |
| P1-4 | evaluations/workflow.css:13-14、layouts/shell.css:389-392 + 5 个页面文件 | `.evaluation-list-table{min-width:760px}` 在 `.panel{overflow:hidden}` 内且无滚动容器：ExperimentDetail 6 处、ABTestDetail 2 处、Problems 2 处、ABTests/Benchmarks 各 1 处，共 **12 张表**右侧列被裁切且触屏不可滚动（≤767px 恒切；SettingsTable/EvaluationsPage 等 7 处已有包裹先例） | 已复核（静态）；实际裁切待 V06 浏览器实测 | §4-D |

### 2.2 P2（静态确认）

| # | 位置 | 问题 | 状态 |
|---|---|---|---|
| P2-1 | pages/Problems/ProblemsPage.tsx:379、problems/presentation.ts:20-30；api/services/evaluation_results_service.py:80、103、206；src/tasks/evaluation.py:882、932 | 题库历史抽屉判断 `status==='passed'`，后端单元状态写的是 `success`：真实数据下通过率恒 0%、状态列显示英文原值。`verify-problems.mjs:69` 与 `problems/client.test.ts:245,268` 用 `passed` 造数据，掩盖了该缺陷 | 已复核；fixture 掩盖证据确凿 |
| P2-2 | monitoring/presentation.ts:44-46；pages/Settings/SystemPage.tsx:302、338、362；api/monitoring/store.py:222、286、452 | `formatPercent` 按 0–100 设计，直接渲染 `error_rate/success_rate/hit_rate`（0–1 比值）：LLM 成功率 95% 显示成「1%」，API 错误率被显示成「0%」 | 已复核 |
| P2-3 | evaluations/observer.ts:357-401 + evaluations/useEvaluation.ts:166-199 | `connectSocket` 同步抛错（如 `VITE_WS_URL` 未注入）时 `onError` 被 `isCurrent()` 守卫丢弃（`conn` 尚未赋值），观察器永久停在 `connecting`，注释声称的降级轮询不生效，唯一恢复手段是手动刷新 | 静态确认 |
| P2-4 | experiments/client.ts:190-209、benchmarks/client.ts:99-118；src/task_manager.py:618-622、667 | 任务快照解析把任何非 null `progress` 当展示对象并强求 4 个展示字段；后端 `claim_task/pause_task` 会在同一 JSON 写内部字段 `{execution_attempt, stop_confirmed}`。任务在首次展示进度写入前失败/暂停时，详情页永久显示「排队中」，失败原因不可见（基准侧报协议错误且不自刷） | 静态确认 |
| P2-5 | auth/http.ts:257-282 | 跨标签无刷新互斥：两个标签并发刷新时后到者 401 并清共享存储，胜者 store 与存储不一致（误登出）；另有存储已空时不清 store、无 `storage` 事件监听，A 标签登出后 B 标签停留壳内且请求全 401 不跳登录 | 静态确认 |
| P2-6 | pages/Settings/SystemPage.tsx:498-509、600、660-665 | 四个监控数据源 `Promise.all` 绑定：任一辅助统计 5xx/超时/形状不符时整轮刷新失败，首次加载永远停在骨架屏，`/system/status` 的健康数据被连带遮蔽——排查故障时最不可少的部分恰好不可见 | 静态确认 |
| P2-7 | pages/Problems/ProblemsPage.tsx:158-163、230-232；problems/client.ts:199-214；api/files/service.py:314 | 「全部记录无效」这个最常见的导入失败只显示一句英文 message，逐条字段错误明细（`details.errors` / `detail.errors`）被丢弃；与部分无效时有明细不对称 | 静态确认 |
| P2-8 | pages/Benchmarks/BenchmarkDetailPage.tsx:157-170；api/services/benchmark_service.py:212-254 | 基准启动 run 超时/响应丢失后不对账（仅成功路径刷新），重试点击会创建第二个付费 run；`start_run` 非幂等。实验页已有同场景处理（ExperimentDetailPage.tsx:560-563） | 静态确认 |
| P2-9 | App.tsx:18-30、components/common/Feedback.tsx:73 | 无根 ErrorBoundary、无 `vite:preloadError` 处理；新版本发布后旧标签惰性加载 chunk 失败即整树白屏，且 `React.lazy` 缓存 rejected 结果，「重试页面」必然再抛 | 静态确认 |
| P2-10 | layouts/components/NotificationCenter.tsx:119-120；store/notifications.ts:195-199；api/services/in_app_notification_service.py:279-290 | 「清空通知」无确认且忽略当前分类（`clear` 只传 `before`）：分类视图下清空会把其他分类一并写入 `cleared_at`，无恢复入口 | 静态确认 |
| P2-11 | api/services/in_app_notification_service.py:363-364 + evaluation_service.py:35-41 | 任务完成通知「已完成 {{completed}} / {{total}}」分子是单元数（题目×策略）、分母只有题目数：2 策略×3 题显示「已完成 6 / 3」（跨层问题，前端如实渲染） | 静态确认 |

### 2.3 P3（静态确认，摘要）

- **评估域**：降级轮询退避 off-by-one（observer.ts:312-314 首败 6s vs WS 3s）；ResultDetailPage 翻页使观察器整体重建 + 同周期双请求（useEvaluation.ts:271、ResultDetailPage.tsx:84-98）；失败案例面板无上限全量渲染（analysis.tsx:784-818，后端无分页）；result 5xx 被固定文案掩盖丢失 request_id 诊断（results.ts:43-53）；恢复任务命中并发限额返回 400 走「任务状态已变化」误导文案（EvaluationDetailPage.tsx:142-144 + tasks.py:32-40 缺 429 映射）。
- **实验/AB/基准域**：null 预算字段渲染成 `max_tokens ≤ undefined`（experiments/client.ts:92-126 + ConfigSummary）；`readApiKeys` null 时创建实验页永久 Skeleton 无错误无重试（CreateExperimentPage.tsx:44-52，A/B 与基准页同场景会抛错，行为不一致）；轮询停止后 `progress.error` 从不展示（ExperimentDetailPage.tsx:652-668）；failed/cancelled 也显示分析 Tab（后端恒 400）；串行模式下 `max_workers` 校验错误不可见导致提交被静默阻止（CreateExperimentPage.tsx:355-370）；「返回编辑」自导航当前路由无效（:446-453）；A/B 轮询与 useTaskProgress 停止策略不一致（`paused` 不停、协议错误无限重试、无恢复/取消入口 → paused 测试死路，ABTestsPage 也缺 `paused` 筛选）；ABTestDetailPage 未按 testId 重建，切换时 busy/actionError 串页；`launch()` 丢弃返回 job 导致双击 400；create 失败无「结果未知」态可重复提交（后端非幂等）；卸载后 navigate 仍执行（React Router v7 activeRef 不复位）；RunHistory 越界 offset 不回页；编辑套件不去重题目（创建路径有去重）；列表解析 all-or-nothing 比后端 schema 更严（空白名套件/超 2^53 seed 会让整页协议错误）；useTaskProgress 身份切换不清 task（潜在，现调用方有守卫）；running/paused 的 A/B 列表仍显示可用删除按钮（后端恒 400）。
- **设置/监控/题库域**：策略/提供商列表无错误与重试分支，失败显示「暂无数据」（SystemPage.tsx:441-467）；费用概览与预警历史 `Promise.all` 部分失败全隐藏（BudgetsPage.tsx:617-621、772-776）；BudgetsPage `reload()` 无代次守卫，晚到旧响应覆盖新列表（:318-333）；定价历史抽屉切换模型不清旧错误、重试丢弃中止函数（PricingPage.tsx:24-73）；成功/失败共用 info 样式消息（PricingPage.tsx:163-183、BudgetsPage.tsx:131-140）；日志页越界分页无「上一页」回退（SystemLogsPage.tsx:157-226）；403 处理三处不一致（SystemPage 重拉角色 / SystemLogsPage 不拉 / Dashboard 仅通用错误）；`probeStatusLabel` 缺 `healthy` 映射直接显英文（SystemPage.tsx:97，Dashboard.tsx:380 另做特判，两处不一致）；ApiKeysPage JSX 内二次转义致 `/` 显示 `&#47;`（:140-141）；密钥 404/403/409 一律显示「服务暂时不可用」+ 任一行操作后整页进加载态丢其他行编辑（:32-36、275-291）；apiKeys 单行解析失败静默丢行（account/apiKeys.ts:78-86）；题库导出 `window.open` 写死 `/api/v1` 绕过实例 baseURL 与 401 刷新（problems/client.ts:314-315 + ProblemsPage.tsx:497-502）；导入进度不区分永久错误（404 作业不存在）与临时错误，重试无限循环且「开始导入」永久禁用（ProblemsPage.tsx:135-163）；导入作业存储键绑定随机 session marker，重登录后恢复失效且旧键泄漏（:112-118 + store/auth.ts:84-85）；大文件上传成功后重试 startImport 会重新上传整个文件（file_id 未复用，:222-229）。
- **横切面**：http.ts:81-86 错误文案进 React 前做 HTML 转义造成双重编码（`&#39;x&#39;`，被 http.test.ts:386-401 锁定）；store/auth.ts:184-197 登录先写 session 再取 `/users/me`（深链接闪屏 + 多历史条目；资料 401 且刷新失败时静默 return）；http 实例无默认 timeout（nginx 挂起时最长等 300s）；标记已读失败阻止跳转且写失败误报「通知暂时无法加载」（NotificationCenter.tsx:77-78 + notifications.ts:5）；抽屉关闭回焦覆盖路由切换的主内容焦点（AppLayout.tsx:266-268）；shell.css 三处 `.ant-select-selector` 在 antd 6.6.6 DOM 中不存在规则失效（:994-997、1241-1244 + workflow.css:324）；通知抽屉宽度规则因 Drawer className 挂载点变化全部失配（:1218-1220、1251-1255）；`white-space:nowrap` 使 evaluation_id 长串在窄列裁切（:2007-2011）；`/settings` 导航项缺 `end` 与子项同时高亮（Navigation.tsx:67-75）；深链接 returnPath 丢 hash（RequireSession.tsx:14）；登录资料请求失败被吞致顶栏身份空悬（store/auth.ts:191-198）；登出请求失败仍清本地且无提示（:200-208）；BudgetsPage aria 占位符传原始枚举（:164）；en-US 无单复数（`1 minutes`，en-US.ts:1119-1122）。
- **样式**：死规则约 38 个类无 TSX 引用（`.run-row`、`.list-tools`、`.settings-layout` 等，子串扫描下限）；`.sheet` padding 与 `.notification-actions` 不换行在 320px en-US 下估算超宽约 30px（抽屉内可滚动）。

## 3. shell.css 断点清单（静态）

| 断点 | 位置 | 覆盖 | 已知风险 |
|---|---|---|---|
| min-width 1536 | 833-849、2061-2068 | sheet/work-grid/run-* | 无 |
| 1024–1279 | 850-870、2069-2122 | 布局压缩、三风格 focus | 侧栏展开时宽表裁切（P1-4）；Studio 185px 列裁切长 ID |
| max-width 1023 | 871-923、2123-2177、1370-1381 | 外壳切换（侧栏隐藏/顶栏） | `.topbar` 高度被基础规则覆盖失效（:889 vs :1481） |
| max-width 767 | 924-1263、1305-1333、2178-2373、2454-2579 | 移动壳、bottom-nav、触控目标 | `.ant-select-selector`/Drawer className 三处规则失效；宽表未处理（P1-4） |
| max-width 359 | 1264-1287、1382-1391、2387-2402 | 极窄兜底 | `.sheet` padding 被 :2202 覆盖失效 |
| prefers-reduced-motion | 1288-1297、2374-2378 | 动效 | 无 |

横向滚动容器现状：仅 `.evaluation-list-scroll`（workflow.css:6）与 RunHistory.tsx:124 内联 `overflowX`；html/body/.sheet/.route-content 无 overflow-x 兜底；fixed/sticky（skip-link、bottom-nav、topbar、sidebar）经排查未发现定位缺陷。

## 4. 已登记 issue（本轮新缺陷，均含复现与关闭条件）

| | issue | 严重度 |
|---|---|---|
| A | 预警规则编辑回传脱敏 target 覆盖真实投递地址（#450） | P1 数据损坏 |
| B | 超支时 `remaining_usd` 为负导致预算用量接口解析失败（#451） | P1 |
| C | 刷新失败不区分错误类型，网络中断即误登出（#452） | P1 |
| D | 12 张宽表无滚动容器，窄屏右列裁切且触屏不可滚（#453） | P1（待 V06 实测确认幅度） |
| E | 题库历史通过率恒 0%：前端 `passed` vs 后端 `success`，fixture 掩盖（#454） | P2 展示错误 |
| F | 监控比率字段（error_rate/success_rate/hit_rate）按百分比直排，数值缩水 100 倍（#455） | P2 展示错误 |

## 5. 验收脚本与 fixture 漂移

### 5.1 过期脚本（2 个）

| 脚本 | 状态 | 证据 |
|---|---|---|
| verify-shell.mjs | **已知失败**（commit 483e2e0 说明、QA.md:9 仍写「47 项通过」已过期） | 仪表盘搜索框/`.run-row`/EmptyState 锚点在 #293 真实化后消失；#330 持久化通知后未声明 `GET /notifications`（记 unknown）；`/` 与 `/help` 的请求白名单断言与真实仪表盘（`/evaluations`、`/costs/summary`、`/notifications`）矛盾 |
| verify-first-batch-live.mjs | **必然失败** | :244 断言预算页含 `'Mock'`，#330（28061aa）已删该文案 |

### 5.2 fixture 与后端契约漂移

| 漂移 | 证据 | 影响 |
|---|---|---|
| 题库历史状态用 `'passed'`，后端为 `'success'` | verify-problems.mjs:69-79、problems/client.test.ts:245；evaluation_results_service.py:127-139、206 | **高**：掩盖 P2-1 真实缺陷 |
| 4 个脚本未声明 `GET /notifications`（verify-shell、verify-i18n、verify-dataset-references、verify-evaluation-management） | 通知 store 需 `{items,next_cursor,unread_count,server_time}` | 中：shell 记 unknown 失败；i18n 有偶发失败风险；其余通知区报协议错误 |
| CORS/expose-headers fixture 已不起作用 | 37c3d51 起开发环境走同源 `/api/v1` 代理（frontend/.env.development、vite.config.ts:27-31）；`expose_headers` 只在真实跨源生效（api/main.py:183） | 中：verify-evaluations 的 CSRF 轮换断言属虚假信心 |
| 三个 Python 驱动脚本的 WS 地址写错（`/api/v1/ws`，实际 `/api/v1/ws/progress`） | scripts/verify_frontend_first_batch.py:79、verify_results_analytics.py:321、verify_benchmark_history.py:46 | 中低：真实验收里 WS 从未连上（无断言依赖，结果仍 PASS） |
| 评估 fixture 缺 `async_task_id/can_pause/can_resume/can_update/can_delete`；实验作业缺 `task_id` | api/schemas.py:72-80；experiment_service.py:47-55 | 中低：主流程走兼容分支，管理按钮全部隐藏，仅 verify-evaluation-management 在验 |
| 导入触发 fixture 返回 `200/running/failed`，后端实际 `202/pending`（失败用 404/409/429 表达） | api/routes/files.py:137-158、api/files/store.py:248-259 | 中低：真实 409/429 路径未测 |
| 其余低危：取消冲突用 409（后端 400）、已读回执用 204（后端 200）、通知时间带 `Z`（后端无时区）、曲线点缺 `run_id`、A/B 结果缺 formal_statistics 等、`/system/status` 缺 scope 元数据 | 各 verify 脚本 | 低：前端忽略或走兼容分支 |

### 5.3 错误分支契约核对结论（无发现项）

任务/评估详情 403/404、通知清空 200 形状、非法游标 400 detail、报告下载非属主 404、资料冲突 409、密码错误 400、非管理员 403——前后端一致。注意 zh-CN 词典没有后端英文 detail 的对应条目，4xx 时界面直接显示英文（见 §2.3 横切面）。

## 6. 覆盖缺口（建议后续补场景）

| 页面/分支 | 现状 |
|---|---|
| 通知中心批量操作（全部已读/清空/分类筛选/错误重试/`before` 参数） | 唯一覆盖它的 verify-shell 已失效 |
| `/settings/profile` 保存资料 409、改密 400；预警规则新建/编辑/删除；定价追加提交（含零价 #433、带斜杠模型 ID）；日志筛选校验与分页；服务端 403（角色被撤销后） | 无浏览器场景 |
| 基准套件创建/编辑；A/B 启动/删除（400 冲突）/轮询失败恢复（#422）；实验完成态 comparison/panel、删除、任务 404 停轮询；导入作业 404、POST 导入 409/429、`.yaml` 拒绝；登录/注册服务端错误（401/429/400/409）；报告下载 403/404 界面提示 | 无浏览器场景 |
| 主 fixture 升级到当前评估 schema（管理按钮分支） | 兼容分支掩盖 |

## 7. 规格层观察（非实现缺陷，供决策）

任何登录用户可追加全局定价，而定价覆盖影响所有用户的费用与预算计算（api/services/spend_records.py:47、src/tasks/evaluation.py:841）。与 frontend/pricing-management spec「用户 SHALL 能提交」一致，属规格层面的跨租户影响面问题——与 #444 关闭条件第 5 条（确认定价追加权限定位）直接相关，建议在该验收中一并决策。
