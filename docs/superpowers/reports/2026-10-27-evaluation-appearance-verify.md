# #229 外观与移动验收验证报告

日期：2026-10-27。PR：#282。Change：evaluation-appearance。结论：**PASS**。构建、浏览器验收及最终独立审查通过。

## 范围与基线

- 保留原作者两次提交；在原分支 `tweak/20261026/evaluation-appearance` 合并最新 `main`@`b8ff9fd`（包含前置 #278），合并提交 `52740cf`。
- 2026-10-27 只读确认前置 #222–#228 均为 CLOSED。
- 验收脚本及焦点修复源码：`ad7ea818395f6bedb23164ca541e07129e8c3fc6`。JSON 的 `source.head` 记录实际运行提交，`source.dirty` 如实记录当时的文档及工作流状态改动。
- 用户确认超过六文件提示阈值后仍继续单一 Tweak change；不引入新业务功能、API 或 delta spec。

## 验收范围

1. 统一 `verify-evaluations.mjs --scenario appearance` 调用独立矩阵；`all` 同样执行，矩阵失败会使统一命令退出非零。
2. 3 风格 × 2 主题 × 4 宽度共 24 组合，覆盖创建、任务列表/详情、结果列表/详情，无页面横向溢出；表格自身允许滚动。
3. 两页题目分别选择后切换风格及主题，保留两页选择、密钥/模型/策略/预算；实际前端发出的创建 payload 精确匹配受支持字段，创建与启动各一次。
4. 任务/结果列表可见筛选值、完整 URL 保留，切外观不增加列表请求；按钮与表格容器可由 Tab 到达。
5. 全宽度验证通知抽屉键盘打开、Esc 关闭、焦点返回。320/390/768px 验证移动菜单 Esc/焦点及创建入口；320/390px 验证底部导航键盘进入结果列表，768px 隐藏底栏不记作通过。
6. 四张代表性截图及每组检查的页面、风格/主题/宽度、请求记录、限制写入仓库公开产物。

## 失败调查与修复

- RED：统一 appearance 命令原先抛出 `Scenario appearance 尚未实现`，退出码 1、0 组检查；接入后原矩阵 120 组通过。
- 扩展检查的初次失败包含 Ant Design 内部标签容器选择错误；通过实际 DOM 确认选择器后修正，没有将该失败误判为业务字段丢失。
- 新的 Esc 检查发现通知/移动抽屉快速关闭时焦点停在 body。临时诊断副本记录 focus 调用栈，确认打开动画完成前关闭可能跳过 afterOpenChange 恢复路径。补充关闭状态转换时的焦点恢复，保留动画完成回调，并使用公开 `focusable.focusTriggerAfterClose=false` 关闭重复恢复。
- 过程中构建曾拒绝直接传入底层 Drawer 的 focusTriggerAfterClose 属性；已核对安装的 Ant Design 类型并改为公开 focusable 配置，后续构建通过。
- 同一原失败场景连续五轮 50 组检查通过。临时调试副本及调用栈不作为交付脚本，不提交到仓库。
- 不需要 workflow.css 改动；本次产品修复仅涉及必要的焦点恢复。

## 命令与结果

- `npm test`：退出码 0，257 passed / 0 failed。
- `npm run lint`：退出码 0，0 errors；BenchmarkDetailPage 的两条既有 hook 依赖 warning 保留。
- `npm run build`：退出码 0，保留既有大 chunk 提示。
- `node --check scripts/verify-evaluation-appearance.mjs`、`node --check scripts/verify-evaluations.mjs`：退出码 0。
- 受影响脚本和组件 `prettier --check`：退出码 0。
- `comet classic openspec -- validate evaluation-appearance --strict`：退出码 0；沿用 skip_specs，不改变已有 spec 行为。
- 完整统一 `all`（含外观矩阵）：退出码 0，143 组统一场景检查通过；其中独立矩阵退出码 0，24 组合、216 组外观检查通过，0 失败、0 未声明 API 请求。完整运行日志及统一报告位于 `/private/tmp/pr282-all.log` 和 `/private/tmp/pr282-all/all.json`；公开矩阵报告见下方链接。

浏览器命令从 frontend 运行，环境提供 Playwright 及 Chrome 路径，不新增依赖：

```bash
EVALUATION_BASE_URL=http://127.0.0.1:5189 \
EVALUATION_QA_DIR=/private/tmp/pr282-all \
EVALUATION_APPEARANCE_QA_DIR=<repo>/docs/frontend/assets/evaluations/appearance \
node scripts/verify-evaluations.mjs --scenario all
```

## 公开证据与视觉检查

[完整矩阵 JSON](../../frontend/assets/evaluations/appearance/appearance.json)。截图索引见 [QA](../../frontend/QA.md)。已逐张人工查看：创建 320px、任务列表 390px、任务详情 768px、结果详情 1440px。字段、按钮和页面结构可辨，未发现页面横向溢出或主题不可读；窄屏表格在自身容器内滚动。全页截图中的固定顶栏/底栏按 1000px 视口位置显示，不据此宣称真机体验。

## 最终独立审查

最终独立只读审查覆盖 `origin/main`@`b8ff9fd` 至源码 `ad7ea81` 的全量 diff，以及本轮 QA、JSON、四张 PNG 和报告；结论 **Ready to merge: Yes**，Critical 0、Important 0。

审查者独立核对 JSON 的 24 组合/216 组及统一 all 的 143 组检查，逐张查看四张 PNG，并运行脚本语法和 diff 空白检查。唯一 Minor 是 QA 对 all 输出目录的说明少了环境变量条件；已补充 `EVALUATION_QA_DIR` 条件、默认公开目录及 `EVALUATION_APPEARANCE_QA_DIR` 优先级。该修正仅涉及文档，无产品取舍，不再重复派发最终审查。

Comet 轻量验证六项：tasks 全部完成、改动与任务一致、构建通过、相关测试通过、未见新增密钥/危险操作、最终独立代码审查通过，均为 PASS。验证阶段再次运行 `npm test && npm run build`，退出码 0。本轮没有 delta spec，沿用 Tweak 精简设计；无未接受的范围偏差。

此结论为本轮独立代码审查，并不冒充 GitHub 上的人工批准或尚未执行的新提交 CI。

## 验证层级与限制

验证真实前端组件、路由、状态和 HTTP 客户端；登录身份及 HTTP 业务响应由 fixture 替换，通知为外壳本地示例。完成状态为前端检查 fixture，不代表真实评估成功。

未执行真实 Cookie/CSRF 与用户隔离、离线 HTTP 服务端、Redis/Celery、供应商、沙箱、真机、Safari/Firefox 或屏幕阅读器验证。上述真实联调由 #232 等后续任务跟踪；#229 的 fixture 验收不宣称覆盖这些层级。本报告不自动关闭 Issue，也不合并 PR。
