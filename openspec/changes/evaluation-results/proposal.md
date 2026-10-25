## Why
#226 的前置 #220/#224/#225 及补丁 #259 均已合入main，主线7d88dc0 CI全绿。结果页仍指向Mock，现有results/result客户端尚未接入真实页面。

## What Changes
- 接入当前用户结果列表、URL状态筛选与分页，以及基于evaluation ID的可直达/刷新详情。
- 展示接口的全量策略汇总和当前单题分页，准确显示百分率、秒、未知指标/未知成本。
- 复用同一进度观察器，让任务和当前结果页并行读取且周期不重叠，结果失败与任务失败独立。
- 新增results浏览器fixture与回归、公开验证报告；沿用个人分支、独立Bugbot审查和base=main的PR。

## Capabilities
### New Capabilities
- `frontend/evaluation-results`: 真实结果列表、详情与同周期观察。
### Modified Capabilities
无。React快照作向后兼容的可选字段扩展，以承载联合HTTP快照，观察器核心与时序契约保持不变。

## Impact
前端结果页面/路由、既有读取适配器、观察器类型及fixture。无新后端API、认证客户端、数据库schema或依赖。失败/部分结果更细语义由#227，入口/完整外观/真实联调由#228/#229/#232负责；本任务仍保证基本加载、失败重试与权限清理。
