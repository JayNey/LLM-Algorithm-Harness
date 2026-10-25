# api-performance-tests 验证报告

结论：PASS。Issue #158 第 5 节的负载、压力、并发、响应时间、数据库查询五项均已有可复现工具和实测记录。生产 API/schema 未修改；不声明生产容量或 SLA。

## 轻量验证六项

- PASS：tasks.md 三项已完成；OpenSpec validate 通过（纯测试工具，skip_specs: true，无 delta）。
- PASS：实现范围为 pyproject.toml、tests/performance 下五个文件，共六个实现文件；其余为本 change 的 Comet 生成元数据。scale 在提交前曾报 build configuration incomplete，提交完成后统计 18 文件（含 12 个流程产物）判为 full；依照 verify override 协议按 3 tasks、0 delta、6 实现文件选择 light。未发现跨层架构、新增生产 capability、public API、schema 或多 change 信号。
- PASS：真实 wheel 构建成功：`python3 -m pip wheel . --no-deps --no-build-isolation --wheel-dir /tmp/harness-158-wheel-final`。`python3 -m compileall -q tests/performance` 通过。
- PASS：最终提交后运行 `/tmp/harness-perf311/bin/python -m pytest tests/performance/test_tools.py tests/test_api_database.py tests/test_runs_visibility.py tests/test_api_documentation.py -o addopts='' -q`，62 passed，29.79 秒。5 条既有 Pydantic 弃用警告；无测试失败。限定相关回归，不声称全仓库覆盖率达标。
- PASS：临时数据库、随机密钥、受限 token 文件及 loopback 服务均隔离；无 LLM/任务提交。临时服务已终止，token 文件确认删除。ruff、black、显式文本编码检查、git diff --check 均通过。
- PASS：按 requesting-code-review 派发一次只读最终审查；无 Critical/Important。三项局部改进已落实：移除基准中的 assert 查询（防止 -O 跳过）、自检固定 PERF_MAX_P95_MS、基准记录 Locust 2.47.0。修正后重新通过 12 工具测试和最终 62 项回归；`python3 -O` 下 1000 行、100 样本、4 并发基准全部无错。

## 实测证据

`tests/performance/baseline.json` 为保存的基准。正常模式 HTTP 各 100 请求/4 并发，数据库各 100 次/串行，三张表各 1000 行，全部无错。HTTP 健康/评估列表/任务列表 p95 分别为 17.730/174.399/52.381 ms；数据库唯一键查询、深分页、count、用户评估列表 p95 为 0.212/0.259/0.170/8.119 ms。

Locust 使用临时真实 HTTP 服务：
- load：10 用户、20 秒，569 请求、0 HTTP 错误、p95 84 ms，退出 0。
- concurrency：10 用户、20 秒，626 请求、0 HTTP 错误、p95 96 ms，退出 0。
- stress：10 秒/阶段，目标 10/20/40/80，历史记录确认峰值 80 用户；1164 请求、0 HTTP 错误、p95 5800 ms，超过 1000 ms 门限退出 1。该非零是主动增压后的诊断结果，按设计保留，并非将性能退化豁免成通过；未在本 change 中扩展为生产性能优化。停止时等待在途请求完成。
- 基准 CLI 使用极低 p95 门限的负向验证退出 1，证实可检测超限。自检覆盖零样本、请求失败和 Locust 延迟门限。

原始运行日志、CSV、HTML 为 `/tmp/harness-158-*`；仓库保留汇总 JSON，README 提供重新生成命令。

## 调试与状态记录

首次临时 venv 被 uv 选择为 Python 3.14，缺少项目依赖；定位后换为与项目一致的 3.11 隔离环境。Locust 启动曾因方法命名覆盖保留的 tasks 属性失败，保留 shape 自检复现后改名为 task_list，重跑通过。文件编码检查指出 subprocess 默认编码后已显式使用 utf-8。短阶段压力测试最初无法到达目标，改为每阶段 users/5 的生成速率，自检和真实历史验证通过。上述问题均经 systematic-debugging 的先定位后修复流程完成。

进入 verify 前为补齐最终文档/修正提交前置条件，通过 verify-fail 回 build 进行提交，之后重新通过 build guard；verify_failures 曾增加为 1；最终验证通过后状态机已重置为 0。所有最终实现已提交；当前未提交改动仅为验证报告和 Comet 状态，留待归档最终确认。

## 归档交付选择

用户明确选择 C：归档、提交、推送当前绑定分支并创建 PR。归档目录为 openspec/changes/archive/2026-10-25-api-performance-tests，最终归档守卫 6/6 通过；branch_status: handled 表示交付方式已确认，远端结果另由 PR 记录。
