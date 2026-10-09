# 变异验证记录（windows-process-management）

说明：以下为有效变异记录。首轮记录中曾夹带两次无效尝试（needle 未匹配、变异未施加就把未变异基线跑当"应红"证据），已剔除；M1 记录时的存活探针尚为 POSIX 专属 `os.kill(pid,0)`，审查 I-3 后两处 docker 测试探针已替换为跨平台 `_pid_alive()`，替换本身不改变 M1/M2 的守护点（terminate_tree 调用与完成条件）。

## M1 run_bounded finally 移除 terminate_tree

变异：`run_bounded` 的 finally 中删除 `terminate_tree(process)` 调用。
结果：`tests/test_sandbox_docker.py::test_timeout_terminates_the_entire_process_group` **FAILED**（`DID NOT RAISE ProcessLookupError`——孙进程存活，超时杀树失效）：

```
tests/test_sandbox_docker.py F                                           [100%]
_______________ test_timeout_terminates_the_entire_process_group _______________
E   Failed: DID NOT RAISE ProcessLookupError
============================== 1 failed in 10.40s ==============================
```

恢复后（全文件）：`54 passed, 2 skipped`（test_process_manager 8 + sandbox_executor 33 + sandbox_docker 9/2skipped）。

## M2 完成条件退化为仅 poll()

变异：主循环完成条件从 `process.poll() is not None and not any(pump_threads alive)` 退化为仅 `process.poll() is not None`。
结果：`tests/test_sandbox_docker.py::test_parent_exit_still_terminates_child_process_group` **FAILED**（leader 提前退出后循环立即放行，未等 deadline，孙进程残留路径未覆盖）：

```
____________ test_parent_exit_still_terminates_child_process_group _____________
E   Failed: DID NOT RAISE SandboxExecutionError
============================== 1 failed in 10.20s ==============================
```

恢复后（全文件）：`54 passed, 2 skipped`。
