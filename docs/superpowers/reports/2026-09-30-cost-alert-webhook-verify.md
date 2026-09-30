# Issue #86 成本预警与 Webhook 通知验证报告

日期：2026-09-30

## 实现核对

- 运行级已知成本达到默认 50%、80%、90% 或自定义阈值时，逐个触发预警；未知定价或 usage 单独计数，不当作零成本。
- 支持 Slack Incoming Webhook、通用 HTTPS JSON Webhook 和 SMTP；失败按暂时/永久错误分类，在限定超时和次数内重试。成功渠道与失败类别写入独立、原子落盘的预警状态文件，恢复后不重发已确认成功的渠道。
- `--auto-stop-on-budget` 在题目边界暂停剩余排队单元，并生成 `cost_cutoff.json`；保留选择器模式的默认降级及显式 `--downgrade-on-budget`。
- 暂停后的聚合报告只计算已执行单元；详细结果中的未运行题目以 `cancelled` 占位，`summary.json.cost_control.incomplete` 标识截断结果。

## 验证

- 定向测试（通知、成本策略、任务服务、CLI、脱敏）：**125 passed**。
- 排除已确认的两项缺失工具测试与旧的 LLM 客户端缓存测试后，其余套件：**632 passed、4 skipped、2 deselected**。
- `openspec validate cost-alert-webhook --strict --no-interactive`：通过。
- `git diff --check`：通过。
- 独立 Security Review：无可执行安全问题。检查了 Webhook 与 SMTP 凭据脱敏、失败记录、重试和任务恢复。

完整套件的一次运行结果为 **662 passed、4 skipped、11 failed**。其中两项代码质量测试因本机缺少 `pylint`、`flake8`、`radon` 无法生成评分；另九项 `test_llm_client.py` 用例命中持久化响应缓存，在未修改的 `origin/main` 上单独运行时也复现了相同九项失败。Issue #86 的相关测试均通过。

## 适用边界

- 预算按每道题结束后的已知成本结算；单道题可能跨越上限，未知价格无法用于熔断判断。
- 通知测试使用本地替身验证请求和 SMTP 交互；未使用真实 Webhook 或邮件账号发送。
- 远端收到通知后、成功状态落盘前若进程退出，恢复运行仍可能重发；接收方可按任务 ID、阈值和渠道去重。
