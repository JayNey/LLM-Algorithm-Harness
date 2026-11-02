## 修复方案

从 `progress.task?.status ?? run?.status` 派生选中运行当前状态，统一用于状态标签和暂停提示。关联任务已经过 id/entity/type 校验，观察器按账号与任务隔离，因此不引入另一套状态缓存。终态仍由现有 effect 对账运行详情、历史和学习曲线。

## 验证

在现有真实页面 + HTTP fixture 脚本中，为同一运行先返回 pending，然后只改变后台任务/运行状态，等待自动轮询验证 running、paused。paused 后手动恢复观察并继续验证自然 completed、结果/历史/曲线重取及轮询停止。实现前运行新增测试取得 RED；修复后复跑整个脚本、前端全量测试、lint 和构建。
