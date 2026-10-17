## 1. 结果读取与落库补齐

- [x] 1.1 单元结果写入 `metrics.iterations`；已有行的统计在字段缺失时按未知处理，不回填伪造值
- [x] 1.2 结果查询服务：按 owner 解析 evaluation id / run_id，分页列出结果，支持策略、难度、标签、状态过滤

## 2. 查询、统计与对比 API

- [x] 2.1 `GET /api/v1/results/{run_id}`、`GET /api/v1/results`、`GET /api/v1/results/problems/{problem_id}`
- [x] 2.2 成功率、token、迭代、耗时、失败模式统计端点，与详情聚合共用计算
- [x] 2.3 策略、模型、历史对比；A/B 对比复用现有结果服务

## 3. 可视化、失败分析与报告

- [x] 3.1 成功率、token、能力雷达、成本-准确率、学习曲线的 JSON 数据
- [x] 3.2 失败汇总、按标签弱项、失败案例列表；错误信息按现有归一化规则聚类
- [ ] 3.3 Markdown、CSV、HTML 与现有图表函数可生成的 PNG 导出

## 4. 验证

- [ ] 4.1 API 测试覆盖查询隔离、统计口径、空历史、未知成本和报告导出；不连接真实 LLM 或 Redis
- [ ] 4.2 更新 `API.md`，并记录与 CLI 聚合一致的检查结果
