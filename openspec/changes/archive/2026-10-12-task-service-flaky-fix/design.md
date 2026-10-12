# 设计说明：task-service-flaky-fix

## 决策

1. **并发峰值计数替代计时**：worker 内 `lock` 保护的递增计数器记录同时执行的 worker 数。ThreadPoolExecutor 一次性提交 4 个单元，真实并发实现下 `max_workers=4` 的峰值 ≥ 2 是确定性行为；若池退化串行（被测的缺陷形态），峰值恒为 1，断言稳定变红。
2. **sleep(0.05) 保留**：为慢机器上的调度留出重叠窗口，但不参与断言（计时不再决定结果）。
3. **保留行为校验**：两条 run 均断言 `record.state == "completed"` 且 4 个单元全部 success——比原计时断言更强。

## 非目标

- 不改 TaskService 实现
- 不处理其他测试的计时问题
