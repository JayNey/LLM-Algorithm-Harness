# Proposal: Windows UTF-8 编码修复（#136）

## Why

临时 Python 文件、日志、测试报告读取和子进程文本解码仍依赖默认编码。Windows 的 cp1252/charmap 会让中文题目或报告读取失败；只指定父进程解码也不能保证 Python 子进程使用同一编码输出。

## What Changes

- 在源码、根报告脚本与测试夹具的直接文本 IO 声明 UTF-8，保留二进制操作。
- 明确子进程 UTF-8 解码，通过复制环境并设置 `PYTHONIOENCODING` 约定 Python 子进程输出；沙箱同时保持其原有最小环境。
- 添加 AST 编码扫描与跨平台回归测试，在六个平台/Python CI 组合中独立执行，避免 Windows 完整套件的 `fcntl` 收集失败挡住本项验证。

## Non-goals

- 不在本 issue 改进进程/文件锁定或 Windows 路径语义。
- Windows 测试的 `continue-on-error` 留待四个子 issue 完成后在 #118 移除。
