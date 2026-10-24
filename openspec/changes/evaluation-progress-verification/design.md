## 根因与方案

当前 main 已移除通用 MonitorStore.record_llm_call 的100ms超短锁等待，SDK采集sink自行保留短预算；本轮两个锁竞争测试通过，不重复修改后端。

progress fixture 错把 connectToServer 返回的 server 端当成模拟服务器：onMessage 监听真实服务器消息，send 也发给真实服务器。纯 fixture 应在原始 ws 上接收浏览器订阅和向页面发送 snapshot/subscribed/progress，不连接真实后端。验证HTTP真值在事件后由20%到60%，不把WS载荷中的50%直接当最终状态。

断言助手提取为脚本模块，保留同步断言即时抛错，异步断言返回可 await Promise。单测证明同步/异步失败可到达场景 catch，记录不会提前变绿。各场景最后核对全部断言通过再设置 report.pass=true。

## 验证与边界

记录 main 原始 progress 失败；执行助手 RED/GREEN、前端全量单测/lint/format/build及实际 Chromium progress/detail/create/list。fixture 替换HTTP与WebSocket，验证应用前端接线而非后端成功。报告保留源提交、命令退出码、截图及替换依赖；实际提供商、broker、worker、沙箱与真机均不外推。

沿用用户既定 Tweak 与个人分支，独立 Bugbot 审查后创建 base=main 的 PR；不自动合并，不因旧CI结果宣称当前头全绿。

## 浏览器回归补充

实际 detail 场景在加载后刷新403时仍显示 model-a：一次性读取已清空但 useEvaluationLive 返回旧快照，页面优先取live；适配器也未处理核心 forbidden/error 事件。修复React返回值的启用/权限门控并在拒绝时不回退旧bootstrap；活动页面手动刷新走同一观察器，启动/取消走runMutation纪元，保留现有协调器及终态/非活动一次性读取。补HTTP403和WS4403实际浏览器断言。

独立审查发现权限拒绝后的显式刷新只能恢复快照、不会恢复订阅。React适配器仅在成功HTTP返回pending/running且通道stopped、未拒绝/未失效时重新start；paused/终态仍停止。浏览器先复现重试无连接，再验证HTTP403重试重新订阅及WS4403重试后的新事件驱动80%真值。
