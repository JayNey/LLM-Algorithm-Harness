# Tasks: windows-process-management

## 1. 跨平台进程管理模块

- [x] 1.1 新增 `src/utils/process_manager.py`：`spawn()`（POSIX start_new_session / Windows Job Object 分配，失败降级+warning）、`terminate_tree()`（killpg / TerminateJobObject，幂等）、`run_bounded()`（线程泵输出 + 合并限幅 + stdin 线程喂入 + deadline 轮询），自有 `ProcessTimeoutError`/`OutputLimitExceededError`；验证：模块单测通过
- [x] 1.2 `src/sandbox_executor.py`：`_run_command` 改为 `run_bounded` 薄封装（异常映射为 SandboxExecutionError("timeout"/"output_limit")，cleanup 回调保持），finally 无条件 `terminate_tree`；清理不再使用的 selectors/signal 导入；验证：tests/test_sandbox_executor.py、tests/test_sandbox_docker.py 全绿

## 2. 测试

- [x] 2.1 新增 `tests/test_process_manager.py`：超时抛 ProcessTimeoutError 且树终止（孙进程模式）、输出超限抛 OutputLimitExceeded 且保留部分输出、stdin 喂入与断管容忍、terminate_tree 幂等、正常路径返回码与输出完整性；验证：pytest 通过（全平台，无 skipif）
- [x] 2.2 既有进程组测试转全平台（超时杀树 / 父退出杀树两条，不添加 skipif），三向变异验证守护有效（移除 terminate_tree 调用→红；恢复→绿）；验证：红→绿观察记录
- [x] 2.3 30 个 Windows 已知失败用例的 Unix 侧回归确认（sandbox_executor/sandbox_docker/experiment/offline_e2e 等）；验证：相关文件 pytest 全绿

## 3. 回归验证

- [x] 3.1 `black --check .` 与 `ruff check .` 全绿；验证：退出码 0
- [x] 3.2 `pytest -m "not online" -q` 全量通过且覆盖率 ≥ 90；issue 指定 `pytest tests/test_sandbox_executor.py -v`；验证：命令输出
