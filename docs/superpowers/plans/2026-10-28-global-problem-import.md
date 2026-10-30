---
change: global-problem-import
design-doc: openspec/changes/global-problem-import/design.md
base-ref: 831e5fe624ecf54d36f4c88c952615725a97e380
archived-with: 2026-10-30-global-problem-import
---

<!-- comet-task-authority: openspec/changes/global-problem-import/tasks.md -->

# 实施计划：全局快速导入

## 1. 全局入口与 URL intent

### 1.1 建立 RED/GREEN 路由参数测试

<!-- comet-task-ref:080d9d3f-613f-45dc-9157-a741833f029b -->

- 先在 `frontend/src/problems/validation.test.ts` 覆盖从非题库页生成 `/problems?import=1`、从题库页保留 `source/limit/offset`、打开/关闭只改 `import`。
- RED：`node --experimental-strip-types --test src/problems/validation.test.ts`，确认新断言因 helper 尚不存在/行为不符而失败。
- GREEN：实现 URL helper 并让 Shell 的桌面侧栏和顶部操作通过同一个 `onImport` 导航；验证同一命令通过。
- 禁止在 URL 更新时丢失题库筛选或向其他页面保留不相关筛选。

### 1.2 接入移动导航

<!-- comet-task-ref:e1779722-3beb-4f7c-8e99-08f94e388f64 -->

- 将 `onImport` 接入移动抽屉和底部导航的语义化按钮，并使用短标签和中英文翻译。
- 使用上一项 RED/GREEN 覆盖的共用导航 helper；运行前端 lint、类型检查和生产构建。
- 浏览器核对桌面侧栏、顶部操作、移动抽屉和 320px 底栏均到达相同的真实导入入口；验证键盘焦点。
- 全仓确认 `MockActions` 没有其他使用者后，移除外壳中的 Mock modal 状态及组件。

## 2. 题库页面与导入防护

### 2.1 RED/GREEN 导入面板路由行为

<!-- comet-task-ref:dce011a0-3acd-48c2-83fc-6913adcd7522 -->

- 让 `/problems?import=1` 打开现有 `ImportPanel`，页面内按钮也更新同一参数，收起时只移除 `import`；当前题库路由内收起后保持面板挂载隐藏，保留活动 job 状态。
- 列表筛选和分页更新必须保留 `import=1`；按 URL 可直接打开和刷新恢复。
- RED/GREEN：使用 `frontend/src/problems/validation.test.ts` 覆盖参数保存和删除；检查 `frontend/src/pages/Problems/ProblemsPage.tsx` 调用真实 importer。

### 2.2 保持现有上传语义与双语界面

<!-- comet-task-ref:db648ea9-1027-44d0-9a88-6808186d8162 -->

- 保留小文件同步直导、大文件异步任务、append/overwrite 确认、进度和校验报告。
- 只新增移动入口所需的标签/可访问名称；在 `frontend/src/i18n/resources.test.ts` 和既有 problem client 测试中核对两种语言及导入契约。

### 2.3 RED/GREEN 防止重复导入

<!-- comet-task-ref:cab4e92a-d910-4cd9-a996-e036b06d6ccc -->

- RED：为“请求处理中或异步 job 非终态时不能再次提交”的纯状态判定写测试，运行 `node --experimental-strip-types --test src/problems/importSubmission.test.ts` 并确认新断言失败。
- GREEN：在 `ImportPanel` 使用同步提交锁；直导请求完成前以及异步 job 到达 completed/failed/cancelled 前都禁用再次开始，重复点击至多发一个请求/创建一个任务。
- 运行相同定向测试，并用一个快速双击场景核对实际按钮状态。

### 2.4 文件选择取消与会话切换

<!-- comet-task-ref:5f9c9013-6a7d-4b1a-a539-4763ea2fbaea -->

- 验证取消系统文件选择或在开始导入前收起面板不会触发 upload/direct-import 请求。
- 保持现有按 owner 重建的 `ProblemSessionProvider` 和 HTTP session-marker 校验；必要时在 `frontend/src/problems/client.test.ts` 增加迟到响应被拒绝的回归。
- 运行定向 problem client 与 `frontend/src/auth/http.test.ts` 会话隔离测试；确认旧响应不会更新新会话界面或以新用户重试。

## 3. 集成验收

### 3.1 前端质量门

<!-- comet-task-ref:9b1f205a-9934-415e-be5c-d9df76c0052f -->

- 执行 `npm --prefix frontend test`、`npm --prefix frontend run lint`、`npm --prefix frontend exec tsc -- -b`、`npm --prefix frontend run build`。
- 记录准确退出码和既有警告；新增失败须先定位根因再修复。

### 3.2 端到端与差异核对

<!-- comet-task-ref:8dda4ca3-a37f-46f4-a535-4c690f8b2d44 -->

- 在桌面和 320px 移动宽度核对侧栏、快速操作、底栏、键盘访问及真实导入面板。
- 核对文件选择取消、会话切换、快速重复点击、直接访问/刷新/关闭 URL 参数和既有筛选。
- 运行 `git diff --check` 和 OpenSpec strict validation；检查最终 diff 仅涉及本 change 范围。
