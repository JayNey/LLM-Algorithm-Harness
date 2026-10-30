## 实现
后端从当前持久化关联校验 task_type/entity_id/user_id，暴露 async_task_id 和 can_pause/can_resume/can_update/can_delete。评估恢复须评估与当前任务均为 paused，沿用原 ID 续跑（与其他业务的 stop_confirmed 门槛区分）；预算只在 pending 更新，删除遵循现有状态。
客户端使用真实 AsyncTask ID 调用 pause/resume，PATCH 只发送有限非负预算，DELETE 接受 204。新动作不自动重试；统一通过观察器 runMutation 使旧 GET 失效，成功/失败后 GET 对账，删除成功导航列表并卸载观察器。动作按页面、client、owner 和 AbortSignal 隔离，防重复并抑制迟到结果。
沿用 Ant Design、现有响应式操作区与翻译体系；预算表单关联标签、删除确认可键盘取消。
## 验证
数据库投影矩阵、客户端 HTTP 合同、页面浏览器回归（路由/身份切换、错误、状态竞争）、真实本地 HTTP 流程。执行前端全套检查与后端相关回归。
