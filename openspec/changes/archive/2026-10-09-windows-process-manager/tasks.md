## 1. 创建跨平台进程管理抽象层

- [x] 1.1 创建 `src/utils/process_manager.py` 模块骨架，包含 `ManagedProcess` 类定义，验证模块可在 Unix 和 Windows 上成功导入
- [x] 1.2 实现 Unix 进程组管理路径（`start_new_session=True` + `os.killpg`），验证现有 Unix 测试通过
- [x] 1.3 实现 Windows Job Objects 路径（通过 `ctypes` 调用 `CreateJobObjectW`, `AssignProcessToJobObject`, `CloseHandle`），验证 Windows 平台进程树终止成功
- [x] 1.4 实现 `ManagedProcess.__enter__` 和 `__exit__` 上下文管理器协议，验证异常路径下进程树被正确终止
- [x] 1.5 添加 Windows Job Objects 创建失败时的 fallback 逻辑（降级到 `process.kill()` 并记录 warning），验证降级分支可触达且不中断执行

## 2. 重构 sandbox_executor.py 使用统一接口

- [x] 2.1 在 `sandbox_executor.py` 中导入 `ManagedProcess`，验证无导入错误
- [x] 2.2 重构 `_run_with_output_limit` 中的 `subprocess.Popen` 调用改用 `ManagedProcess` 上下文管理器，保持 `start_new_session` 逻辑移到 `ManagedProcess` 内部，验证现有测试通过
- [x] 2.3 删除 `_terminate_process_group` 方法及其调用点（终止逻辑已由 `ManagedProcess.__exit__` 处理），验证 `grep -r "_terminate_process_group" src/` 无结果

## 3. 测试覆盖

- [x] 3.1 为 `src/utils/process_manager.py` 添加 Unix 专属单元测试（进程组终止验证），使用 `@pytest.mark.skipif(sys.platform == "win32", reason="Unix-specific")` 标记，验证测试在 Unix 上通过且 Windows 上被跳过
- [x] 3.2 为 `src/utils/process_manager.py` 添加 Windows 专属单元测试（Job Objects 终止验证、子进程树清理验证），使用 `@pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific")` 标记，验证测试在 Windows 上通过且 Unix 上被跳过
- [x] 3.3 添加跨平台集成测试验证 `ManagedProcess` 在超时场景下终止子进程树，验证 Unix 和 Windows 上均通过
- [x] 3.4 运行完整测试套件 `pytest tests/test_sandbox_executor.py -v`，验证所有现有测试通过且无回归

## 4. 验证与清理

- [x] 4.1 在 Windows 环境运行 `pytest tests/ -v -k "sandbox or process"` 验证所有沙箱和进程管理相关测试通过
- [x] 4.2 在 Unix 环境运行相同测试验证无回归
- [x] 4.3 检查代码中不再存在 `os.killpg` 或 `start_new_session` 的平台条件分支（除 `process_manager.py` 内部），验证 `grep -r "os.name.*nt.*killpg\|start_new_session.*os.name" src/sandbox_executor.py` 无结果
