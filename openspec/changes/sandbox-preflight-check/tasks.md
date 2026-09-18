## 1. 预检与分类

- [ ] 1.1 先增加预检失败即在模型调用前中止的测试，再实现 `SandboxExecutor.health_check()` 与 `_run_strategy` 预检
- [ ] 1.2 先增加用例级 `sandbox_error` 归类 `system_error` 的测试，再修复 `_derive_failure_category`
- [ ] 1.3 先增加 CLI 捕获预检错误的测试，再在 `main.py` 输出可行动提示并以 exit 1 退出

## 2. 验证

- [ ] 2.1 运行全量测试与 OpenSpec 严格校验，并以停用 Docker 的方式实测预检行为
