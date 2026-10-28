## Why

结果详情目前只能查看表格和分页，用户无法下载该次运行的报告；后端已有 Markdown、HTML 和 CSV 即时报告接口。将下载入口接到现有认证客户端，可让用户获取当前运行的真实报告并看到明确的失败与部分结果提示。

## What Changes

- 在结果详情提供 Markdown、HTML 和 CSV 报告下载。
- 使用当前结果的 `run_id` 和已配置 API 地址，通过现有认证及会话刷新机制请求文件。
- 处理文件名、重复点击、服务/权限错误及浏览器下载资源释放。
- 说明运行中、失败、取消或不完整运行的报告可能只含部分记录，并提供中英文文案。

## Capabilities

### New Capabilities

- `frontend/result-reports`：从评估结果详情安全下载当前运行的即时报告。

### Modified Capabilities

无。

## Impact

- 影响 `frontend/src/pages/Results/ResultDetailPage.tsx`、评估客户端或相邻报告客户端及中英文资源。
- 复用 `GET /api/v1/reports/markdown/{run_id}`、`html/{run_id}` 和 `csv/{run_id}`；不改后端报告生成与所有权校验。
