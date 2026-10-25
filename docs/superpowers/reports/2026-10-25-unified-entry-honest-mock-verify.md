# 验证报告：unified-entry-honest-mock（T13 统一入口与诚实 Mock 标记）

日期：2026-10-25 · 分支：`tweak/20261025/unified-entry-honest-mock`（基于 upstream/main 2950180）· 提交：b2e9407 → 13adc57（→ 收尾提交）
上游 issue：JayNey/LLM-Algorithm-Harness#228 · OpenSpec change：`openspec/changes/unified-entry-honest-mock`

## 行为验收（browser fixture，非后端 E2E）

### entries 场景（verify-evaluations.mjs，本轮新增）

- **RED**（实现源码前，b2e9407 之前的工作区）：`node scripts/verify-evaluations.mjs --scenario entries` 退出 1——侧栏创建按钮点击后 `waitForURL('**/evaluations/new')` 30s 超时（旧 Mock 弹窗行为），行为级 RED 符合 issue Step 2 预期。
- **GREEN**（实现后）：退出 0，`{"scenario":"entries","pass":true,"assertions":16}`。覆盖：
  - 五类显式创建入口（侧栏按钮、快速操作菜单项、仪表盘页头按钮、空状态「创建首个评估」、帮助页创建按钮）全部落到 `/evaluations/new`，面包屑「创建评估」；
  - 创建页无模拟弹窗残留（无「例如：HumanEval 基线对照」占位、无「确认示例配置」文案）；
  - 导入入口（侧栏 + 快速操作）保持明确 Mock（「不读取或上传文件」），无创建表单混入；
  - 通知三类点击分别只落真实 `/results`、`/evaluations`、`/help`，不指向虚构详情路由；
  - 示例仪表盘任务停留在「评估任务详情 · Mock」抽屉，URL 不变；
  - 真实评估页无全局「业务 · Mock」「业务与通知 · Mock」标注；示例仪表盘保留区域标注；
  - 全场景 POST 请求为 0、无页面异常、无未声明 API 请求。
- 证据：`docs/superpowers/reports/assets/evaluation-live-workflow/fixture/entries.json`、`entries-create-page.png`。

### verify-shell.mjs（过期业务段修复）

- 修复前在 main 基线即不可通过：该 fixture 自 #214 后未随真实页面更新，「评估任务」点击后仍按 Mock 页断言（`搜索评估任务` 输入框在真实评估页不存在），且创建弹窗草稿/「示例配置已确认」断言对应本变更删除的行为。此为既有差异，本变更一并修复并在 PR 记录。
- 修复后：退出 0，`PASS: 50 browser checks; no business API requests or page errors`（审查修复提交 13adc57 后复跑再次通过）。断言调整：Mock 列表交互锚定示例仪表盘；创建入口断言改为导航断言（快速操作段先回仪表盘再点击，可独立失败）；「无业务 API 请求」白名单加入真实创建页只读接口（api-keys / evaluation-options / models / problems，响应形状与 `frontend/src/account/apiKeys.ts`、`frontend/src/evaluations/client.ts` 解析器逐字段一致，审查者实测核对）；移动抽屉导航目标由「基准测试」（真实页，会拉业务数据）改为帮助页。
- 证据：`docs/superpowers/reports/assets/issue168/checks.json` 与截图。

## 单测与静态检查（frontend/ 下）

| 命令 | 结果 | 退出码 |
| --- | --- | --- |
| `npm test` | 250 pass / 0 fail（含新增：通知种子路由边界；app-shell 补 `/results/eval-123 → 评估结果详情`、无全局 Mock 标注、无创建弹窗占位断言） | 0 |
| `npm run lint` | 0 errors（2 warnings 为 `BenchmarkDetailPage.tsx` 131/145 pre-existing，不在本次 diff） | 0 |
| `npm run format:check` | All matched files use Prettier code style! | 0 |
| `npm run build` | `tsc -b` + vite 构建成功（chunk 大小 warning 为既有现象） | 0 |

最终收尾提交前在最新工作树重跑上述四项与两个 fixture，结果同上。

## 独立审查（两轮制，general-purpose 只读子代理）

- 第一轮（全量 `git show b2e9407`，实测复跑单测/tsc/lint）：**approves**，无 P0/P1；P2×3：孤儿化死 CSS（采纳，已清理）、verify-shell 快速操作段弱断言（采纳，已补强）、导入弹窗「查看题目库示例」措辞（改动前既有文案，按审查建议留待后续）。
- 第二轮（定点 `git show 13adc57`）：**approves**，无遗留问题；确认死 CSS 无误删、断言可独立失败、后续段落前置状态不受影响。

## 实现要点与差异记录

- Shell.onCreate → `navigate('/evaluations/new')`；`MockActions` 收窄为 `'import' | null` 并删除创建分支；BusinessPage 示例按钮统一「创建评估」并清理死分支（`/problems`、`/experiments`、`/benchmarks`、`/evaluations`、`/results` 已由真实页面接管）。
- 全局 Mock 标注（顶栏 preview-tag / 侧栏 mock-note / 页脚 / 风格选择器）移除，区域标注保留；shell.css 孤儿规则随 PR 清理。
- fixture 层修复记录：真实列表页挂载后 `writeListQuery` 重写 URL 更换 `location.key`，通知抽屉以 `openedAt === location.key` 判定开合——bell 点击与 URL 改写竞态会导致抽屉开启即关闭，属列表页有意设计（导航关抽屉）与 fixture 时序过紧的组合，产品行为未改，entries 场景以 `stabilize()` 等 URL 稳定后交互；antd Drawer title 为 div 非 heading role，定位改用文本。

## 未验证层级（如实标注）

- 真实后端联调（离线 HTTP fixture 之外的层级）：真实 Redis/Celery、供应商与沙箱联调未执行——本变更不触碰创建页数据流与通知接口契约，相关层级由 #231/#232 的既有与后续验证覆盖。
- WebSocket 实时进度未在本变更场景内新增断言（entries 场景不涉及 WS；observe 相关层级维持 #256 既有证据）。
