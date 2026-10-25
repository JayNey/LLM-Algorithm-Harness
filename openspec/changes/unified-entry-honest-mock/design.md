## 方案

### 统一创建入口

- `AppLayout.tsx` 的 `Shell`：`modal` 状态从 `'create' | 'import' | null` 收窄为 `'import' | null`；`onCreate` 改为关闭抽屉后 `navigate('/evaluations/new')`；`onImport` 保持打开导入示例弹窗。快速操作菜单、侧栏创建按钮、`Outlet context` 的 `actions.onCreate` 结构不变，行为随 Shell 收敛。
- `MockActions.tsx`：删除 `mode === 'create'` 分支（示例表单、busy 定时器、「确认示例配置」反馈）；props 收窄为 `mode: 'import' | null`；保留导入示例与「查看题目库示例」。
- `BusinessPage.tsx`（DashboardPage 实现）：示例面板按钮统一为「创建评估」→ `actions.onCreate`；删除已不再经过该组件的 `/problems` 导入分支与 `/evaluations`、`/results` Mock 列表分支（真实页面已接管）；页头创建按钮与空态按钮不变，行为随 Shell。

### Mock 标记按区域

- 移除外壳级全局标注：顶栏 `preview-tag`「业务 · Mock」、侧栏 `mock-note`「业务与通知 · Mock」、页脚「业务与通知 · Mock」、风格选择器 `mobile-mock`。
- 保留区域级标注：通知中心抽屉 Mock 说明、BusinessPage 各面板 sample-caption／「Mock 快照」／「评估任务详情 · Mock」抽屉标题、导入弹窗说明。
- `notifications.ts` 种子文案「业务与通知均为 Mock 数据」改为「示例与通知均为 Mock 数据」；`route` 字段类型本就只允许 `/results | /evaluations | /help`（列表/帮助页），新增单测锁定种子不含虚构详情 ID。

### 面包屑

- 现实现已按 `detailPages` 匹配（#234 基线带入），本变更不改动匹配逻辑，仅补单测锁定三个真实标题；若单测 RED 再修。

### fixtures

- `verify-evaluations.mjs`：`entries` 已在 known 列表但 dispatch 未实现，本次实现该场景。复用 `fixture()` 路由替换与 `fixture-checks.mjs` 的 `check()`：遍历侧栏、快速操作、页头、空态、帮助页五类创建入口，断言全部落到 `/evaluations/new` 且 DOM 无创建弹窗残留；导入入口断言 Mock 弹窗文案；通知逐类点击断言只落真实列表/帮助路由；示例仪表盘任务断言停留在 Mock 抽屉且 URL 不变。
- `verify-shell.mjs`：自 #214 后未随真实页面更新，`/evaluations` 业务段与创建弹窗断言在 main 上已过期。改锚定：示例仪表盘搜索输入跨风格保留（`data-qa-identity`，替代原创建弹窗草稿证据）；空态「创建首个评估」点击后断言落在 `/evaluations/new`；最终「无业务 API 请求」断言加入真实创建页只读接口白名单（api-keys / evaluation-options / problems，响应形状沿用本仓库既有 fixture 契约，不从旧示例臆测）。

### 测试与验证命令

- 单测：`app-shell.test.ts` 面包屑补 `/results/eval-123 → 评估结果详情`，并新增「SSR 外壳不含全局 业务 · Mock 标注」断言；`notifications.test.ts` 补种子路由边界。
- 命令（frontend/ 下）：`npm run lint`、`npm test`、`npm run build`；fixture：`node scripts/verify-evaluations.mjs --scenario entries`、`node scripts/verify-shell.mjs`。
