## 1. 严格函数结果通道

- [x] 1.1 编写并观察解析器及 Host 提前退出回归失败，实施显式 marker 严格校验，保留 legacy 与 stdin/stdout。
- [x] 1.2 更新既有 Docker 成功 mocks，补充 Docker 缺失结果通道和真实容器回归，验证正常返回及调试 stdout。
- [x] 1.3 运行相关及全套测试、静态检查和构建，记录真实 Docker 验证及环境限制。
