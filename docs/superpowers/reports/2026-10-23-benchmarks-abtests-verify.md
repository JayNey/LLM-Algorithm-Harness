# 验证报告：benchmarks-abtests（issue #166 第②步：基准 Suite + 学习曲线 + AB 测试页）

- 日期：2026-10-23
- 分支：comet/benchmarks-abtests（交付目标 tweak/20261023/benchmarks-abtests）
- 基线：5810e9f6（upstream/main，含第①步），4 个提交，31 文件（+3667/−14）
- 验证模式：full（2 份 delta spec；用户确认继续 tweak）
- 集成审查：两轮制独立审查。第一轮 REQUESTS_CHANGES（**2 P0**：AB 结果 elapsed_seconds/tokens 为按变体字典、failure_categories 为二层嵌套，扁平解析必炸；**/benchmarks 与 /ab-tests 列表路由未接线**——两列表页不可达；5 P1：PATCH 携带后端不存在的 name、基准 run strategies 须为对象数组、trends 负增长率被拒、run 终态后结果陈旧且失败无处展示、verify/测试夹具固化错误形状）→ 首轮修复部分静默未落地（批量替换锚点失配 + commit message 声称与 diff 不符）→ 二次复审拦截 → 2b4ebaf 真修 → 三次定点复审 **APPROVE**（零阻塞遗留；非阻塞观察：run `{name}` 形状与 null 时间戳解析暂无单测断言，属测试缺口非缺陷）。

## 1. Completeness

| 检查项 | 结果 | 证据 |
| --- | --- | --- |
| tasks.md 9/9 全部勾选 | PASS | 未勾选 0 |
| delta spec 4 条需求全部有实现与测试载体 | PASS | 见 §2 |
| proposal 目标（基准簇/AB 簇/图表/路由/验证脚本）满足 | PASS | 全部落地 |

## 2. Correctness：需求与场景映射

| Spec 需求 | 实现 | 场景覆盖 |
| --- | --- | --- |
| 基准 Suite 管理（列表全量/创建/PATCH 可选字段/启动 run/task 进度/无删除入口） | benchmarks client + BenchmarksPage 内联创建 + 详情页编辑与 run 表单 | client.test（列表壳/详情/run 202+task_id/run 可空指标/拒绝路径）；PATCH 载荷与 Update schema 逐字段一致（审查核实）；删除入口不存在（范围纪律核实） |
| 学习曲线展示 | learning-curve 端点 + TrendLine 按模型分组折线 + trends 文字 | client.test（多模型序列/可空点/负增长率 -0.25）；timestamp 可空三层闭合（类型/解析/图表过滤） |
| A/B 创建与列表（双变体校验、分页筛选删除、启动仅状态可查） | validation + CreateABTestPage + ABTestsPage + useStatusPolling（5s 至终态） | client/validation.test（payload seed 默认 42、逐字段错误、变体 ID 重复拒绝、URL 白名单）；「变体数量不满足本地拒绝」由 validateABTestDraft 前置保证；「启动后仅状态可查」由无 task_id 契约 + 状态轮询实现 |
| A/B 结果统计展示（两组比率/ci95/检验三态/失败分类，形状不符显式报错） | results 严格解析（ratePair 全可空 + signed 数值 + 按变体字典/嵌套分类）+ 按变体统计表 | client.test（ci95 可空、unavailable 三态、嵌套分类 deepEqual）；「完成后统计表渲染」由 verify-benchmarks ab-detail 场景覆盖（浏览器 fixture 层） |

## 3. Coherence

- design.md 决策落实并经二轮回写实况：两自包含簇、严格解析子集、runCreation 不引入（AB 创建为页面内联状态，回写注明）、进度通道复用与轮询策略、AB 单次失败不打断轮询（design 明文）。
- useTaskProgress 泛型化为结构化窄接口——experiments 既有调用行为不变（审查交叉核对）。
- 无 Design Doc（tweak 预设），检查项 7 记 N/A。
- 规范纪律：无 Suite 删除/run 列表/AB 取消/分层 AB 等不支持入口；verify mock 与真实契约一致（含嵌套形状）；无注入面。

## 4. Runtime 检查证据

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| build：`bash -lc 'cd frontend && npm test'` | exit=0 | .comet/checks/70488551-….log（178 tests 全过） |
| verify：同命令（报告定稿后采集） | 见 .comet/checks/ 最新日志 | 178/178 |
| lint / type | PASS | `npx tsc -b` 0 错误；eslint 0 error（2 条 exhaustive-deps warning 为刻意的终态重取触发器，已注释）；prettier 通过 |
| 安全 | PASS | 无注入面；路径 ID encodeURIComponent；无新增依赖 |

## 5. 限制与偏差声明

- 真实浏览器/真实后端联调未执行（Playwright 环境未装、依赖真实密钥与 worker）；verify-benchmarks.mjs 经 node --check + eslint 校验，场景逻辑静态核对。
- 首轮修复静默未落地一事已如实记录：根因为 husky 提交钩子（prettier）重排文件后，后续批量替换锚点失配且未校验落点；整改为全部改用 Edit 工具（带过期检测），并由二次复审逐项拦截确认。

## 结论

三维验证无 CRITICAL、无 WARNING；三轮审查（两轮定点）最终 APPROVE。**验证通过，可进入归档确认。**
