## 1. 数据与查询
- [x] 1.1 迁移 0003：budgets/alert_rules/alert_events/pricing_overrides；ORM 与迁移一致
- [x] 1.2 cost 查询服务：任务成本跨表解析、汇总/趋势/分解聚合（时间段过滤）
- [x] 1.3 budgets：upsert/update/usage（全局 + 按难度比例估计，含口径标注）
## 2. 预警、定价与报告
- [x] 2.1 alerts：规则 CRUD + 触发历史；通道/阈值校验；响应脱敏
- [x] 2.2 pricing：目录读取（内置+文件+覆盖合并）、覆盖入库（追加版本）
- [x] 2.3 reports：任务成本报告 + cost-optimization（合成 comparison → build_advisory）
## 3. 验证与交付
- [x] 3.1 测试：四表 CRUD、聚合正确性、越界/跨用户拒绝、脱敏、空历史；全量套件 + 覆盖率 ≥ 90
- [ ] 3.2 独立审查、文档（API.md）与验证报告

## 交付门禁
提交并创建关联 #154 的 PR，检查远端 CI，并在验证报告中记录交付结果。
