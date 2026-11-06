## Context

主线 d944ea2 已用 `ExecutionResult.iterations` 计算摘要轮次。调试会话保存策略结果，轨迹由现有记录器查询和导出。

## Decisions

用真实调试 CLI 和 VanillaStrategy 覆盖成功、答错、查询和导出。固定模型与沙箱响应以复现可预测的结果。用真实的空迭代结果验证零轮分支，并让策略抛出异常以验证失败提示。先验证现有实现与验收条件的差距。
