# 基准统计修复验证报告

结论：PASS。变更 fix-benchmark-statistics 已实现并通过相关验证，已获得归档、推送并创建 PR 的用户授权。

日期：2026-10-26。分支：tweak/20261026/fix-benchmark-statistics，目标：main。
源码审查范围：fbfa11cdeadb0e2eea177b2dc105158c04337537..5ee7e14。

## 修复结果

- BenchmarkExecutor 在保留既有策略级字段的基础上输出顶层 accuracy、cost_usd。
- accuracy 为策略准确率的算术平均，与 BenchmarkHistoryStorage 的既有计算口径一致；cost_usd 为全部策略 estimated_cost_usd 之和。
- 无策略结果时 accuracy 为 None、cost_usd 为 0.0。
- BenchmarkService 逐指标仅在顶层值为 None 时回退到 summary，保留有效零值及 summary-only 兼容性。
- 真实执行器的统计已通过运行详情、数据库重新读取及两次历史学习曲线与趋势的集成测试。

## 完整性、正确性与一致性

- 任务：2/2 完成，OpenSpec apply 返回 all_done。
- 范围：4 个源码/测试文件；其余为本次 Comet 状态和规划产物。自动规模评估包含这些产物，选择 full 验证；实施范围未新增能力、端点、数据库结构或架构协调。
- 规格：修复已有 api/experiment-management 的基准运行持久化和学习曲线要求；没有规格级行为变更，.openspec.yaml 明确 skip_specs: true，严格校验通过。无 delta spec 需要同步。
- 设计：实现符合 change 的 design.md；没有实现偏差。独立 Superpowers Design Doc/plan 按 tweak 预设不要求，未人为补造文档。
- 兼容：原 suite、problems_evaluated、problems_missing、strategies 和策略级 total_cost 等字段保留，既有 JSON 历史读取测试通过。
- 边界：单策略、多策略、不同策略题目总数、零准确率、零成本、空报告、顶层优先级、逐字段 summary 回退及缺失指标均有回归覆盖。
- 安全：未引入密钥、网络调用、额外持久化接口或权限改动；数据库与任务生命周期检查保持原有执行顺序。

## 验证证据

1. 修复前基线：执行器、基准 API 与任务的现有相关测试 25 passed。
2. 执行器新增测试先出现 6 failed / 4 passed，失败均为缺少 accuracy 字段；汇总修复后 10 passed。
3. API 新增回归先出现 5 failed / 13 passed，展示零值被改成 None 或 summary 中的非零值。
4. 修复后相关测试与正式 verify 阶段测试均为 90 passed。正式验证命令：

```sh
python3 -m pytest -o addopts='' -p no:cacheprovider tests/test_api_experiment_benchmark.py tests/test_benchmark_task.py tests/benchmark -q --tb=short --basetemp=/Users/charlesleclerc/Documents/Codex/2026-10-26/co/work/pytest-verify --junitxml=/Users/charlesleclerc/Documents/Codex/2026-10-26/co/work/benchmark-tests.xml
```

5. 改动文件的 ruff --no-cache、black --check 和 git diff --check 均通过：

```sh
python3 -m ruff check --no-cache src/benchmark/executor.py api/services/benchmark_service.py tests/benchmark/test_executor.py tests/test_api_experiment_benchmark.py
python3 -m black --check src/benchmark/executor.py api/services/benchmark_service.py tests/benchmark/test_executor.py tests/test_api_experiment_benchmark.py
git diff --check
```

6. Python wheel 离线构建通过，且检查归档内两个修改后的源码文件与工作区逐字节一致：

```sh
python3 -m pip wheel . --no-deps --no-build-isolation --wheel-dir /Users/charlesleclerc/Documents/Codex/2026-10-26/co/work/dist --disable-pip-version-check --no-index
```

环境说明：PyPA build 未安装（import build 命中本地 build/ 命名空间），因此使用已安装 pip 和项目声明的 setuptools 后端完成打包；ruff 使用 --no-cache 避开只读沙箱缓存写入。测试输出的 5 条 Pydantic 弃用提示与基线一致。验证范围为上述相关测试，未运行全仓库测试或声明全仓库覆盖率达标。

## 集成代码审查

review_mode: standard。独立只读 reviewer 对完整源码 diff、任务、设计、报告生成、历史提取、持久化及学习曲线消费者进行了检查，结论 READY，无可操作的正确性、安全或兼容问题。

审查明确核对：等权统计与历史口径一致；空报告语义有测试；零基线增长率沿用既有 None 语义；暂停/失败状态不会被新增统计绕过。外部模型执行保持离线替身，但执行器结果映射、API 写入和曲线聚合均使用真实代码。

## 后续状态

修复已在新分支本地提交；verify 状态元数据与本报告属于同一变更。旧数据库记录中的空指标没有批量回填。用户已明确选择 C：确认归档、立即推送并创建 PR。change 已移动到 openspec/changes/archive/2026-10-26-fix-benchmark-statistics/；归档提交完成后按该授权交付。
