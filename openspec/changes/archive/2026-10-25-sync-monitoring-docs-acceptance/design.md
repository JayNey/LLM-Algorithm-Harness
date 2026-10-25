## 实现说明
以当前分支 e700646 为代码基线核对监控路由、采集实现、既有报告与部署编排。修改 OpenAPI 注释及示例以反映已有能力，不更新 tests/fixtures/openapi-v1.json 冻结兼容基线。文档区分 API 存活、数据库就绪、管理员诊断与真实 worker 执行环境。

本次使用现有测试验证接口说明及边界，记录精确命令、结果、跳过原因；真实 Docker、Redis/Celery、PostgreSQL 和供应商环境未执行则明确标注未验收。issue 追加带基线与日期的评论，保留历史原文且不关闭 issue。
