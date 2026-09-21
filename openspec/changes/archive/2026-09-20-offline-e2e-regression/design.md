## Context

现有测试以单元/集成为主：`test_integration.py` 覆盖组件协作但不断言结果文件内容；负向输入（坏数据集/坏配置/空策略）散落且无统一断言；在线验证已有 `online` 标记机制但文档未定义。上游 #20 要求以行为验证（而非覆盖率数字）证明离线链路与负向场景。

## Goals / Non-Goals

**Goals:**

- 一条成功链路与一条失败链路的端到端测试，直接断言落盘结果文件的字段值。
- 负向场景（缺数据集/坏配置/空策略）全部以非零退出 + 明确错误结束，不写结果文件。
- 文档明确 offline（替身）与 online（真实凭证）的边界与运行方式。

**Non-Goals:**

- 不引入真实网络依赖到默认测试路径；不做 Web/GUI 回归（随关联功能后续补充）。
- 不以覆盖率数字为验收标准。

## Decisions

1. **替身注入点沿用既有架构缝隙。** 端到端测试通过 `patch("src.harness.LLMClient")` 注入固定响应替身（与既有集成测试一致），CLI 层以 in-process `main()` 驱动，保证覆盖到参数解析、运行、落盘的真实代码路径；不新造第二套注入机制。
2. **空策略从"静默空报告"收紧为"显式报错"。** `harness.run()` 在 `strategies` 为空时抛 `ValueError`，CLI 捕获后 exit 1——空运行被误读为成功是该 issue 点名的风险，行为收紧优先于兼容。
3. **断言以落盘文件为准。** 成功/失败链路均读取 `summary.json` 与 `<strategy>_results.json` 断言精确字段（solved 数、`failure_category`、token 汇总），而非内存返回值。
4. **在线跳过可见性用子进程断言。** 以 `pytest tests/test_online_verification.py` 子进程运行断言 `skipped` 出现，保证 CI 报告里跳过状态真实可见。

## Risks / Trade-offs

- [空策略报错可能影响隐式依赖空运行的调用方] → 检索确认无此用法；这是 issue 点名要求的行为收紧。
- [替身绑定 harness 注入点，未来注入方式变化需同步] → 注入点是上游既有测试惯例，变更时测试会显式失败提醒。
