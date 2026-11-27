# Web Pareto 多实验与自定义预算

## Why

Issue #524 指出实验详情的 Pareto 页固定提交当前实验和空预算，无法使用已有 API 的多实验比较与预算推荐能力。成本优化输入已完成，本次补齐 Pareto 输入到真实分析结果的闭环。

## What Changes

- 默认仍自动分析当前实验，支持从当前用户可访问的实验分页列表中选择一个或多个实验。
- 支持输入以逗号或空白分隔的 USD 预算列表，保留 overall/formal 口径；预算数值不换算、不舍入、不在客户端去重。
- 去重实验 ID 后获取全部原始 comparison，再调用现有 `/pareto/analyze`；任一读取失败即终止本次分析。
- 展示前沿与各预算建议、服务端不兼容错误；输入变化、网络失败和迟到响应不得留下被误认为当前结果的旧数据，并提供重试。
- 补齐双语文案、客户端测试及使用小型固定数据的浏览器与真实分析接口验收。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `frontend/experiments-management`：新增多实验 Pareto 输入、预算传递和结果恢复要求。

## Impact

- 预计修改 7 个交付文件：实验详情页、客户端、客户端类型、客户端测试、中英文语言资源、新增 Pareto 浏览器验收脚本。分类为 implementation 与 tests；OpenSpec 和 Comet 工作流产物另计。
- 范围限定为已有 Pareto 页和现有分析接口的接入，不新增后端 API/schema，不更改算法、权限或报告导出。
- 7 个文件超过 tweak 的 6 文件提示阈值，仅因双语文案和验收脚本所需；在 Open 确认时明确请求继续 tweak 的文件数授权。
- 工作区：当前目录与 main 分支。执行配置：direct / direct / off（Runtime 的 tweak 预设），仍执行必要回归与规格验收。
- 来源：https://github.com/JayNey/LLM-Algorithm-Harness/issues/524
