# #308 个人题库数据集引用验证

日期：2026-10-28（Asia/Shanghai）。Change：personal-dataset-references；分支：codex/personal-dataset-references；基线：95b97a11e977a45be0db08e3fbdaa86b8cc2dc41。

## 结论

实现与 #308 验收项、proposal、design 和两条新增需求/四个场景一致。相关后端 225 项、前端 281 项测试通过，5 个浏览器场景通过；前端生产构建成功。没有未解决的本次变更正确性、安全或边界问题。

用户已明确选择继续 tweak 和独立分支（1A2B），覆盖已说明的跨服务 API/前端范围。无需数据库迁移、新依赖或公共题库写入。用户在归档前最终确认中选择 C：确认归档、推送当前绑定分支并创建 PR。

## 可重现证据

- 后端：`python3 -m pytest tests/test_dataset_references.py tests/test_api_experiment_benchmark.py tests/test_api_files.py tests/test_experiment_task.py tests/test_benchmark_task.py tests/test_ab_test_task.py tests/test_experiment_queue_safety.py tests/test_experiment_cancellation.py --no-cov -q`：225 passed，5 条既有 Pydantic 弃用提示。定向测试 `tests/test_dataset_references.py` 为 22 passed。
- 前端：在 frontend 中执行 `npm test`：281 passed；`npm run lint`：0 errors（基准页两条原有 useCallback 依赖警告）；`npm run build`：tsc 与 Vite 成功（保留既有大 chunk 提示）。
- `python3 -m black --check api/datasets.py api/experiment_models.py api/routes/files.py api/services/experiment_service.py api/services/benchmark_service.py api/services/ab_test_service.py tests/test_dataset_references.py`、同范围 `python3 -m ruff check` 和 `python3 -m compileall -q` 均通过；前端修改文件经 prettier 与提交 hook 的 eslint 检查。
- `comet classic openspec -- validate personal-dataset-references --strict`：通过。
- 浏览器：Vite 5180，本机 Chrome，执行 `frontend/scripts/verify-dataset-references.mjs`，输出 `PASS: 5 browser scenarios, 3 source payloads`。真实 React 页面使用模拟 API，不调用模型。记录及六张桌面/窄屏截图见 [浏览器证据](assets/personal-dataset-references/report.json)。桌面宽 1280，窄屏宽 390，截图已人工查看。
- 初始 RED：新增 API 测试复现缺少 /datasets、双来源/空白来源未拒绝；三个前端 payload 测试复现个人集合仍被强制要求路径。随后相同测试 GREEN。

## 需求映射

### 个人数据集引用与选择

`api/datasets.py` 的集合列表只查询当前 owner，稳定 dataset_id 解析再次匹配 owner。`api/routes/files.py` 的 GET /datasets 使用登录身份。请求模型 DatasetRequest 为三类创建/运行请求共享排他校验，空白/双来源/缺少来源拒绝。`freeze_dataset` 对缺失/他人引用、空集合和不可用数据明确报错；旧路径保留 DATA_ROOT 限制。

集成测试通过真实 problems/upload 导入后分别创建实验、基准 run 和 A/B，并启动执行；验证用户 B 列表为空，不能消费用户 A 引用；覆盖 unknown、empty、corrupt、参数冲突与路径越界。前端共享 DatasetPicker 提供集合选择、加载、空态入口和失败重试；三类校验和客户端兼容个人引用和旧路径，原模型/策略字段保持。浏览器捕获三类 POST，均只有 dataset_id，没有 dataset_path。

### 执行数据快照与追溯

在实验/A-B create、benchmark start_run 边界冻结完整 Problem JSON，摘要包含来源、创建时间、SHA-256、题目数、版本及内部 owner。摘要响应去除完整 problems 与内部 owner；完整数据与业务 config 同事务持久化，随业务行保留和删除。

Worker 以 execution_dataset 校验 owner/hash，再用私有 TemporaryDirectory 生成输入；ExitStack 覆盖整个执行作用域。新增测试先创建业务，再覆盖个人集合、删除源集合与原始上传；三类任务实际暂停，经 TaskManager 确认停止并恢复，再由新的服务实例完成执行，两次读取内容相同。检查 tags、difficulty、judge_config、source_metadata、source_problem_id 保留，临时文件均已清理。另测错误 owner、篡改摘要不符、异常退出清理、删除业务行带走快照，以及旧路径源文件删除后依然可读快照。

## 一致性与审查

遵循 design 的数据库快照方案，无独立快照存储/GC、无共享文件系统依赖；部署与 TTL/强杀清理说明已写入 docs/experiments.md。tweak 按用户选择跳过 Superpowers Design Doc 和完整 plan，因此此两项不适用。delta spec 未发现漂移。

review_mode=off（tweak 预设），按 comet-verify 跳过自动独立代码审查。主会话已检查最终改动的所有权、请求契约、冻结边界、临时文件生命周期、历史记录路径回退、完整字段序列化、前端协议解析和三类表单，不存在待修复发现。

额外尝试 mypy：目标六个修改模块当前无诊断；命令整体仍被未修改的 Celery/kombu/YAML/scipy stubs 和 api/routes/tasks.py、api/routes/evaluations.py 共 11 条既有类型问题阻断。未将该命令记为通过，也未扩展本次范围修复这些既有问题。

## 验证范围与运行条件

使用真实认证/导入/业务数据库和 Celery 任务管理状态；队列发布与模型调用使用离线替身。浏览器使用模拟 HTTP 数据验证表单，不宣称对真实模型或线上多主机队列做端到端验收。多主机需共享业务数据库；升级前已存在且没有快照的任务沿用原文件要求。被操作系统强杀的 Worker 可能遗留系统临时目录，由部署 tmp 清理策略处理。

## Verify 阶段独立复核

构建提交后重新运行 `python3 -m pytest tests/test_dataset_references.py tests/test_api_experiment_benchmark.py --no-cov -q`：61 passed；重新运行 frontend 的 npm test（281 passed）、npm run lint（0 errors）、npm run build（成功）、修改文件 prettier 检查和后端 black/ruff 检查均通过。OpenSpec strict validate 再次通过。验证阶段未修改实现或测试，仅追加本报告及 Comet 状态证据。

## PR #314 CI 修复复核

首轮 CI 的 Lint 和六个测试矩阵均因 tests/test_dataset_references.py 五处隐式编码失败，补齐 UTF-8 后编码门禁通过。完整测试随后发现新增端点未加入统一 API 文档、HTTP 端点覆盖表与兼容性基线，以及真实实验/A-B 恢复时临时文件路径导致检查点指纹变化。覆盖率检查本身通过。

修复将检查点指纹建立在配置与题目内容之上，排除临时输入路径；回归验证同内容换路径可恢复且不重复费用，内容变化仍拒绝。数据集列表通过 FileService 接入统一端点测试；OpenAPI 补齐认证、限流、错误、curl 和个人数据源请求示例。契约按既有版本策略递增为 1.3.0，只定向更新三个已审查的请求模型和新增 /datasets 操作，旧路径约束及兼容性门禁的严格比较规则保留。

本地验证：相关 API 文档/版本/端点/数据集/真实执行器及实验/A-B 回归 964 passed；费用 API 完整集成 24 passed（含真实 HTTP 及 Worker 暂停恢复）；UTF-8 与数据集原回归 40 passed。全仓库 Ruff、Black 和显式编码扫描通过。远端新一轮完整测试矩阵将在该修复推送后运行。
