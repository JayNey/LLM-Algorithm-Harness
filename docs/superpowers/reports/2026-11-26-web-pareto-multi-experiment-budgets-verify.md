# Issue #524 验证报告

## 结论

实现满足已批准范围。完整性：5/5 任务、3/3 新增要求；正确性：所有新增场景已通过客户端测试、真实 API 浏览器验收或现有会话边界源码核对；一致性：遵循简要设计与现有认证/请求隔离模式。无 CRITICAL、IMPORTANT 或待决定的行为偏差。

## 实现映射与场景

- Pareto 多实验选择：ExperimentDetailPage.tsx 的 ParetoTab 使用现有 client.list 分页；client.ts 的 pareto 去重 ID 并完整读取原始报告后 POST。客户端测试覆盖重复 ID、快照保留、空选择、读取失败短路和取消信号。浏览器覆盖默认单实验、列表失败重试、分页加载、两实验请求、不兼容第三实验、404 读取拒绝后不提交部分报告。
- 预算与口径：预算输入拒绝负值、NaN、Infinity、非法文本和溢出；空白为 []。浏览器断言 `[0,0.012345,2,2]` 原值提交与服务端去重后的三行推荐，并逐行比较真实 API 的预算/可行性/point_id，确认 formal 下足额预算推荐 premium，前沿显示 premium。overall/formal 请求均已核对。
- 失败恢复与结果隔离：输入与结果分区，useResource 通过 load/attempt 身份与 AbortController 忽略旧响应。浏览器覆盖加载时隐藏旧表、读取拒绝、分析 500、当前输入重试、迟到成功/失败、空选择、恢复选择及携带进行中请求切换详情后恢复默认分析。身份切换复用 session.tsx 的 owner key 重挂整个会话及 ParetoTab，源码核对通过；本次没有改变该权限/生命周期边界。
- 访问控制：实验列表与原始 comparison 均经原有认证 HTTP 实例和资源接口读取，不新增权限旁路；服务端不兼容错误直接显示，不在客户端合并统计或推断可比性。
- 7 个交付文件与 proposal 一致，分类 implementation/tests。文件数授权见 rulings.md。review_mode=off 为已批准 tweak 预设，未派发独立 reviewer。

## 实际检查

| 检查 | 结果 |
| --- | --- |
| frontend `npm test` | 371 passed, 0 failed；日志 `/tmp/issue524-all-frontend.log` |
| `.venv/bin/python -m pytest tests/test_pareto.py --no-cov -q` | 31 passed；日志 `/tmp/issue524-pytest.log` |
| frontend `npm run build` | tsc 与 Vite 成功；日志 `/tmp/issue524-build.log` |
| 7 个交付文件的 `npx eslint` 与 `npx prettier --check` | 通过 |
| `git diff --check` | 通过 |
| `comet classic openspec -- validate web-pareto-multi-experiment-budgets --strict` | 通过 |
| `CHROME_PATH='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' node --experimental-strip-types scripts/verify-pareto-inputs.mjs` | exit 0，18 次分析请求；日志 `/tmp/issue524-browser-complete.log`；证据 `/tmp/issue-524-qa/result.json` 与桌面/移动截图 |

浏览器通过隔离 FastAPI TestClient 调用真实 `/pareto/analyze` 与共享算法，认证/列表读取用本地 mock；没有付费模型调用。客户端500错误按共享HTTP客户端既有规则显示统一提示。生产构建仍有既有大 chunk 提示；定向 pytest 初次默认覆盖率模式31项均通过但未达到仓库全局90%门槛，后按定向验证目的使用 --no-cov 成功，不宣称全仓后端覆盖率通过。既有 Pydantic 弃用警告未改动。

## 设计与模式核对

保留原始 comparison 的数据集/配置快照；后端决定兼容性、预算排序去重与前沿。页面按需分页且保留当前实验默认选项，沿用现有双语资源、Ant Design 控件及 useResource 模式。当前详情切换通过 key 重挂 Pareto 表单，身份切换由既有 SessionScope 的 owner key 隔离。无 schema、依赖或持久化迁移。
