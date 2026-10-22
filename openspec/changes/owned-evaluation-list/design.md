## 实现

从 main 1960983 的既有 EvaluationSession 取得 client 与 owner，新增泛型 useList(load, query, owner)；请求使用 AbortController，并以代际和 owner/query/loader/重试序号隔离结果。渲染时同步隐藏不属于当前输入的旧数据。

页面从 URL 读取规范化 status/limit/offset；状态变化清零 offset，超页按服务端 total 跳到最后有效页（空集回到 0）。错误不转换为空列表，加载和换页不继续显示旧任务。使用现有反馈组件和主题变量，表格可独立横向滚动。任务名称不伪造，详情链接使用 evaluation_id。

## 验证

先扩展 list fixture，记录 Mock 页面失败；增加查询单测及真实 React 生命周期测试，覆盖不遵守取消的旧 Promise、换 owner、卸载、重试。运行前端全量单测、lint/build/格式检查、list/create fixture，检查代表性截图并独立 Bugbot 审查。仅浏览器 fixture 和离线验证，无真实 LLM/Redis/Celery 联调；真实联调由 #232 跟踪。

## 流程

沿用用户既定增量 Tweak 和个人分支，从最新 origin/main 开始；单一 issue 范围、无架构升级，不重复要求确认。共享脚本仅扩展 list 场景，避免改变其他负责人负责的路由和客户端。
