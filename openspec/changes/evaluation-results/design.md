## 实现
- results列表复用useList、readListQuery/writeListQuery及现有Cookie/CSRF客户端；列表id始终作为evaluation ID导航，run_id=null可用。
- ResultDetailPage读取evaluation ID和URL limit/offset。联合loader通过Promise.allSettled并发读取task和当前result页；task失败抛给观察器，result失败以独立resultError随成功task交付，401/429仍交给既有观察器会话恢复/限流处理。无额外结果轮询器。
- useEvaluation/useEvaluationLive接受稳定的自定义loader；快照身份含client/loader/owner/id，阻止路由、分页、会话和迟到请求串用。React快照类型使用可选的result/resultError扩展字段，观察器核心保持不变。
- bootstrap完成后启动同一观察器，WS只触发联合HTTP失效，终态/paused停止自动观察；手动刷新走当前观察器，未挂载时走bootstrap。
- 策略统计直接用result.strategies，不按当前problems.items重算；单题键为JSON编码的[problem_id,strategy]；null用未知，耗时用秒，success_rate×100。unknown_cost_count非零时明确已知部分/未知条数，不把缺失成本写成免费。
- 保留外壳和主题，复用现有横向表格容器与分页样式；不把可滚动表格变成根页面横向溢出。

## 验证
先补fixture并在Mock基线记录results RED，再实现。覆盖列表status/分页/URL、run_id=null直达刷新、跨页全量汇总、同题多策略、未知字段、错误/重试/权限/旧响应隔离及事件合并下任务+结果单周期。单测覆盖联合loader与表现规则；全量前端工程检查、已有detail/progress/create/list回归和独立Bugbot。HTTP/WS全部fixture，不宣称真实后端/供应商/沙箱端到端。
