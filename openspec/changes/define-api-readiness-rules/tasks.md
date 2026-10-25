## 1. 就绪规则文档

- [x] 1.1 更新 `docs/api-monitoring.md`：明确三类能力的依赖、未检查语义及验收示例；逐项对照 design，运行 `git diff --check`。

## 2. 契约验证

- [ ] 2.1 运行 OpenSpec strict validate 与现有健康接口、部署契约测试，确认预留路径仍未实现且已发布行为不变；核查所有验收示例可得到唯一结论。
