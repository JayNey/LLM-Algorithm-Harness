## 1. 发布侧
- [x] 1.1 `api/progress.py`：频道命名 + `publish_progress`（best-effort，Redis 故障降级）+ ProgressStream 协议与 Redis 实现
- [x] 1.2 `src/tasks/evaluation.py` 接线：task.started / task.progress / problem.completed / 终态事件
## 2. 订阅侧
- [x] 2.1 `/api/v1/ws/progress` 端点：token 鉴权、subscribe/unsubscribe/ping 协议、owner 校验、快照回放、多频道监听与断开清理
- [x] 2.2 main.py 接线（ProgressStream 可注入）
## 3. 验证与交付
- [x] 3.1 测试：鉴权/越权订阅/快照回放/事件转发/退订/发布降级；全量套件 + 覆盖率 ≥ 90
- [x] 3.2 独立审查、文档（API.md WS 协议）与验证报告

## 交付门禁
提交并创建关联 #150 的 PR，检查远端 CI，并在验证报告中记录交付结果。
