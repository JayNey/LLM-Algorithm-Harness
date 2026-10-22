## 问题与根因

真实 Celery 基准任务的 execute_benchmark 创建 BenchmarkService 时仅传入 recover=False，未注入 AuthService。服务的 _execute 在读取运行记录前检查认证依赖，因而所有基准运行都会以 authentication service is not configured 失败。现有任务测试替换整个 execute_benchmark，构造测试也仅检查 recover=False，未覆盖真实认证路径。

## 修复目标

在 worker 中按既有实验任务模式，从 AuthSettings 创建 AuthService 并注入 BenchmarkService，恢复从持久化密钥构建 LLM 配置的行为；执行后释放服务数据库连接。补充真实任务入口的离线回归，验证所属用户密钥可解密执行，其他用户密钥仍被拒绝。

## 范围

仅修改 src/tasks/benchmark.py 与 tests/test_benchmark_task.py，无新能力、公共接口或数据库结构变更，无规格要求变更，因此不创建 delta spec。

## 工作区

用户选择新分支：hotfix/20261022/fix-celery-benchmark-auth，目标分支 main。

## 上下文插件

comet task 在读取插件状态时因 ~/.comet/plugins/state.json.lock 写入权限不足失败；按 hotfix 协议不阻断修复，未注入插件内容。

## RED 证据

2026-10-22 执行 `MPLCONFIGDIR=/private/tmp/celery-benchmark-mpl pytest tests/test_benchmark_task.py -k 'disables_recovery or disposes_engine or resolves_owned_credentials' --no-cov`：4 failed。构造断言显示 AuthService 从未创建；真实任务在合法用户密钥下返回 failed，跨用户密钥用例实际错误为 authentication service is not configured，确认在所有权校验前就失败；异常路径未释放 engine。

首次运行的真实路径测试暴露测试种子未先 flush suite 的外键顺序问题，已仅调整测试数据插入顺序，再次运行得到上述对应本 bug 的 RED 证据；尚未改动生产代码。
