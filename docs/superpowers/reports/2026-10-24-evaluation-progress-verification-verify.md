# #225 进度补验收与详情接线修复

日期：2026-10-24（Asia/Shanghai）。受测 main 基线 `d0f275c4092a2b4c12a91e55c836a9bc80710d14`；应用修复和公开浏览器证据源码 `bd082ff369e4c050676170cb2219efa26b7b8353`（开始验证时工作树干净）。change：`evaluation-progress-verification`，Tweak，个人分支，PR base=main。

## 前置状态

用户授权按此前结论继续：先处理 Windows SQLite 回归、补 #225 浏览器验收，再判断 #226。实际拉取最新 main 后，#255/#250/#257/#256 均已合并；#255 已删除普通 MonitorStore 写入的100ms短锁等待，SDK sink仍自行限制预算。本轮不重复修改后端。main CI [40062521868](https://github.com/JayNey/LLM-Algorithm-Harness/actions/runs/40062521868) 的10项检查全部成功，包含六个OS/Python组合。

#225 已关闭，#256 已合并，但实际执行其 progress fixture 超时；随后 detail HTTP403 与 progress WS4403 均暴露真实页面仍显示旧数据。因此 #226 需要本补丁合入 main 后再开始，不能仅按 issue CLOSED 判断前置可用。#226 没有在本分支提前实现。

## 复现与修复

