## 实现
沿用 evaluation ID、既有 Cookie/CSRF 客户端与联合 loader。状态与结果存在性独立：pending/running 零记录 waiting，有记录 partial；paused/failed/cancelled 保留各自状态与记录数；completed 零记录 empty、少于预期 incomplete、达到预期 complete；未知或跨版本 unknown。请求错误用 resultError 独立表达，不当作 empty。

联合结果读取仍在一个观察周期中；终态分歧仅补读一次，仍分歧显示未确认并手动重试。task 或 result 403/404 均使整个快照失效，bootstrap/live 权限失效后不能从另一缓存复活。手动重试需要重新授权成功后才能恢复。任务原因只取详情 error_message。

ResultDetailPage 展示可用性、已记录/预期数、任务原因和独立请求错误，复用原有组件与外壳样式。

## 验证
先增加状态×存在性矩阵及权限/补读测试并记录 RED，再实现 GREEN。states 浏览器 fixture 覆盖矩阵、task403/result200、result403、task200/result503、终态收敛/持续分歧和手动重试。运行全量前端单测、lint、build、相关 results/progress fixture；记录 fixture 与真实 Redis/Celery/供应商/沙箱联调层级差异。
