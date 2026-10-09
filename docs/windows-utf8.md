# Windows UTF-8 编码约定（#136）

题库、报告、日志、临时代码文件以及测试夹具使用显式 UTF-8。二进制操作保留原始字节。Python 子进程标准流通过环境副本的 `PYTHONIOENCODING=utf-8` 与父进程解码匹配；这不会改动父进程环境或依赖 `PYTHONUTF8=1` 掩盖缺失的文件编码。

检查与独立验证：

```bash
python scripts/find_missing_encoding.py
python -m pytest tests/test_utf8_io.py -q --no-cov
```

扫描器检查项目源码、根 Python 脚本和测试中的直接文本调用，支持常见导入别名，并忽略明确二进制操作。它不替代类型检查，不分析任意字符串中的用户程序或第三方库内部 IO。Unicode 回归测试以 cp1252 模拟默认编码，覆盖报告/导入、文件日志、工具临时文件和子进程标准流。

CI 在完整测试套件前独立执行编码测试。主线 Windows 当前仍有 `fcntl` 收集阻塞，后续还需完成 #137 进程管理、#138 文件句柄/锁定、#139 路径差异；四项完成后再在 #118 移除 Windows `continue-on-error`。macOS 和 Ubuntu 的完整 CI 始终需要通过。