- 原 progress fixture 对 `connectToServer()` 返回对象调用 onMessage/send，方向指向真实上游，页面未收到模拟订阅确认，等待“实时进度已连接”30秒超时。改为在原 WebSocketRoute 上接收浏览器消息、发送模拟响应，不建立上游连接；所有评估 fixture 都拦截WS。方向依据 [Playwright WebSocketRoute 官方文档](https://playwright.dev/docs/api/class-websocketroute)。
- 原 check 助手把同步断言也推入微任务，未 await 的调用无法即时触发场景 catch。助手提取为 `fixture-checks.mjs`，同步立即执行/抛错，异步返回可等待Promise；单测先2失败/2通过，再4通过。报告末尾再确认全部检查通过。
- 真实 React 接线在HTTP403后仍优先展示旧live快照，WS4403也未处理 forbidden。适配器现在处理 forbidden/error/unauthorized，禁用时不返回旧快照和连接模式；页面不回退已拒绝的bootstrap数据，动作入口撤下。HTTP503保留旧数据并禁操作，显式刷新成功后恢复。
- 活动页面刷新使用同一观察器；启动/取消经 runMutation 纪元协调，避免旧请求覆盖动作后的HTTP真值。尚未观察及终态仍用一次性读取。保留现有Cookie/CSRF客户端、观察器核心和服务端能力字段。
- 进度证据先等待初始snapshot对账完成：HTTP20%，WS仅发送50%的失效事件，之后确有新HTTP返回60%，页面显示60%。没有把首次在途HTTP误当事件后的新请求。

## 实际验证

下列命令均退出0，RED步骤除外：

- 根目录 `.venv/bin/python -m pytest tests/test_api_monitoring_store.py -k 'concurrent_writers or contended_write' --no-cov -q`：2 passed、43 deselected。
- frontend `npm test`：214 passed、0 failed，含新增助手4例及既有观察器时序、权限、dispose、动作纪元测试。
- `npm run lint`：0错误，保留未改动 BenchmarkDetailPage.tsx 的2条既有runFinished依赖警告。
- `npm run format:check`：通过。`npm run build`：类型检查/构建通过，保留既有大于500kB的chunk提示。
- `node scripts/verify-evaluations.mjs --scenario all`：90组通过。独立 detail 26、progress 7、create 38、list 22 组也执行通过；这些分组数包含部分共享断言，不能相加当all总数。
- OpenSpec strict、git diff --check：通过。Runtime build/verify的正式记录在交付段补充。

[公开 JSON](../../frontend/assets/evaluations/progress-verification/all.json) 含源提交、所有断言、HTTP请求、真实/替换组件、截图及事件因果记录。第一阶段HTTP值为20/20/20/60，事件前已完成3次读取，60%来自事件后的新请求；拒绝后恢复阶段HTTP依次60/60/60/80，最终80%同样来自后续事件的新请求。socket_paths在首阶段取值，重连由独立恢复断言核对。人工另检查 [权限拒绝截图](../../frontend/assets/evaluations/progress-verification/progress-denied.png)，旧详情和动作入口均已撤下；人工检查 [progress桌面](../../frontend/assets/evaluations/progress-verification/progress.png)、[Orbit深色320px](../../frontend/assets/evaluations/progress-verification/detail-orbit-dark-320.png)、[Studio浅色1440px](../../frontend/assets/evaluations/progress-verification/detail-studio-light-1440.png)：关键信息与动作可见，无根页面横向溢出；手机长页保留固定导航及页面滚动。其余截图由脚本保存，不宣称逐张人工检查。

复现：frontend先`npm ci`，启动`npm run dev -- --host 127.0.0.1 --port 5180`，另终端设置可解析的外部`PLAYWRIGHT_MODULE`后执行上述脚本。可用`EVALUATION_BASE_URL`覆盖地址、`EVALUATION_QA_DIR`覆盖输出。仓库不因此增加Playwright依赖。

## 规格完整性、正确性与一致性

修改1项既有requirement“终态、权限与会话生命周期”，包含5个场景。前三个核心场景分别由observer.test.ts中4403/HTTP403/404、runMutation旧请求作废、dispose后无回调覆盖；新增React权限清理由detail HTTP403与progress WS4403浏览器覆盖，页面动作/刷新由detail成功、失败、取消冲突与刷新恢复浏览器覆盖。状态与页面使用既有observer能力，无新协议/认证客户端。设计与实现一致。最终任务完成及独立审查结论见交付段。

## 验证边界

这是前端单测、工程检查与Chromium HTTP/WS fixture。真实React StrictMode、路由、会话provider、创建store、HTTP客户端、进度观察器参与；HTTP身份/任务响应、WS及session marker由fixture提供。未验证真实Redis/Celery、提供商、沙箱、真实登录端到端、Safari/Firefox或真机。构造的进度值用于检验HTTP优先，不代表实际任务进度一致性。既有外壳Mock标记由#228处理，全流程外观与真实联调分别由#229/#232跟踪。

## 交付

独立Bugbot首轮发现1项P2：权限拒绝后手动重试未恢复自动订阅。新增浏览器回归先RED（等待实时连接5秒超时），修复后progress 7组、detail 26组通过。适配器只在成功HTTP返回pending/running后重启，paused/终态不重启。复审无剩余问题，审查者另执行观察器和助手29项测试全部通过。最终公开all复测90组通过（干净源码bd082ff）。[PR #259](https://github.com/JayNey/LLM-Algorithm-Harness/pull/259) 已创建，base=main，Refs #225。4/4任务完成，1/1 requirement及5/5场景已核对，无未完成实现或剩余审查问题。正式Runtime已实际执行 `npm --prefix frontend run build`（日志ID bfea3937-4055-4895-bd5a-82a143292f12）和 `npm --prefix frontend test`（日志ID 2fd5bd67-3562-40cf-b493-45d81f26c0dd，214/214通过）；输入前后指纹一致，build守卫14/14、verify守卫5/5通过，verify_mode=full、verify_result=pass。规模评估建议full，与实际模式一致。phase=archive，归档确认pending，未自动同步主规格或移动change。Runtime的review_mode=off不用于跳过本轮审查：用户既定流程要求的独立Bugbot已覆盖最终实现，结果见上。未另建技术Design Doc，局部设计位于change/design.md；该额外文档检查不适用。

PR CI只自动执行仓库后端工作流，前端fixture与工程检查由上述独立证据证明。PR最新头的CI以GitHub当前检查为准，不把main或旧头通过当作最新头通过。未自动合并或关闭其他任务；本轮作者提交排除.comet/.claude/.codex/.agents/skills-lock.json。
