## Why

#229 需要证明真实评估页面在窄屏、常见平板和桌面宽度下仍可操作，同时切换三套外观与主题不会丢失当前路由、筛选或表单草稿。现有浏览器脚本已有零散的尺寸断言，但 `appearance` 场景尚未实现，覆盖也未形成统一矩阵。

## What Changes

- 增加独立的评估外观浏览器验收入口，覆盖创建、任务列表、任务详情、结果列表和结果详情。
- 对 Orbit、Precision、Studio × light、dark × 320、390、768、1440px 运行页面溢出、键盘可达、筛选/表单状态保持检查，并保存精确组合和限制。
- 仅在矩阵暴露可复现的页面溢出或操作问题时，按现有外观契约修正相关 CSS。
- 更新前端 QA 文档，标明 fixture 替换的依赖和未验证的真实设备/后端层级。

## Capabilities

### New Capabilities

无。此变更增加验收工具并验证已有外观契约，不引入产品能力。

### Modified Capabilities

无。实现遵循 `openspec/specs/frontend/app-shell/spec.md` 中已有的三套风格、主题和状态保持要求；不改变该契约。

## Impact

- 新增独立浏览器脚本，避免与尚未合并的 #228 在 `verify-evaluations.mjs` 上冲突。
- 可能修正 `frontend/src/evaluations/workflow.css` 中被矩阵证实的问题。
- 更新 `docs/frontend/QA.md` 并保存当次验收报告及截图。
- #228 已通过 #278 合并；在 PR #282 同步 `main`@`b8ff9fd` 后，将外观矩阵接入 `verify-evaluations.mjs --scenario appearance` 及 `all`。
- 补齐多页题目选择、创建字段和完整筛选 URL 保持，以及移动导航、Esc 关闭和焦点恢复检查。
- 将 JSON 和代表性截图保存到仓库公开路径，在 QA 和验收报告中记录命令、退出码、代码基线及审查结论。
