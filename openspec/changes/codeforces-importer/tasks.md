## 1. API 与转换

- [x] 1.1 接入公开 problemset API，增加 contest/rating/tag/limit 过滤和有界重试
- [x] 1.2 抓取题面、输入输出说明和公开样例，转换为标准 Problem schema
- [x] 1.3 实现 rating、标签、题号映射和交互题/缺失题面处理

## 2. CLI 与文档

- [x] 2.1 接入公共 import 命令，支持位置 source 与显式 `--source`
- [x] 2.2 更新导入指南和 README 示例

## 3. 验证

- [x] 3.1 增加过滤、转换、样例、错误和难度映射测试
- [x] 3.2 运行全量测试、OpenSpec 严格校验并完成代码审查
