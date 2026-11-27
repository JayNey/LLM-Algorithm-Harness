# Web 实验高级配置

## Why

issue #526：Web 实验创建只提供策略名称、迭代和温度，以及互斥的单维预算，无法复现已有 CLI 实验配置。现有 API、StrategyConfig、ProblemLoader 和 ProblemBudget 已提供所需语义，应把这些配置接入表单并验证执行链路。

## What Changes

- 为每个策略提供可选 max_tokens、system_prompt 和受支持 custom_params；空配置保持现有默认及参数继承。
- 提供 difficulty、tags、problem_ids、limit 筛选；创建前、创建成功后及持久化详情展示选择范围，解释标签任一匹配、条件交集与最后截取 limit。
- 支持同时设置每题 calls、tokens、seconds 上限，沿用共享预算的执行与计量语义。
- 对输入提供可定位、可修正的错误；兼容缺失新增字段的旧草稿及旧任务响应。
- custom_params 仅开放策略已读取的安全参数，不提供服务器路径、base_url 或沙箱配置入口。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `frontend/experiments-management`：扩展创建表单、组合预算、筛选和配置回显。

## Impact

主要影响实验前端类型、校验、请求/响应转换、创建页和详情；补充前端测试、离线 Python 执行链路回归及本地浏览器验收材料。若发现 API 现有传递链路存在范围内遗漏，补齐并回归，不新增端点或调整共享预算语义。

预估涉及 10–14 个交付文件（实现、测试、国际化），单个 change 完成；不依赖付费模型、真实 Eval 或沙箱部署调整。
