# api-coverage-gate 验证报告

## 范围与实现

仅完成 GitHub issue #158 第 6 节：覆盖率目标、报告、CI 检查。生产代码、API、schema 未变更，skip_specs: true。

- 收集仓库内执行数据，所有报告仅纳入 src/、api/，未导入 namespace 文件也纳入分母。
- 保留总覆盖率与 src 各 90% 门槛，API 独立门槛 81%；按 coverage 原生两位小数精度检查。
- 默认生成终端、HTML、XML 报告；CI 六种 OS/Python 组合分别检查并上传报告，保留 14 天。失败不被上传步骤掩盖。

## 验证证据

- 最终完整套件：`python3 -m pytest -m "not online"`，退出 0，1751 passed、6 skipped、115 warnings，耗时 211.94 秒。总覆盖率 91.20%。配置收集修正后首次完整运行出现既有沙箱系统时间回拨：test_experiment_report_and_panel_include_error_analysis 期望 logic_error=2，实际为 1；日志记录 SandboxResult.execution_time=-0.11969995498657227，原因是沙箱以 time.time() 差值计算耗时。此前两次完整运行通过，单独复测该用例再次通过（1 passed）。该异常与覆盖率配置无关；保留失败日志 /tmp/issue158-clock-failure.log，未修改生产计时逻辑。完整复跑最终通过，未跳过或改写该测试。
- 分模块门槛：`python3 -m coverage report --include="src/*" --fail-under=90` 退出 0，10856 行、1038 未覆盖，90.44%；`python3 -m coverage report --include="api/*" --fail-under=81` 退出 0，5066 行、363 未覆盖，92.83%。HTML 存在；XML 仅包含 162 个业务文件，src/models.py、api/models.py 和动态迁移路径均保留。
- 临时真实 coverage 样例验证：src 达标通过；API 不足退出 2、达标退出 0；无模块或缺失数据退出 1；XML 包含未导入普通模块、动态迁移和未执行 namespace 迁移文件，仅包含 src/api 路径。关闭 namespace 选项后样例失败，证明能捕获遗漏。
- 配置/风格：TOML/YAML 解析、ruff、black、显式编码检查、git diff --check、OpenSpec strict validate 通过。
- 构建：pip wheel --no-deps --no-build-isolation 成功；本机未安装可选的 build 前端，改用现有 pip 构建，无新增工具。
- 最终独立集成审查：无剩余 actionable findings。审查中发现的动态迁移和未执行 namespace 文件遗漏已修复并用样例验证。

## 限制与既有问题

- 本地未执行远端 GitHub Actions，无法据此声称六个环境均已通过。
- 真实 Redis/Celery、Docker 和可选在线用例按环境跳过；离线覆盖率不代表真实服务可用性。
- 补充执行 mypy src/ --ignore-missing-imports 得到两处既有错误：api/files/parsing.py:93（SafeLoader 类型缺失，本机未安装 types-PyYAML）和 api/progress.py:139（unused-ignore）。用 main 原配置复现完全相同结果；相关源码与类型检查配置未变更，不属于本次覆盖率配置交付。本次未宣称类型检查通过。

## 轻量验证检查

- PASS：3 项任务完成，范围与三个实现文件（配置、CI、README）一致。
- PASS：wheel 构建成功，未改变运行时依赖或 API。
- PASS：完整离线测试和两个分模块覆盖率检查通过。
- PASS：生成终端、HTML、XML 报告，并验证路径、范围与无数据失败路径。
- PASS：未新增密钥、unsafe 操作或生产逻辑。
- PASS：最终独立集成代码审查无剩余问题。

结论：本次覆盖率变更 PASS，可进入归档前用户确认。未执行远端 CI，且补充类型检查中的既有问题不计作本次已通过的检查。
