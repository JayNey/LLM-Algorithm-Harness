# #525 验证报告

## 结论

PASS：当前实现满足批准的推荐参数范围。4/4 任务，1 条新增需求与 5 个场景均有实现及验证证据。没有本次改动引入的关键问题；无迁移、付费模型调用或外部服务写入。Run 的 reviewMode=off，未进行独立 reviewer 审查，由当前 Agent 完整核查规格、设计与最终差异。

## 完整性与一致性

- 请求模型 `api/evaluation_options.py:60` 为 limit 定义默认 20、严格整数 1–100；现有阈值保持默认 0.5、范围 (0,1]。
- 路由 `api/routes/evaluation_results.py:187` 显式向共享分析传 limit，沿用已授权历史、来源、最少样本与排序。
- 客户端字段可选，兼容省略参数的现有调用。RecommendationPanel 输入当前参数并清除旧预览与选题；空值、阈值越界与非整数数量阻止提交；容量说明为 100 道。中英文资源完整。
- 当前 9 个交付文件：实现 4、文案资源 2、测试 2、验收报告 1，与批准的 7–9 文件预估一致；范围复核见 `.comet/rulings.md`。

## 场景映射

| 场景 | 实际证据 |
| --- | --- |
| 阈值改变薄弱组 | 固定 50% 失败历史，API 测试及 Chrome 验证阈值 0.5 有候选、0.75 无薄弱组 |
| 超过默认数量 | 110 道固定候选，API 验证 1/20/30/100 返回及排序前缀；Chrome 验证 20/30/100 个复选框 |
| 默认及非法输入 | API 省略参数返回 20；非法数量 0/-1/101/20.5/bool/string/null 及非法阈值返回 400 INVALID_PARAMETER；Chrome 验证默认字段及清空/越界/小数禁用提交且不发送请求 |
| 空状态和访问边界 | API 覆盖来源、历史不足、无候选及他人历史 404；Chrome 切换来源和最少样本验证对应空状态 |
| 保存并继续 | API 保存第 20 个以后的候选、重新读取、创建后数据库 ID 一致；Chrome 修改参数清除旧选题，选择 candidate-025，保存、重开题集并进入创建页，权限校验请求只含该 ID |

## 检查

- `.venv/bin/pytest tests/test_api_evaluation_options.py tests/test_recommender.py --no-cov -q`：82 passed，日志 `/tmp/issue-525-backend-tests.log`。
- `npm test`（frontend）：371 passed，日志 `/tmp/issue-525-frontend-tests.log`，包括中英文资源检查。
- `npm run build`（frontend）：TypeScript 和生产构建通过；存在原有大 chunk 提示。
- `CHROME_PATH='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' node frontend/scripts/verify-recommendation-controls.mjs`：通过；日志 `/tmp/issue-525-browser.log`，桌面与手机截图 `/tmp/issue-525-qa/desktop.png`、`/tmp/issue-525-qa/mobile.png`。浏览器使用真实请求模型、路由及分析函数，替换存储依赖；实际权限与持久化另由 API 集成测试覆盖。
- 定向 Ruff、Black、ESLint、Prettier、`git diff --check` 与 OpenSpec `validate --strict`：通过。

## 已有检查限制

Python mypy 全导入检查失败：第三方 sklearn/celery/scipy 缺失类型声明，另有 deduplication、tasks 与推荐路由的既有注解错误。限定导入检查仅剩推荐路由的 empty_reason 类型推断错误；从 HEAD 提取原始路由到 `/tmp/issue525_baseline_route.py`，用相同参数复现同一错误（原 214 行，当前 215 行），本次两行后端变更未引入新类型错误。这项可选检查未计为通过。

通用 `verify-i18n.mjs` 初次启动因默认 Playwright 浏览器未安装而未执行；中英文资源由 371 项单元测试覆盖，本次表单由本机 Chrome 脚本验收。没有执行全仓库后端测试或真实模型调用。
