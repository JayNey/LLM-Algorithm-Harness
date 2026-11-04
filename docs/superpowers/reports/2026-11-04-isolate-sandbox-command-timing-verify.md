# #340 沙箱并发计时验证

结论：PASS。change：isolate-sandbox-command-timing。

## 完整性
2/2 tasks 完成。改动仅涉及 src/sandbox_executor.py 和 tests/test_sandbox_docker.py，其余为 Comet 产物。用户已明确选择独立分支，并在文件数提示后确认继续 tweak；没有新增公开 API、capability、schema 或跨层架构协调。
使用 skip_specs: true 修复既有行为，OpenSpec strict validate 通过。没有 delta spec；主 execution-protocol 的函数结果通道要求仍由相关回归覆盖。tweak 不要求完整 Superpowers Design Doc/plan，这两项不适用。

## 正确性与验收映射
- 调用级 _CommandTiming 从单次测试/内存分析传至命令层，实例不再保存最近命令耗时。
- finally 在清理前记录 perf_counter 耗时；成功、后端错误、解析错误、超时和输出限制均使用本次计时，尚未启动命令时以单调时钟回退。
- 原实现 RED：20 项确定性回归失败，A 在清理等待 B 后误读 6.0，返回 timeout；修复后 A=0.1，B=6.0，28 项 GREEN。
- 两种输入输出模式、命令失败、解析失败、输出限制、超时以及清理异常覆盖完成。
- Harness.run(use_task_service=True) 默认 max_workers=5 共享 runtime 的真实调度入口验证通过；命令运行器和时钟替换为确定性替身，未调用模型。
- 内存分析共享执行器的快任务保留有效采样，慢任务按自身命令预算拒绝。
- 真实 Docker 两种模式并发测试：快速任务在清理阶段等待慢任务结束，仍 passed 且耗时低于 5 秒；慢任务 timeout 且耗时超过 5 秒。

## 验证命令与结果
- python3 -m pytest tests/test_sandbox_executor.py tests/test_sandbox_docker.py tests/test_harness.py tests/test_code_quality/test_space_analyzer.py tests/test_deployment_config.py tests/test_task_service.py tests/test_offline_e2e.py --no-cov -q：204 passed, 8 skipped（32.36s）。8 项是未启用 Docker 的集成测试，已在下一项单独全量执行。
- RUN_DOCKER_TESTS=1 python3 -m pytest tests/test_sandbox_docker.py --no-cov -q：50 passed（26.81s）。
- verify 阶段再次运行确定性并发测试：28 passed。
- black --check、ruff check（两份改动 Python 文件）、mypy src/sandbox_executor.py、compileall -q src、git diff --check：通过。
- comet classic openspec -- validate isolate-sandbox-command-timing --strict：通过。

## 一致性与审查
实现与 design.md 的调用级数据传递、无全局锁、runner 输出契约保持一致。无 spec 漂移、无新增密钥或非隔离执行路径。review_mode: off 为 tweak 默认值，未派发自动代码审查；已人工检查最终 diff、参数传递、异常路径及测试同步超时保护。

CRITICAL：0；IMPORTANT：0；WARNING：0；SUGGESTION：0。
测试输出中的既有提示为 Pydantic Config 弃用、pytest 模型收集与 fixture 弃用；mypy 提示未使用 kombu 配置段，无新失败。
Comet 的 state scale 在 build 阶段曾返回 tweak build configuration is incomplete；doctor、build guard 均通过，进入 verify 后 scale 正常，采用 full 验证。没有修改 Runtime 或绕过 guard。

当前分支 comet/isolate-sandbox-command-timing。实现已提交 d093b70、9a42a2a；待提交内容仅为验证报告及本 change 的 Comet 状态。用户于 2026-11-04 选择 C：确认归档、推送绑定分支并创建 PR；归档提交包含此报告与 Comet 状态。
