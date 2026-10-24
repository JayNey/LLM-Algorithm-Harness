# Tasks: settings-frontend

## 1. 簇 A：监控面板（admin）

- [ ] 1.1 `monitoring/types.ts` + `client.ts`（严格解析：system/status 全量、resources、api-stats(window)、llm-stats(window)、cache-stats、system/health）+ 单测（真实形状/拒绝路径/窗口参数）
- [ ] 1.2 SystemPage 重写：健康卡片、CPU/内存/磁盘、队列 pending/reserved、任务计数、API 统计（QPS/avg/P95/错误率）、LLM 统计、缓存命中分区；30s 轮询（可关、隐藏暂停）；沙箱/策略/提供商只读 Tab（config/*）

## 2. 簇 B：预算与预警（owner）

- [ ] 2.1 `budgets/types.ts` + `client.ts`（budgets CRUD + usage、alerts CRUD）+ 校验（cap 非负、threshold 1–100、channel 白名单）+ 单测
- [ ] 2.2 `/settings/budgets` 页：预算编辑（global/difficulty 三档/action）+ 使用量 + 预警规则表（增改启停删）；投递未实现文案

## 3. 簇 C：定价（owner）

- [ ] 3.1 `pricing/types.ts` + `client.ts`（目录/历史/追加）+ 校验 + 单测
- [ ] 3.2 `/settings/pricing` 页：三源目录表 + 模型历史抽屉 + 追加自定义定价表单

## 4. 簇 D：日志（admin）

- [ ] 4.1 `systemlogs/types.ts` + `client.ts`（level/start/end/search/limit/offset）+ 单测
- [ ] 4.2 `/settings/logs` 页：级别筛选、时间范围、搜索、分页

## 5. 收尾

- [ ] 5.1 routes.tsx（budgets/pricing 全员、logs admin）+ AppLayout 两 Provider + package.json glob
- [ ] 5.2 verify-settings.mjs（monitor/budgets/pricing/logs 场景）+ QA.md；全量测试/tsc/eslint/prettier 绿；#167 记录验收
- [ ] 5.3 独立审查两轮制 + 最后 commit 后三件套重验
