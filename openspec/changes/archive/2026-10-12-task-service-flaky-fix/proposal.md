## Why

`tests/test_task_service.py::test_parallel_execution_with_different_max_workers` 用墙钟加速比（parallel < serial/1.5）断言并发性，在负载波动的 CI runner 上反复假红：已连续阻塞 PR #176 的 Windows py3.12 job（2026-10-12 三次），此前 PR #144 的 Windows job 也因同一测试失败（当时已留言建议单独修复）。

## What Changes

- 用确定性的并发观测替代墙钟断言：worker 内以线程安全计数器记录峰值并发，`max_workers=1` 断言峰值并发 == 1，`max_workers=4` 断言峰值并发 ≥ 2（即单元真实并行分发）；两条 run 均断言全部单元成功完成。
- 不修改 `src/task_service.py`（被测实现无缺陷）。

## Capabilities

### New Capabilities
无（纯测试稳定性修复，不改变系统能力）。

### Modified Capabilities
无。

## Impact

仅 `tests/test_task_service.py` 一个测试文件；消除 CI 假红，加快团队合入节奏。
