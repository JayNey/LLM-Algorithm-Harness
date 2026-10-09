# Tasks: windows-file-locking

## 1. 跨平台锁与存量修复

- [x] 1.1 新增 `src/utils/file_lock.py`：`exclusive_lock(f)` 上下文管理器，fcntl → msvcrt（LK_NBLCK 锁首字节）→ no-op 降级链；验证：单测覆盖三分支（monkeypatch 模拟平台属性）
- [x] 1.2 `src/incremental/history.py`：删除 `import fcntl`，`save()` 改用 `exclusive_lock`，打开→锁→写→解锁→关闭次序与 3 次重试语义不变；验证：`python -c "import src.incremental.history"` 于无 fcntl 模拟下可导入，增量相关测试全绿
- [x] 1.3 `src/benchmark/executor.py`：悬空 NTF 改 `mkstemp` + `os.fdopen` with 块形态，写路径与 finally 清理逻辑不变；验证：benchmark 测试全绿 + 异常路径临时文件清理测试

## 2. 守护与行为测试

- [x] 2.1 AST 守护测试 `tests/test_windows_file_handles.py`：src/ 全部 NamedTemporaryFile/mkstemp 必须处于 with 块内（fdopen 包装形态计为合规），阳性/阴性对照用例；验证：pytest 该文件通过
- [x] 2.2 行为测试：锁互斥与释放、fcntl 缺失（monkeypatch）下导入与保存、save 锁失败重试 3 次抛 OSError、benchmark 异常路径清理；验证：pytest 通过 + 变异验证守护有效（红→绿）

## 3. 回归验证

- [x] 3.1 `black --check .` 与 `ruff check .` 全绿；验证：退出码 0
- [x] 3.2 `pytest -m "not online" -q` 全量通过且覆盖率 ≥ 90；另跑 issue 指定 `tests/test_importers.py`、`tests/test_debug_e2e.py` 与增量相关测试；验证：命令输出
