# workflow-css-shared-layout 验证报告

- 日期：2026-11-03
- 分支：`tweak/20261103/workflow-css-shared-layout`
- 提交：`e06bc2f`（`tweak: 将 workflow.css 收口到共享布局并新增直接加载视觉 smoke`）
- 工作流：tweak；`verify_mode: full`（含 delta spec）
- 产物语言：zh-CN

## 范围

验证“工作流样式改由共享布局加载”与“直接加载视觉 smoke”两项改动，覆盖：

- `frontend/src/layouts/AppLayout.tsx` 新增 `@/evaluations/workflow.css` 导入，并删除 10 个页面的重复导入。
- 新增 `frontend/scripts/verify-direct-load.mjs`：针对生产构建直接加载 6 个工作流路由。
- `docs/frontend/QA.md` 的运行说明。
- delta spec：`openspec/changes/workflow-css-shared-layout/specs/frontend/app-shell/spec.md`。

## 命令与结果

| 命令 | 结果 |
| --- | --- |
| `cd frontend && npm test` | 322 项通过，0 失败，退出码 0 |
| `cd frontend && npm run lint` | 退出码 0，无错误 |
| `cd frontend && npm run build` | 退出码 0，`dist/assets/index-*.css` 含 `.evaluation-list-table`，不再产出独立 `workflow-*.css` |
| `cd frontend && DIRECT_LOAD_QA_DIR=/tmp/direct-load-verify PLAYWRIGHT_MODULE=<external> CHROME_PATH=<chrome> node scripts/verify-direct-load.mjs` | 66 项断言通过，0 失败，0 未声明请求，退出码 0 |
| `comet classic openspec -- validate workflow-css-shared-layout --type change --strict --no-interactive` | `Change 'workflow-css-shared-layout' is valid` |
| `cd frontend && npm run format:check` | 退出码 1，仅 `scripts/verify-settings.mjs`（本次未修改的既有文件）未格式化；本次改动文件 `src/layouts/AppLayout.tsx`、`scripts/verify-direct-load.mjs`、`docs/frontend/QA.md` 均通过 Prettier |

## 完整验证检查项

| 检查项 | 结果 | 证据 |
| --- | --- | --- |
| 1. tasks.md 全部完成 | PASS | 4/4 勾选；build 守卫同样通过 |
| 2. 实现符合 `design.md` 决策 | PASS | 共享布局导入、仅保留一个导入来源、smoke 分三层断言、入口 CSS 层叠顺序均按 design 落地 |
| 3. 实现符合 Design Doc | N/A | tweak 不产出 `docs/superpowers/specs/` Design Doc；本 change 以 `design.md` 承担设计说明 |
| 4. 能力规格场景通过 | PASS | 见下方场景覆盖表 |
| 5. proposal 目标满足 | PASS | 共享样式进入入口 CSS、页面重复导入删除、直接加载 smoke 可重复执行并有报告与截图 |
| 6. delta spec 与 design 无矛盾 | PASS | design.md 与 delta spec 对共享加载、单一来源、smoke 断言范围的描述一致，无漂移 |
| 7. `docs/superpowers/specs/` 设计文档可定位 | N/A | tweak 无关联 Design Doc（`design_doc: null`），已在 `design.md` 顶部说明 |

## Delta spec 场景覆盖

| 场景 | 覆盖方式 | 结果 |
| --- | --- | --- |
| 直接打开实验列表 | smoke 直接 `goto /experiments`，断言表格 `border-collapse: collapse`、`min-width: 760px`、单元格内边距 16px/12px、1440 与 390 宽度无横向溢出 | PASS |
| 直接打开其他工作流页面 | smoke 直接加载 `/experiments/new`、`/experiments/exp-fixture-1`、`/ab-tests`、`/ab-tests/new`、`/benchmarks/suite-fixture-1`，断言面板内边距、容器 `min-width: 0`、无溢出、无 `pageerror` | PASS |
| 单一导入来源 | smoke 静态扫描 `src/pages/**`，断言不再出现 `evaluations/workflow.css`；`grep` 确认只剩 `AppLayout.tsx:36` 一处导入 | PASS |
| 运行 smoke | 缺构建产物时明确报错；全部断言通过时退出码 0，任一失败退出码 1 | PASS |

## 集成代码审查

`review_mode: off`（tweak 默认）。按 `/comet-verify` 规则跳过自动 code review，原因记录为：本次改动为样式导入收口与验证脚本新增，无业务逻辑、接口或数据处理变更；构建、测试、lint、浏览器 smoke 与 OpenSpec 校验已覆盖正确性与边界。

## 产物

- 截图与报告：`docs/frontend/assets/direct-load/`（`report.json` 66 项断言，8 张截图）。
- 验证时的 smoke 重跑输出写入 `/tmp/direct-load-verify/`，避免污染已提交产物。

## 例外与限制

1. `npm run format:check` 全仓失败仅因既有 `scripts/verify-settings.mjs` 未格式化，与本次改动无关；未在本 change 内修复该无关文件，建议单独提交 `npx prettier --write scripts/verify-settings.mjs`。
2. smoke 使用外部 Playwright 包（`PLAYWRIGHT_MODULE`）与系统 Chrome（`CHROME_PATH`），仓库未新增依赖；fixture 替换全部 `/api/v1/**` 响应，不证明真实后端、真实登录或生产部署。
3. 验证为 Chromium 桌面/移动视口模拟，未覆盖 Safari/Firefox、真机和屏幕阅读器。
4. `docs/reviews/` 为上一轮审查产物，用户确认保持未跟踪，不并入本 change。

## 结论

PASS。无 CRITICAL/IMPORTANT 问题；`format:check` 的既有失败已记录为与本 change 无关的例外。
