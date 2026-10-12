## 1. 稳定化
- [x] 1.1 重写 `test_parallel_execution_with_different_max_workers`：峰值并发断言 + 完成态/结果校验，移除墙钟加速比
## 2. 验证与交付
- [ ] 2.1 目标测试多次重复运行稳定通过；ruff/black 全绿；离线全量套件通过且覆盖率 ≥ 90

## 交付门禁
提交并创建关联 PR（引用 #176/#144 的 flake 记录），检查远端 CI。
