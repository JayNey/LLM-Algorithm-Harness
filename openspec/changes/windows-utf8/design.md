# Design: 显式文本编码边界

文件文本使用 `encoding="utf-8"`，二进制文件不添加编码。Python 源码临时文件和日志 FileHandler 同样明确编码。沙箱二进制捕获后的 decode/序列化 encode 显式声明 UTF-8，保持既有无效字节替换规则。

新增 `utf8_subprocess_env` 返回环境副本，仅设置 Python 标准流编码，不修改父进程环境，也不强制文件的默认 UTF-8 模式。代码质量工具和 CLI 测试配套使用父进程 `encoding="utf-8"`；沙箱在受控环境中单独加入该标准流变量，Docker 容器通过 `--env` 传入。

`scripts/find_missing_encoding.py` 静态检查直接 open、Path 文本方法、文本临时文件、日志文件和文本 subprocess 调用，识别导入别名并跳过明确二进制调用。它是直接调用的 AST 检查，不解析字符串中的任意用户代码或第三方内部实现；内部生成的包装代码另由回归测试验证。

测试通过将默认文本 open 模拟为 cp1252，确认报告、导入、日志、工具临时代码文件仍正确保存 Unicode。子进程验证保留 `PYTHONUTF8=0` 而仅覆盖标准流编码。CI 在完整套件前单独运行本项测试，让 Windows 的既有 `fcntl` 问题和编码验收结果分别可见。

最新主线 CI 的 macOS/Ubuntu 测试全部通过；Windows 完整套件被 `fcntl` 模块缺失中断，属于后续锁定兼容工作，不靠编码环境变量掩盖该问题。
