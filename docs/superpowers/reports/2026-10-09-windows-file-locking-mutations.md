# 变异验证记录（windows-file-locking）

## M1 file_lock 解锁回锚移除（CRITICAL 回归样本）
- 结果：
============================= test session starts ==============================
platform darwin -- Python 3.14.3, pytest-9.1.1, pluggy-1.6.0
rootdir: /Users/Zhuanz/Desktop/LLM-Algorithm-Harness
configfile: pyproject.toml
plugins: anyio-4.12.1, mock-3.15.1, cov-7.1.0
collected 1 item

tests/test_windows_file_handles.py F                                     [100%]

=================================== FAILURES ===================================
_______________ test_msvcrt_branch_locks_and_unlocks_same_offset _______________
tests/test_windows_file_handles.py:271: in test_msvcrt_branch_locks_and_unlocks_same_offset
    assert calls == [
E   AssertionError: lock/unlock offsets drifted: [(1, 0, 1), (2, 20000, 1)]
E   assert [(1, 0, 1), (2, 20000, 1)] == [(1, 0, 1), (2, 0, 1)]
E     
E     At index 1 diff: (2, 20000, 1) != (2, 0, 1)
E     Use -v to get more diff
=========================== short test summary info ============================
FAILED tests/test_windows_file_handles.py::test_msvcrt_branch_locks_and_unlocks_same_offset
============================== 1 failed in 0.10s ===============================
- 恢复后：
============================= test session starts ==============================
platform darwin -- Python 3.14.3, pytest-9.1.1, pluggy-1.6.0
rootdir: /Users/Zhuanz/Desktop/LLM-Algorithm-Harness
configfile: pyproject.toml
plugins: anyio-4.12.1, mock-3.15.1, cov-7.1.0
collected 1 item

tests/test_windows_file_handles.py .                                     [100%]

============================== 1 passed in 0.05s ===============================
## M2 executor 悬空 NTF 复原
- 结果：
============================= test session starts ==============================
platform darwin -- Python 3.14.3, pytest-9.1.1, pluggy-1.6.0
rootdir: /Users/Zhuanz/Desktop/LLM-Algorithm-Harness
configfile: pyproject.toml
plugins: anyio-4.12.1, mock-3.15.1, cov-7.1.0
collected 1 item

tests/test_windows_file_handles.py F                                     [100%]

=================================== FAILURES ===================================
_____________________ test_src_temp_handles_in_with_blocks _____________________
tests/test_windows_file_handles.py:132: in test_src_temp_handles_in_with_blocks
    assert not violations, "dangling temp-file handles in src/:\n" + "\n".join(violations)
E   AssertionError: dangling temp-file handles in src/:
E     /Users/Zhuanz/Desktop/LLM-Algorithm-Harness/src/benchmark/executor.py:95 NamedTemporaryFile() outside with-block
E   assert not ['/Users/Zhuanz/Desktop/LLM-Algorithm-Harness/src/benchmark/executor.py:95 NamedTemporaryFile() outside with-block']
=========================== short test summary info ============================
FAILED tests/test_windows_file_handles.py::test_src_temp_handles_in_with_blocks
============================== 1 failed in 0.21s ===============================
- 恢复后：
============================= test session starts ==============================
platform darwin -- Python 3.14.3, pytest-9.1.1, pluggy-1.6.0
rootdir: /Users/Zhuanz/Desktop/LLM-Algorithm-Harness
configfile: pyproject.toml
plugins: anyio-4.12.1, mock-3.15.1, cov-7.1.0
collected 1 item

tests/test_windows_file_handles.py .                                     [100%]

============================== 1 passed in 0.19s ===============================
## M3 history.py 重新引入 import fcntl（首次变异无效：插入点落在 docstring 内部，属文本非导入；见下方修正条目）
- 结果：
============================= test session starts ==============================
platform darwin -- Python 3.14.3, pytest-9.1.1, pluggy-1.6.0
rootdir: /Users/Zhuanz/Desktop/LLM-Algorithm-Harness
configfile: pyproject.toml
plugins: anyio-4.12.1, mock-3.15.1, cov-7.1.0
collected 1 item

tests/test_windows_file_handles.py .                                     [100%]

============================== 1 passed in 0.18s ===============================
- 恢复后（全套）：
============================= test session starts ==============================
platform darwin -- Python 3.14.3, pytest-9.1.1, pluggy-1.6.0
rootdir: /Users/Zhuanz/Desktop/LLM-Algorithm-Harness
configfile: pyproject.toml
plugins: anyio-4.12.1, mock-3.15.1, cov-7.1.0
collected 10 items

tests/test_windows_file_handles.py ..........                            [100%]

============================== 10 passed in 1.40s ==============================
## M3（修正）history.py 顶部重新引入 import fcntl
- 结果：
============================= test session starts ==============================
platform darwin -- Python 3.14.3, pytest-9.1.1, pluggy-1.6.0
rootdir: /Users/Zhuanz/Desktop/LLM-Algorithm-Harness
configfile: pyproject.toml
plugins: anyio-4.12.1, mock-3.15.1, cov-7.1.0
collected 1 item

tests/test_windows_file_handles.py F                                     [100%]

=================================== FAILURES ===================================
______________________ test_no_direct_fcntl_import_in_src ______________________
tests/test_windows_file_handles.py:218: in test_no_direct_fcntl_import_in_src
    assert "fcntl" not in imports, (
E   AssertionError: /Users/Zhuanz/Desktop/LLM-Algorithm-Harness/src/incremental/history.py:1 direct 'import fcntl' breaks Windows imports; use src.utils.file_lock.exclusive_lock instead
E   assert 'fcntl' not in ['fcntl']
=========================== short test summary info ============================
FAILED tests/test_windows_file_handles.py::test_no_direct_fcntl_import_in_src
============================== 1 failed in 0.16s ===============================
- 恢复后（全套）：
============================= test session starts ==============================
platform darwin -- Python 3.14.3, pytest-9.1.1, pluggy-1.6.0
rootdir: /Users/Zhuanz/Desktop/LLM-Algorithm-Harness
configfile: pyproject.toml
plugins: anyio-4.12.1, mock-3.15.1, cov-7.1.0
collected 10 items

tests/test_windows_file_handles.py ..........                            [100%]

============================== 10 passed in 1.27s ==============================
