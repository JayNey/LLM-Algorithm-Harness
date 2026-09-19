## 1. 安全导入器

- [x] 1.1 增加 LiveCodeBench 模型字段和安全 JSON/JSONL 解析
- [x] 1.2 实现版本、日期、难度、limit 过滤和摘要记录
- [x] 1.3 映射 public/private 测试、stdin/function 协议和不支持说明

## 2. CLI 与测试

- [x] 2.1 注册 `harness import --source livecodebench` 及筛选参数
- [x] 2.2 增加离线夹具，覆盖版本、混合协议、private JSON 和不安全序列化
- [x] 2.3 增加真实数据导入说明，不让 CI 依赖在线数据

## 3. 验证

- [x] 3.1 更新 README/importing 文档和上游许可说明
- [x] 3.2 运行全量测试、静态检查并完成代码审查
