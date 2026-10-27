# Issue #231：工程质量与回归验证

日期：2026-10-27（Asia/Shanghai）。Change：`evaluation-quality-gates-completion`。分支：`codex/tweak/20261027/evaluation-quality-gates-completion`。

## 基线与范围

用户确认基于 PR #286 新建分支并同步 main。保留原提交 `545d62d46ef5c237731d9e57c9fddb7159665a0d`，合入 main `b86d65eff2d2a76fdd39f54fe7b2794b9e3dc955` 后，测试代码 SHA 为 `48ea717b5526cc8198f1b395e4285e58263f8564`，已含 #229 / PR #282 与 #230 / PR #291。

本轮产品源码、测试、前端、pyproject 和 CI 配置相对 main 无差异。交付文件为质量矩阵、命令 JSON、日志及本报告，其他变更为 Comet 工作流产物。未改变公共行为，因此 `skip_specs: true`；tweak 预设不需要独立 Superpowers Design Doc/plan，也没有 delta spec 或规格漂移。

## 实际验证结果

完整命令、工作目录、执行时间、代码 SHA、环境、退出码与日志行号见 [commands.json](../../frontend/assets/issue231/commands.json)，完整命令输出见 [execution.txt](../../frontend/assets/issue231/execution.txt)，逐项要求对应见 [检查矩阵](../../frontend/EVALUATIONS_CHECKS.md)。日志仅归一化 ANSI 色码、行尾空白和末尾空行，没有改写检查结果。

- 全量 `python3 -m pytest -m "not online"`：3366 passed、11 skipped、128 warnings，461.94s，exit 0；总 coverage 92.69%。
- 同轮 coverage 后置门禁：`src/*` 91.38% ≥ 90，`api/*` 94.86% ≥ 81，均 exit 0。没有用定向 coverage 冒充全量。
- 定向 16 文件 Python：382 passed，5 warnings，exit 0；显式 `--no-cov`，与全量分开。
- 原始 API mypy（3 个指定文件、保留 Python 3.10 目标）：exit 0；CI `mypy src/ --ignore-missing-imports`：98 个源文件通过，exit 0。
- 指定 ruff、全库 ruff、Black（351 个文件）、编码检查：均 exit 0。
- 前端 `npm test`：257 passed；`npm run lint`、`npx tsc -b`、`npm run build`：均 exit 0。保留两条既有 hook warning 和大 chunk 提示。
- `git diff --check origin/main...HEAD`、工作区 diff check、OpenSpec strict validate：通过。

## 失败分类与验证边界

宿主首次 CI mypy exit 1，缺少 dev 类型桩且依赖版本与隔离完整开发环境不同；隔离 Python 3.11、完整 `.[dev]` 环境在不改源码/目标版本的情况下复验通过。初始失败完整保留。原 PR 使用 Python 3.12 目标覆盖的替代证据已被原始 API 命令通过所替代，不需要维护者接受豁免。

本轮日志文件引入过尾随空白；历史提交 `e639932` 的 diff check 可复现 exit 2。修正归档格式并重算哈希后，当前 diff check exit 0。它被明确归为本轮文档回归，未归为既有问题。

11 skips 分别为 3 个 Locust 可选依赖检查、2 个真实 Redis/Celery 测试、1 个 LeetCode online、1 个容器监控、1 个队列监控、2 个真实 Docker 沙箱测试，以及 1 个供应商验证模块级 skip；条件和 warnings 原文见矩阵/日志。本地仅 macOS/Python 3.11，不宣称 Windows、真实服务、Safari/Firefox、真机或真实 browser↔API 联调已验证。

前置 #216–#230 的公开要求与当前代码/测试逐项核对，依赖 PR 均在测试基线祖先链中。继承 #230 的 all149/appearance216 对应 `45d910` 且前端源码未变；security8 记录 `606fb25` 与 auth/store 源码 dirty，shell51 无 source 元数据，后两者按前置公开报告引用，不虚构统一 SHA。最终 all 本身也覆盖认证与迟到 identity 场景。四个产物均有零未知请求；all/security/shell 的页面异常字段存在且为空，appearance 未记录该字段。原复核脚本的缺失字段默认零输出已明确撤回为该项证据，保留旧输出并新增 `inherited-browser-evidence-v2` 准确复核。它们均为继承的 fixture 证据，本轮未重跑浏览器。#232 的真实外部依赖和 #233 的交付汇总继续单独跟踪。

## Comet 完整验证

规模评估：3 项任务、0 个 delta spec、15 个变更文件（包含证据与流程元数据），选择 full。完整性：3/3 build 任务均有实际检查或材料；正确性：19 项当前必需门禁/自检 exit 0，两项已解除失败保留；一致性：proposal/design 的代码基线、双环境、coverage 顺序、原始 mypy 和分层证据均一致。不适用的独立 Design Doc/plan 和 delta spec 按 tweak 的明确规则跳过。

verify 阶段独立执行 `python3 -m json.tool docs/frontend/assets/issue231/commands.json`（exit 0），并通过 Python 内联检查核对 27 个日志块及整体 SHA-256、19 个当前门禁结果、两项失败原始退出码、五个源码树 ID、coverage 执行顺序、矩阵链接和任务复选框；全部通过。源码树与 build 验证时相同，未重复执行没有变化的全套测试。

## 最终集成审查

独立只读集成审查首轮：Critical 0、Important 0、Minor 3（各产物来源 SHA、appearance 缺失字段、环境版本比较范围）。已回到 build 完成三处修正并保留旧日志，新增准确复核；等待同一 reviewer 定点复审。

## 远端状态与归档

main 的 [CI run 40444425429](https://github.com/JayNey/LLM-Algorithm-Harness/actions/runs/40444425429) 对应 `b86d65eff2d2a76fdd39f54fe7b2794b9e3dc955`。证据快照中 8/10 jobs 成功、两项 Windows 检查运行中；该快照不代表所有 CI 已完成。Security job 中既有 bandit/safety 配置 `continue-on-error`，不能据 job success 推断安全扫描零发现。

新分支尚未推送，未宣称其新提交 CI 通过；未修改、关闭 issue 或发布 PR 留言。归档前剩余 dirty 项均为本 change 的验证报告与 Comet 阶段记录，不含用户修改。完成本地验证后按 comet-archive 最终确认选择归档及本地保留/推送/创建 PR；#231 的远端交付与审查通过后才可关闭。
