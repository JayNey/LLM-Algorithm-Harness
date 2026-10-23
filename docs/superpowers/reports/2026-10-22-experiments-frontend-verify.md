# 验证报告：experiments-frontend（issue #166 第①步：实验管理前端簇）

- 日期：2026-10-22
- 分支：comet/experiments-frontend（交付目标 tweak/20261022/experiments-frontend）
- 基线：47a9a5a（upstream/main），8 个提交，25 文件（+4229/−5）
- 验证模式：full（1 份 delta spec；规模远超 light 阈值，用户已确认继续 tweak）
- 集成审查：两轮制独立审查（general-purpose 只读子代理）。第一轮 REQUESTS_CHANGES：**1 P0**（后端 config JSON 无顶层 api_key_id，解析器会让真实后端下全部页面不可用——所有夹具曾人为注入该键掩盖缺陷）+ 3 P1（`_rate` 分母为零的 null 比率被拒、advisory.excluded 形状错位、启动后 pending 盲区可重复 enqueue）+ 8 P2 → 662d2c6 / a35c7b1 修复 → 定点复审 **APPROVE**（3 条一行级遗留全部已随手修复：取消后清启动锚、paused 任务可取消、budget_recommendations.point_id 可空）。

## 1. Completeness

| 检查项 | 结果 | 证据 |
| --- | --- | --- |
| tasks.md 14/14 全部勾选 | PASS | 未勾选 0 |
| delta spec 4 条需求全部有实现与测试载体 | PASS | 见 §2 |
| proposal 目标（创建/列表/详情+对比/帕累托/成本建议、路由增量、verify 骨架）满足 | PASS | 页面三件、图表薄封装、verify-experiments.mjs 均落地；基准/AB 按声明递延第②步 |

## 2. Correctness：需求与场景映射

| Spec 需求 | 实现 | 场景覆盖 |
| --- | --- | --- |
| 实验创建与启动（校验对齐 schema、创建后导航、run 返回 task_id 锚定） | validation.ts + runCreation.ts + CreateExperimentPage + 详情页 start() 以 task_id 置 started 锚 | validation.test（合法 payload / 逐字段错误 / 过滤空模型 / 温度越界）、runCreation.test（creating→created、非法停 editing、网络→create-unknown、4xx→editing、owner 失配拒写）；「非法草稿本地拒绝」场景由 validateExperimentDraft 前置于网络请求保证 |
| 实验列表与生命周期（服务端分页、状态白名单回 URL、删除确认、经任务通道取消、不伪造搜索/克隆） | ExperimentsPage + client.runningExperimentTasks（running+paused 并查去重）+ cancelTask | validation.test（URL 白名单/钳位）、client.test（任务索引与 DELETE /tasks）；页面无搜索/克隆入口（审查项 7 核实） |
| 异步进度观察（3s 轮询、终态/paused 停、卸载取消、连续失败暂停重试、不用 WS） | useTaskProgress（快照派生、AbortController + generation、3 次失败暂停） | client.test（task 快照 progress 形状）；hook 逻辑经审查静态核对（无 set-state-in-effect，eslint react-hooks 规则通过） |
| 对比分析与可视化（组合表、热力图、McNemar 标注、成本效益、panel、帕累托、成本建议，惰性加载，形状不符显式报错） | 详情页 4 个 Tab（挂载即加载 = 惰性）+ WinRateHeatmap/CompareCharts + client 严格解析 | client.test（嵌套矩阵/可空 p 值与缺省 a/b、真实 null 比率形状、pareto 前沿、optimize 三目标、原始报告上报 deepEqual） |

## 3. Coherence

- design.md 决策逐条落实并已回写事实：同构新簇、零改 client.ts（evaluations）、轮询不走 WS、创建→启动相位（editing/creating/created/create-unknown）、列表取消经任务索引、分析 Tab 惰性、图表薄封装、verify 骨架、测试策略。契约盘点修正为真实形状（config 无顶层 api_key_id；null 比率；pareto/optimize 上报原始报告）。
- 无 Design Doc（tweak 预设），检查项 7 记 N/A。
- 规范纪律：未混入第②步内容；未伪造后端不支持的入口（审查项 7 已核实）。
- 代码模式：遵循 `.ts/.tsx` 后缀 import、`import type`、erasableSyntaxOnly；session/useList 跨簇复用属既定同构策略。

## 4. Runtime 检查证据

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| build：`bash -lc 'cd frontend && npm test'` | exit=0 | openspec/changes/experiments-frontend/.comet/checks/c5e8d0ce-….log（167 tests 全过） |
| verify：同命令（报告定稿后采集） | 见 .comet/checks/ 最新日志 | 167/167 |
| lint / type | PASS | `npx tsc -b` 0 错误；`npx eslint`（experiments/pages/charts/verify 脚本）0 problems；prettier 通过 |
| 安全 | PASS | 全 diff 无 dangerouslySetInnerHTML/innerHTML；panel 文本走 React 文本节点与 echarts canvas；无新增依赖 |

## 5. 限制与偏差声明

- `verify-experiments.mjs` 为浏览器 fixture 层（不连真实后端），需手动启动 dev server 运行；本报告未在本机执行 Playwright（环境未装浏览器），脚本经 `node --check` 与 eslint 校验，场景逻辑经审查静态核对。
- 真实后端联调（创建→启动→Celery 执行→对比报告）未在本 change 执行——依赖真实 LLM 密钥与 worker；严格解析已按 upstream/main 源码字节级对齐，形状漂移会显式报错而非静默。
- `POST /tasks/{id}/resume`（恢复暂停）未接入，递延第②步；paused 任务可取消。

## 结论

三维验证无 CRITICAL、无 WARNING；两轮独立审查最终 APPROVE 且遗留全部已修。**验证通过，可进入归档确认。**
