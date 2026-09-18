## 1. 模型与导入器

- [x] 1.1 增加人工补全状态和说明字段，保持旧题库兼容
- [x] 1.2 实现 LeetCode URL/slug 解析、GraphQL 请求、重试和错误分类
- [x] 1.3 实现 HTML 清洗、元数据/签名提取和保守样例解析

## 2. CLI 与测试

- [x] 2.1 注册 `harness import --source leetcode`，接入预览、去重和报告
- [x] 2.2 增加至少五种离线响应夹具并覆盖部分失败/人工补全
- [x] 2.3 增加可选在线验证说明，不让 CI 依赖实时 LeetCode

## 3. 文档与验证

- [x] 3.1 更新 README 和 importing 文档，明确 public-only 和限制边界
- [x] 3.2 运行全量测试、静态检查、OpenSpec 校验并完成独立代码审查
