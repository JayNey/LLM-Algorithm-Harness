# #223 真实评估列表验证报告

日期：2026-10-22（Asia/Shanghai）。初始 main 基线 19609830f7051773ad8c42be4146c281930bba07；应用实现与浏览器证据头 b2e9bd09ae84a4e880f56ed4028dff63b2504e36。使用单一 change `owned-evaluation-list`，沿用已确认的增量 Tweak 和个人任务分支。

## 依赖与边界

新分配任务为 #223、#226、#229、#232；另有既有 #157。本轮先做 #223：#220/#221/#222 的当前状态均为 CLOSED/COMPLETED，客户端、session provider 和创建页面实际已在 main；#222 正文保留历史“待审查”快照，本轮按最新关闭状态、主线实现及当前创建回归核对，不仅依赖旧快照。#226 仍依赖 #224/#225，#229 还依赖后续流程页面，#232 依赖 #231；均未据此宣称可完成真实端到端。

## 实现

- 评估列表从现有 EvaluationSession 的 Cookie/CSRF HTTP 客户端加载，不新增客户端或认证逻辑。用 evaluation_id 作为任务标识和详情链接，无虚构名称、名称搜索或 Mock 行。
- 展示服务端模型、策略、题目数、开放状态、execution_progress 和 USD 费用/预算。未知状态保留原值；pending 依据 can_start 区分待启动与已入队。
- URL 保存 status/limit/offset，筛选清零 offset，支持刷新和后退；超页根据实际 total 回到最后有效页，空集回到 0。加载、账号空集、筛选空集和请求失败分别呈现，重试保留当前查询。
- useList 的 AbortController、请求代际和 owner/loader/query/重试身份校验阻止迟到覆盖；渲染阶段即隐藏不属于当前身份或查询的数据。匿名 owner 不请求数据。
- 保留三风格、主题和移动导航。表格自身可滚动，未改变外壳、全局入口、客户端契约或路由；外壳的全局 Mock 提示仍由 #228 负责。

## 实际验证

以下命令从 frontend 执行，均退出 0（RED 步骤除外）：

- `npm test`：151 passed、0 failed。新增 URL 查询往返测试；浏览器中的实际 React 生命周期另行验证。
- `npm run lint`：0 错误、0 警告。初次新增 ref 清理警告已通过移除冗余代际增量解决；取消信号与新请求代际仍负责隔离，未用 eslint-disable 绕过。
- `npm run build`：类型检查和生产构建通过。
- 变更文件 Prettier 检查通过；OpenSpec strict 通过。
- `node scripts/verify-evaluations.mjs --scenario list`：22 组断言通过。先在原 Mock 页面重现加载状态缺失（退出 1）；实现后覆盖真实字段、未知/入队状态、20 条分页、尾页、筛选重置、刷新/后退、三风格状态保持、503 重试、账号/筛选空集、非首页超页恢复、迟到查询等。
- list 场景另在真实 React StrictMode 下使用故意忽略 AbortSignal 的可控 loader：验证旧查询、旧 owner、换 owner 首次提交隐藏旧数据、失败与合法空页、重试和卸载后的迟到结果。它是前端生命周期 fixture，不是实际 API 身份联调。
- `node scripts/verify-evaluations.mjs --scenario create`：37 组断言通过，含已有创建/会话安全回归，验证本轮没有破坏 #222 既有流程。
- 独立 Bugbot：审查整个分支相对 origin/main 的差异，无发现。审查覆盖 hook 生命周期、owner 隔离、客户端契约、URL 筛选分页、超页恢复、渲染和 fixture；未修改文件。此处不声称审查者额外执行了测试。

调试期间还修正了两处 fixture 定位：Ant Design 中文按钮的可访问名称含空格；历史后退断言使用只属于目标页的任务，避免与筛选结果重叠。未通过放宽功能断言接受错误行为。

## 公开证据与复现

- [list JSON](../../frontend/assets/evaluations/list/list.json)：实际头、替换依赖、请求、22 组断言及截图索引。
- [390px 列表](../../frontend/assets/evaluations/list/list-390.png)、[1440px 列表](../../frontend/assets/evaluations/list/list-1440.png)：人工已检查，截图为 Studio/light；页面无横向溢出，手机表格可独立滚动。不是全设备/全主题组合验收。
- 本机日志：/private/tmp/issue223-list-red.log、issue223-list-final.log、issue223-create-final.log、issue223-unit.log、issue223-build.log、issue223-lint.log；路径仅用于本机核验，不是其他环境的依赖。

先运行 `npm ci`，在 frontend 启动 `npm run dev -- --host 127.0.0.1 --port 5180`。另一个终端运行上述 fixture；Playwright 需在执行环境提供，可用 `PLAYWRIGHT_MODULE=/absolute/path/to/playwright` 指向外部包，或安装在可解析位置。`EVALUATION_BASE_URL` 可覆盖地址，`EVALUATION_QA_DIR` 指定输出目录；可选 `CHROME_PATH`，否则使用 Playwright Chromium。脚本未知业务请求会失败，不回退为成功。

## 验收范围与剩余事项

本轮证据为前端单测、类型/工程检查、浏览器 HTTP fixture 和 React 生命周期。身份 API 与列表响应由脚本替换；没有连接真实 Redis/Celery、供应商或沙箱，没有证明真实账号登录到结果的端到端联调。完整详情/进度、结果、全外观矩阵、真实联调分别由 #224/#225、#226/#227、#229、#232 跟踪。保留这几个验收层级，不将 #223 的 fixture 结论外推。

PR 的 CI 与 Runtime 阶段检查在提交后补充；合并/关闭任务由实际验收结果决定。本轮 authored commits 排除 .comet/.claude/.codex/.agents/skills-lock.json。

## 规格核对

真实列表与未知状态场景对应 list fixture 的真实字段/状态断言；加载、两类空集与错误重试分别覆盖。URL 场景对应分页参数、刷新/后退、筛选清零和末页恢复断言；异步隔离对应忽略 AbortSignal 的实际 React 生命周期断言及 HTTP 迟到筛选测试。实现与 proposal/design/delta spec 一致，无范围缩减。

交付前 main 新增 #239（API 重启时独立 worker 任务恢复），仅后端任务服务及其测试/报告发生变化，前端受测源码未变。分支将基于该最新 main 重放后交付；上述前端证据保留其真实来源提交。全量 Prettier 检查亦退出 0。
