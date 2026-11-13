# LeetCode 节点判题验证

变更 `fix-leetcode-node-judge` 对应 [GitHub #479](https://github.com/JayNey/LLM-Algorithm-Harness/issues/479)。实现任务 1/1 已完成。

- 105、106 使用固定正确解法验证层序输出、内部空位和空根。错误解法覆盖不匹配的树、环和直接返回数组。
- 133 验证有环图、单节点、空图和邻居重排，并拒绝错误根、缺边、原节点以及复用原邻居列表的克隆。
- 138 验证空链表、重复值、空指针、前后引用和自引用，并拒绝原节点、浅拷贝、next 环和错误 random 指针。
- CLI 与 Web 加载同一批旧记录，获得相同判题配置和题目指纹。重新导入带 `ListNode` 签名的题目会记录明确原因，执行器返回 `unsupported`。
- 节点构造与结果转换都位于共享的隔离 runner 内，沿用现有结果标记。现有普通函数及 stdin/stdout 的沙箱回归也已执行。

## 执行证据

- `RUN_DOCKER_TESTS=1 pytest -o addopts= -q tests/test_sandbox_docker.py`：68 项通过。
- LeetCode 导入、导入生命周期、批量导入及 Host 执行套件：95 项通过，1 项跳过。
- Web 文件导入、增量指纹、Harness 和题库加载套件：147 项通过。
- Python wheel 构建成功，包内含节点 runner。改动 Python 文件的 Black、Ruff 及 `git diff --check` 通过。
- `comet classic openspec -- validate fix-leetcode-node-judge --strict` 通过，五个规格场景均有实现及回归对应。
- 对改动做了本地差异审查。当前 Comet 的 `review_mode` 为 `off`，因此没有独立自动审查。
- 全仓 mypy 在基线与本分支均报告相同的 4 个既有错误，位于 API 的文件解析、进度和成本告警模块。
- 沙箱内的全仓 pytest 遇到本机回环端口绑定限制。受影响的定价 API 用例在允许绑定后重跑，7 项通过。
