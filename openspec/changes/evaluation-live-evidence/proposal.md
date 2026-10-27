## Why

#232 要求实际验证真实登录、创建、启动、进度和结果。PR #284 目前只交付了阻塞盘点；用户现要求在该原分支补齐真实端到端，并明确授权项目 config.json 中已有供应商配置，本轮累计模型调用预算上限 US$0.10。

## What Changes

- 在独立本地目录准备真实 API、SQLite、Redis、Celery worker、Docker 沙箱和浏览器；生成隔离测试账号及认证密钥，不覆盖现有用户数据库。
- 新增独立 live 验证脚本，真实登录和选项加载，使用一个最小题目、vanilla 策略和明确预算完成创建、启动、观察与结果；不拦截或替换业务 HTTP/WS、队列、模型或沙箱。
- 更新 QA 和报告，保存可公开的状态、脱敏 ID、UTC 时间、成本与浏览器截图索引。凭证仅经执行环境/受限本地文件传递。

## Capabilities

### New Capabilities

- `deepseek-provider`：明确 DeepSeek provider，固定官方 OpenAI 兼容地址，打通本人密钥管理、真实模型列表、生成和评估执行。

### Modified Capabilities

- `frontend/api-keys`：提供商选择、解析和分组增加 DeepSeek，保持密钥隐藏和既有身份边界。

## Impact

- 修改 QA、验证报告，新增 live 脚本及脱敏证据。
- 前置 #231 已通过 PR #292 合入 main（`7efbecb`），当前 PR #284 已包含该 main。
- 若发现真实流程缺陷，先复现并按最小失败测试修复；超出本 change 或预算的事项明确报告，不以 fixture 替代。
