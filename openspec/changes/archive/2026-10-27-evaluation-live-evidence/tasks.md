## Tasks

- [x] 1. 只读盘点本机 API、数据库、Redis、Celery、Docker/sandbox、测试账号、provider key 和预算条件；不读取或记录凭证内容。 <!-- comet-task:d737ebaf-cc96-4e2e-8b15-d7fd03344ba4 -->
- [x] 2. 创建 `docs/frontend/EVALUATIONS_QA.md`，分开记录 fixture 与 live 步骤、当前未验证层级、安全边界和恢复步骤。 <!-- comet-task:ef3af62f-3c85-432c-bc26-45131ab191a5 -->

## 本轮真实联调补齐

- [x] 3. 准备隔离认证配置、测试账号/题目及真实 API/Redis/Celery/Docker；核对配置来源、模型价格与 US$0.10 累计预算，保留脱敏预检证据。
- [x] 4. 新增独立 live 脚本及必要的脱敏/预算守卫自检；实际完成浏览器登录→实际选项→单题单策略创建/启动→真实进度/结果，记录成本、ID、状态与截图；失败先调查，不用 fixture 补足。
- [x] 5. 更新 QA、报告与复现/清理步骤，执行相关测试/类型/lint/构建、证据脱敏和完整性校验、diff check 与独立审查；按原 PR 交付验收结果。
