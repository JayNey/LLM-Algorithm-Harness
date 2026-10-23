# 评估详情与真实操作验收（#224）

日期：2026-10-23。Change：evaluation-detail-actions。分支：codex/evaluation-detail-actions。基线：fa60243e975debb1595d8d959d07ecc73430854f（接手时最新 origin/main）。前置 #218/#220/#221/#222/#223 均已关闭且实现已合并 main。

## 实现与范围

将原内存回执页改为 GET 驱动的详情页，展示 evaluation_id、模型、策略、服务端状态与单元进度、预算、成本、创建/更新时间和错误原因。挂载和手动刷新没有 POST。既有 routes.tsx 已注册 `/evaluations/:evaluationId`，故无需重复添加路由；同时修复导航面包屑未匹配详情路由的问题。

详情动作在现有创建协调器中使用独立 action 状态，与创建/自动启动共享锁，不改写创建回执或草稿。动作预检 GET 核对能力，POST 前校验 owner、operation 与页面 AbortSignal；不把响应接受模拟为 running/cancelled。动作结束重新 GET，失败保留 ID 和数据；暂时刷新失败禁用旧能力，403/404 清除快照。创建未知仍禁止重建，但允许操作已核对的既有 ID。

用户明确确认继续 tweak（超过六文件提示阈值）并从最新 main 创建新分支。本轮没有后端、认证协议、依赖、数据库或 public API 修改。

## 验证结果

以下命令均从 frontend 执行，退出码均为 0：

- `npm test`：174 passed、0 failed，包含 21 项协调器测试和详情/创建面包屑测试。
- `npm run lint`：通过。
- `npm run format:check`：通过。
- `npm run build`：类型检查与生产构建通过；现有实验详情的大 chunk 提示仍存在，本轮详情独立 chunk 约 3 KB，未扩大该实验依赖。
- `node scripts/verify-evaluations.mjs --scenario detail`：25 组断言，真实 React StrictMode、router、session provider、客户端、协调器与页面。
- `node scripts/verify-evaluations.mjs --scenario create`：38 组断言，含 201 后转详情、启动失败后仅重试 start、不再次 create。
- `node scripts/verify-evaluations.mjs --scenario list`：22 组回归断言。

仓库根 `git diff --check` 和 `comet classic openspec -- validate evaluation-detail-actions --strict` 均退出 0。

RED 证据：实施前 detail fixture 因缺少详情状态区域超时，退出 1；取消协调器测试因未实现动作失败。面包屑新增测试在原代码输出“页面未找到”时失败。审查修复先补详情动作生命周期、创建未知和后续创建回归，再实现独立 action 状态，21 项协调器测试全部通过。

## Spec 场景对照

- 直接访问/刷新：两类 pending、running、paused、completed、failed、cancelled、未知状态；按钮严格来自 can_start/can_cancel，刷新只 GET。
- 动作与竞争：取消成功、503、409 输给完成，启动失败重试，重复点击共享锁；服务端快照决定最终状态。
- 加载/权限：初始 403/404 无动作，刷新 503 保留数据并禁用操作，403 清除后可重试恢复。
- 生命周期：真实 useEvaluation 在忽略 AbortSignal 的 transport 下拒绝旧路由/刷新/owner 响应；卸载不再提交。真实路由离页使启动与取消的预检失效，不继续 POST；取消既有任务后仍可在同会话创建新任务。
- 外观：Orbit/Precision/Studio × light/dark × 320/1440px，12 个截图组合均无页面横向溢出。人工检查桌面与移动截图，保持既有外壳和导航。全局 Mock 标签由 #228 负责，本轮保留。

## 代码审查

按 requesting-code-review 派发独立只读审查。首次发现三项 P2：详情离页后预检仍 POST、create-unknown 使详情动作静默失效、详情动作占用创建回执。均在当前 change 修复并补回归。定点复审通过，未发现剩余可操作正确性、安全或边界问题；审查者独立运行协调器测试 21/21 通过。

完整性：3/3 tasks 完成，1 条 ADDED requirement、5 个场景已对应实现和测试。实现遵循 design.md；tweak 无单独 Superpowers Design Doc/plan，不将该豁免视为缺失。无 spec/design 漂移。结论：PASS，可进入归档确认。

## 证据与复现

公开 fixture 证据位于 [detail.json](../../frontend/assets/evaluations/detail/detail.json)，同目录包含 12 张详情截图与 create/list 回归 JSON。截图证据生成于工作区实现版本，JSON 的 source 记录了执行时 HEAD 和 dirty 路径，不能把基线 HEAD 误称为已包含所有变更的提交。

先 `npm ci` 并启动 `npm run dev -- --host 127.0.0.1 --port 5180`。验收脚本使用外部 Playwright（不新增仓库依赖），可通过 `PLAYWRIGHT_MODULE` 指定包路径；`CHROME_PATH` 可选。默认写入报告资产目录，`EVALUATION_QA_DIR` 可覆盖输出；fixture 声明替换的 HTTP 边界并拒绝未知请求。

验证层级：已执行浏览器 fixture、前端单测/SSR/工程检查。未执行离线真实 HTTP 后端联调、真实 Redis/Celery、真实供应商、沙箱执行、真实移动设备与 Safari/Firefox。fixture 没有证明这些层级，也没有关闭整个真实评估工作流验收。
