## 1. 变体与实验设计

- [x] 1.1 支持两个 prompt 变体、baseline 标识和 prompt 覆盖
- [x] 1.2 实现固定 seed 的难度/标签分层均衡分配

## 2. 统计与报告

- [x] 2.1 计算样例/正式通过率差异和 95% 置信区间
- [x] 2.2 支持 Fisher/卡方、Welch t 检验、Token/耗时和标签/难度统计
- [x] 2.3 输出 JSON、CSV、Markdown 和 prompt 优化建议

## 3. 入口与验证

- [x] 3.1 提供 `harness ab-test --config` 和示例配置
- [x] 3.2 增加固定夹具、均衡性和统计手算验证
- [x] 3.3 全量回归、OpenSpec 严格校验和最终代码审查
