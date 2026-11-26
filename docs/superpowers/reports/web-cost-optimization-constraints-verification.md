# 验证报告：web-cost-optimization-constraints

## 结论

Issue #523 的实现及验收通过。5/5 任务完成，2/2 新增需求、6/6 场景已核对，无 CRITICAL、IMPORTANT 或待决定行为偏差。仍处于当前 change，等待归档交付选择。

| 维度 | 核对结果 |
| --- | --- |
| 完整性 | 5/5 任务完成；2 条新增需求均有实现及测试证据 |
| 正确性 | 6/6 场景覆盖，固定数据经客户端、真实 API 路由和共享 build_advisory 验证 |
| 一致性 | 遵循已批准设计，复用现有客户端、useResource、AbortSignal、错误组件、表格和国际化资源 |

## 需求与场景映射

### 成本优化约束输入

实现：`frontend/src/pages/Experiments/ExperimentDetailPage.tsx` 的 OptimizeTab；`frontend/src/experiments/client.ts` 的 optimize 与 advisory；响应契约见 types.ts。

- 有效约束到达共享分析：浏览器输入预算 5、准确率 80，真实客户端发送 budget=5、min_accuracy=0.8。测试通过 FastAPI TestClient 调用真实 `/api/v1/optimize`，包装共享 build_advisory 并核对其完整调用参数；服务端返回真实计算结果。
- 固定数据：cheap 费用 $1.2、准确率 50%，premium 费用 $6、准确率 100%，每难度 2 题。默认最低成本推荐 cheap，最低准确率 80% 后推荐 premium；$5 分层预算可覆盖 easy/medium 共 4 题、估算 $4，hard 明确预算不足。预算仅约束分层方案，保留三个推荐目标的既有语义。
- 未填写约束：客户端与浏览器均核对省略 budget/min_accuracy，保留三目标推荐和排名、不显示预算方案；百分比 0、100 边界均转换正确。
- 非法输入：页面覆盖预算 0、负值、Infinity、NaN、文本和溢出指数；准确率负值、101、Infinity、文本，均反馈字段错误、不发分析请求并隐藏旧结果。

### 成本优化结果恢复与预算展示

实现：同页 OptimizeResults、ExperimentFeedback 以及现有 useResource；新增中英文文案保持资源键一致。

- 预算展示：核对预算、准确率、估算成本、覆盖题数、每层推荐与不可行原因；$0.01 时共享分析返回 estimated_accuracy=null，客户端保留 null，页面显示“无法估算”。分层错误类型及不合法准确率等响应由严格解析拒绝。
- 失败重试：注入一次 500，页面保留可编辑约束及错误提示；重试以当前预算 3 请求，成功展示对应方案。
- 迟到结果：挂起预算 2 的旧请求，再设置预算 5、准确率 80%；加载时隐藏旧结果、表单可编辑，释放旧响应后仍展示当前约束的 premium 推荐与分层结果。
- 桌面与 390px 窄屏截图已人工视觉核对：字段可读，窄屏单列，结果表格在独立容器内横向滚动。

## 实际检查

- `frontend: npm run build`：通过，TypeScript 与 Vite 构建成功。
- `frontend: npm run lint`：通过；六个交付文件的 Prettier 检查通过。
- `frontend: node --experimental-strip-types --test src/experiments/*.test.ts src/i18n/*.test.ts`：33 passed，0 failed。
- `.venv/bin/python -m pytest tests/test_cost_optimizer.py tests/test_api_experiment_benchmark.py::TestAnalysis --no-cov -q`：17 passed。
- `frontend: CHROME_PATH=<本机 Chrome> node --experimental-strip-types scripts/verify-optimization-constraints.mjs`：通过，14 次优化请求，覆盖客户端契约、真实共享处理和浏览器场景。
- `comet classic openspec -- validate web-cost-optimization-constraints --strict`：通过。
- `git diff --check`：通过。

记录见 `openspec/changes/archive/2026-11-26-web-cost-optimization-constraints/checks.json`；本次平台原始日志为 `/tmp/issue-523-{build,frontend-tests,python-tests,browser}.log`，结构化浏览器结果为 `/tmp/issue-523-qa/result.json`，截图为同目录 `constraints.png` 和 `constraints-mobile.png`。

## 范围、审查与验证边界

交付代码及测试共 6 文件：实验详情页、客户端、类型、中英文资源及独立验收脚本；Comet 产物另行保存。无 API schema、共享算法、CLI、密钥、服务地址或沙箱权限变化，仍符合已批准 tweak 范围。

独立代码审查按当前 Runtime 配置 review_mode=off 跳过，由本会话完成规格一致性和差异核对。不是独立 reviewer 结论。

测试使用本地固定数据；API 鉴权依赖在隔离 TestClient 中替换，不验证生产部署、真实登录或外部模型调用。未运行全仓测试。第一次局部 Python 测试的 17 个用例均通过，但触发全仓 90% coverage 门槛；随后以 `--no-cov` 正确执行局部回归并退出 0，不据此宣称全仓覆盖率达标。构建保留既有大 chunk 提示，不影响本次构建成功。

初次浏览器失败来自 Ant Design 双汉字按钮自动空格导致测试精确匹配不到“重 试”；已按实际可访问名称修正测试，最终完整脚本通过。无未解决失败。

## PR 交付绑定复核

用户明确选择归档、推送并创建 PR 后，当前 change 从 main 重新绑定到 `codex/web-cost-optimization-constraints`，远端为 origin，PR base 为 main。实现、测试、规格及工作区内容未改变，现有检查继续适用。旧 main 归档提案已通过公开 Runtime 入口取消，本轮只复核交付绑定，不重复运行未失效的检查。
