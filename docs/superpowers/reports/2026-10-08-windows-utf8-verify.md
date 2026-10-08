# Issue #136 UTF-8 编码修复验证

日期：2026-10-08（Asia/Shanghai）

基线：`main@3a21707`。最新主线 [CI 37620147403](https://github.com/JayNey/LLM-Algorithm-Harness/actions/runs/37620147403) 的 macOS/Ubuntu Python 3.11、3.12 测试通过；Windows 完整套件有 5 项收集错误，均指向 `fcntl` 模块缺失，尚未进入后续测试执行。

## 改动

- 修复静态扫描定位的 115 处隐式文本编码：源码与根报告脚本、临时代码、文件日志、子进程文本捕获、测试夹具和报告读取均显式声明 UTF-8。
- Python 工具与 CLI 测试使用环境副本指定 UTF-8 标准流，沙箱仅在已有受控环境/容器中加入标准流编码变量。父进程环境不被修改，二进制操作保留原样。
- 新增直接调用的 AST 扫描器和独立编码测试；CI 在完整套件之前验证编码边界，保留 Windows 临时 `continue-on-error`。

## 本地证据

- 编码扫描：`Implicit text encodings: 0`。
- 独立 UTF-8 回归：18 passed。以 cp1252 模拟默认文件编码，验证中文、Ω、emoji 的报告、导入、日志和临时代码文件；验证 Python 子进程标准流与父进程匹配。
- 完整离线套件，包含 CI 覆盖率检查：1120 passed、4 skipped，覆盖率 93.32%（使用 CI 的 `--cov` 命令口径）。
- Ruff 全仓、Black 全仓、mypy `src/`、OpenSpec 严格校验及差异空白检查：通过。

## 独立审查

使用 review-bugbot skill 审查 #136 的源码、环境副本、扫描器、测试及 CI 范围，未发现可执行问题。审查方复验 18 个编码回归测试、零遗漏扫描和差异检查通过；其远端 CI 尚未核验，最终 CI 结论需查 PR 检查。

首次真实 Windows 专项执行发现工具临时文件测试直接比较 LF 字节，而 Windows 文本写入使用 CRLF；已改成显式 UTF-8 文本读取并采用通用换行处理，保留 Unicode 内容断言，未修改生产文件换行策略。

## 验证范围

本项验证编码边界，Windows 全套仍需后续子 issue 修复 Unix 进程、文件锁定和路径行为。本地为 macOS；实际 Windows/Ubuntu 结果以本 PR 的 GitHub CI job 与独立编码步骤结论为准。四个子 issue 完成后再移除父 issue #118 的 Windows 容错。
