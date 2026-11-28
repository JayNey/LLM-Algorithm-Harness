# 验证报告：Web A/B 高级策略配置与题目筛选

## 结论

验证通过。5/5 任务完成，3/3 新增需求、8/8 场景具备实现与验证证据；无 CRITICAL、IMPORTANT 或未解决的行为偏差。当前改动为已批准 issue #527 范围内 12 个实现/测试文件，文件数授权见 `openspec/changes/web-abtest-advanced-config/.comet/rulings.md`。归档与 Git 交付尚待用户选择。

## 完整性、正确性与一致性

| 维度 | 结果 |
| --- | --- |
| 完整性 | proposal、design、delta spec、tasks 齐备；5/5 任务完成 |
| 正确性 | 高级参数、实际过滤、提示词优先级、兼容、错误修正均覆盖 |
| 一致性 | 复用实验白名单、筛选归一与控件，沿用现有 API、runner 和分组规则 |

## 需求与场景映射

1. **A/B 高级策略配置**：`frontend/src/abtests/validation.ts` 校验并构造完整策略；`types.ts` 保持新增草稿字段可选；`client.ts` 保留服务器配置；创建页使用 `StrategyAdvancedFields`。
   - 高级参数实际生效：`tests/test_web_abtest_config.py` 从真实 POST、数据库读取到 `_build_config`、ABTestRunner、真实 vanilla/self_consistency 策略及 mock SDK，断言 3456 Token、策略温度 0.25、自一致温度 1.2 与每题三个候选；两道题实际结果均通过。
   - 非法输入阻止请求：`frontend/src/abtests/client.test.ts` 覆盖温度越界、Token 非整数/越界、非法 JSON/非对象、未知键、错误类型/范围/枚举；浏览器确认 num_candidates=0 时无请求，修正后可提交。
   - 省略新增字段：前端旧草稿/空字段单测断言省略请求字段；Python inherited 模式断言保存配置不含温度/Token 覆盖，实际调用继承模型温度 0.4、Token 4567；浏览器旧响应展示默认配置。
2. **A/B 题目过滤与配置回显**：`experiments/advanced.ts` 归一筛选，`ProblemFilterFields` 解释条件语义，`ABTestDetailPage.tsx` 展示持久化策略和筛选摘要。
   - 实际范围符合筛选：固定六题数据含错误难度、错误标签、排除 ID、超出 limit 的干扰题；真实 runner 仅生成 picked-a/picked-b 两题结果，保留 seed=17 的既有分组结果。
   - 过滤后题目不足：too-few 模式断言 runner 在调用模型前明确拒绝不足两个变体的输入；现有 TestABTests 生命周期覆盖服务执行与结果读取，详情沿用 error_message 提示。
   - 省略或错误筛选：前端断言全空时无 problem_filters，非法难度、零/负数/小数/非有限 limit 拒绝；浏览器旧响应显示全部题目未筛选。
3. **A/B 高级配置保留变体语义与错误恢复**：创建页保留既有两变体、seed 与并发字段，busy 防重并禁用配置，失败保留 draft；现有 PromptVariantClient 无修改。
   - 提示词优先级：Python 实际 SDK 调用核对 control 使用策略提示词，experiment 使用变体覆盖，control 前缀/后缀与 experiment 前缀保持；baseline_id、seed、max_workers 均传递。
   - 请求失败后修正重提：中英文浏览器先拒绝非法配置，再模拟 503，检查提交及配置控件禁用、草稿保留；把 max_tokens 从 3456 改为 4000 再提交，核对第二次请求及刷新后的详情配置。

## 实际检查

详见 `openspec/changes/web-abtest-advanced-config/checks.json`，以下结果均已读取完整退出状态。

- 前端相关测试：62 passed、0 failed，覆盖 A/B、共享实验、国际化；日志 `/tmp/issue527-frontend-tests.log`。
- Python 相关测试：37 passed，覆盖 A/B runner、API、Web 实验共享配置及新增四种执行场景；日志 `/tmp/issue527-python.log`。
- TypeScript/Vite build 通过，ESLint 通过；日志 `/tmp/issue527-build.log`、`/tmp/issue527-lint.log`。
- 修改文件 Prettier、Python Ruff/Black 与 `git diff --check` 均通过。
- OpenSpec 严格校验通过。
- `node frontend/scripts/verify-abtest-config.mjs`（从 frontend 执行时去掉 frontend/ 前缀）通过；zh-CN/en-US 均无 pageerror，验证 320/390px 详情无横向溢出；报告 `/tmp/issue527-browser/report.json`，同目录保存表单、详情和移动端截图。

浏览器首次验收断言曾预期 mock 的原始 503 detail；共享 HTTP 层会规范化为“服务暂时不可用”。核对 `auth/http.ts` 后仅修正测试预期，中英文完整重跑通过。Python 格式化改变了 noqa 所在行，最终调整注释位置后 Ruff/Black 均通过。

## 边界与风险

- 保持 tweak direct/direct/off；独立审查按已批准 review_mode=off 跳过，不冒充独立验收。
- 使用真实 API 请求模型、SQLite 持久化、真实 runner 和策略；模型 SDK 与沙箱使用本地 mock。未调用付费模型、未启动真实 Eval，不对远程模型质量作结论。
- 沿用现有分组算法、prompt 覆盖与参数继承，不新增 API/schema 或服务依赖。
- Vite 存在现有大 chunk 提示、Python 存在依赖弃用告警，均不影响本次结果，无新增阻塞。
