## 实施方式

单独新增 `frontend/scripts/verify-evaluation-appearance.mjs`，复用现有前端页面、登录 fixture 约定和 Playwright 运行环境，不改动 #228 正在修改的共享浏览器脚本。浏览器实际加载 React、路由、外观 store 和页面组件；身份、HTTP 业务响应由确定性 fixture 提供。

每个风格、主题、视口组合都覆盖创建、任务列表、任务详情、结果列表和结果详情。列表用 URL 筛选作为稳定状态，创建页填写表单草稿；切换风格/主题后确认 URL、筛选值和草稿仍在。检查根页面没有横向溢出，并验证可滚动表格容器及主要操作可由键盘访问。报告记录实际运行的页面与组合、请求替换范围、断言、截图和设备限制。

浏览器截图仅保留有代表性的矩阵样例；全部 24 个组合均运行断言。若发现实际失败，先定位溢出或焦点问题，再只修改对应外观 CSS，并重跑受影响组合。

## 依赖边界

#228 已通过 #278 合并，本轮在同步最新 main 后补齐其集成验收。统一脚本的 appearance 和 all 委托独立矩阵脚本执行，并传递服务地址、输出目录及失败退出码；不重复维护矩阵实现。

题目 fixture 提供两页数据，检查跨页选题、密钥/模型/策略/预算在切换后保留并进入真实前端提交的 payload。列表检查完整 URL 和可见筛选值。窄屏检查导航抽屉的键盘入口、Esc 关闭/焦点恢复以及抽屉和底部导航的实际跳转。各页面、组合的检查结果和截图索引写入公开 JSON。

验收产物保存到 `docs/frontend/assets/evaluations/appearance/`，报告存于 `docs/superpowers/reports/`。真实浏览器供应商调用、后端、Redis/Celery、真机和 Safari/Firefox 不由该 fixture 证明；不引入产品能力或修改现有 spec 契约。

## Workflow Decision

用户明确指定在 PR #282 原分支工作，因此采用 isolation=current。2026-10-27 用户确认：虽然 JSON、截图、验收文档及工作流元数据使文件数超过 Tweak 提示阈值，仍继续单一 change 的 Tweak 流程；不引入新能力、API 或架构改动。

## 验收发现的必要修复

新增 Esc 场景复现快速关闭抽屉时动画回调可能未执行，焦点恢复遗漏。AppLayout 移动菜单和 NotificationCenter 在关闭状态变化时补充焦点恢复，保留 afterOpenChange 回调，并通过公开 focusable 配置关闭重复的默认恢复。连续五轮最小回归 50 组及完整矩阵 216 组检查通过；不涉及外观重设计。
