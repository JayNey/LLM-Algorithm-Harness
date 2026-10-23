# #157 Docker 沙箱容器资源验证报告

日期：2026-10-23（Asia/Shanghai），change 于 2026-10-22 开始。工作基线 main 8d8714f355922eeacd2b7f7d03384db41484d5b4，已包含 PR #240。本轮仅补 #157 的容器资源子范围，沿用用户既定增量 Tweak 与个人分支。

## 前置核对与选择

#240 已合并且十项 CI 全通过，#223 的实现已在 main，issue 仍开放并不代表代码尚未合并。后续 #226 仍等 #224/#225；#225 的公开记录只有观察器核心，页面集成依赖 #224，main 尚无 useEvaluation/observer 完整接入。#229 还有详情、结果、入口等前置，#232 仍等 #231。本轮继续分配给 eZ-CY、已有基础依赖满足的 #157，没有领取其他人的工作或提前完成受阻的前端任务。

## 改动与准确口径

- 新沙箱 Docker 命令加入固定标签 io.llm-algorithm-harness.sandbox=v1，网络/只读/权限/CPU/内存/PIDs 等限制保留。标签是观测选择器，不是用户认证依据；旧版无标签容器不计入。
- 管理员 system/status.containers 可显式启用当前 API 进程 Docker context 的只读 ps/stats 采样。默认 not_configured/disabled，公开健康、401、403 和禁用读取零采样。
- 仅返回摘要 ID、CPU 百分比、CLI 显示内存转换字节/限额/百分比及 PIDs；不返回名称、原始 ID、镜像、环境、命令、挂载或原始异常。
- 两命令共享0.5–10秒预算，输出接受上限64KiB，默认32/最多64个样本；超量为 partial/sample_limit。复用进程树终止与输出限制工具，清理另有有界余量（两个 pipe join 各最多5秒）；关闭等待当前预算加12秒，不停止任何被观测容器。
- 缺测为 null，成功枚举为空才返回0/[]；ps 与 stats 非原子。容器完成/退出会保留枚举和可用读数并标 partial/stats_failed，不误判整个 Docker daemon 故障。
- 单 API 进程一个在途采样，成功/失败均缓存并展示年龄；过期并发请求得到 refresh_in_progress，关闭后不再开始采样。cluster_complete=false，不生成全局 CPU/内存总值。
- 数值是 Docker CLI 的舍入显示值；Linux 缓存扣除、PIDs 的线程口径和 Windows daemon 缺失列遵循 [官方 stats 协议](https://docs.docker.com/reference/cli/docker/container/stats/)。不外推到 API 主机或生产集群。

## 测试与真实验证

- RED：沙箱 Docker 命令缺少 --label，单项断言失败；修复后首批46项容器/沙箱回归通过。
- HTTP/OpenAPI/v1/端点回归：896 passed。保留已有 API v1 契约基线，仅增补开放响应的示例，未修改冻结基线或门禁。
- 首轮完整离线：2967 passed、8 skipped，91.81% 合计覆盖率，317.16秒。此结果在 P2 修复前，仅作历史记录。
- Bugbot 完整分支审查发现1个 P2：--rm 容器在 inventory 后退出时，stats 非零导致错误丢弃全部读数。新增两项 RED 失败，再保留合法 stdout/枚举、未知行设 null；修复后定向93 passed、2 skipped。
- Bugbot 复审无剩余发现；审查者独立定向70 passed、3 skipped（--no-cov）。第一次审查定向68项通过但命令触发全库 coverage 门禁失败，该数字不是全库覆盖率；最终完整回归随后重新生成覆盖率证据。
- 最终完整离线：2969 passed、8 skipped、197 warnings，273.59秒；src/API 合计91.80%。命令：python -m pytest -m 'not online' -o faulthandler_timeout=60。原始日志 /private/tmp/container-full-final.log。
- 独立分项门禁均退出0：src 90.58%（要求90%）；API 93.98%（要求81%）。未降低门禁。
- Ruff 全仓、Black 333文件、显式编码扫描0处、OpenSpec strict 通过。mypy src 97文件通过；改动API四文件 --follow-imports=silent 检查通过。
- 扩大到完整 api/monitoring + route 的类型检查会跟随导入并暴露未修改的 api/routes/tasks.py 与 evaluations.py 中4个错误（无参类型注解、created_at/updated_at 的 Any|None、Returning Any）；未把该扩大检查写成通过，未修改无关路由。日志 /private/tmp/container-mypy-api.log 与 container-mypy-changed.log。

## 真实 Docker 层级

[公开脱敏证据](assets/container-resources-2026-10-23/real-docker.json) 在干净的提交 73c6f1c883f4f5ba920e2ccd10c0ab7ecafa6729 实际运行，退出0：

- 用现有 SandboxExecutor 命令构建器启动两只本轮自建的受限测试容器，一带标签，一移除标签。
- 采集实际 CPU、内存、256MiB 限额、PIDs，确认无标签容器不在响应，原始名称和 ID 不泄露，缓存可复用；采样后两只容器仍在运行。
- 再由测试夹具在 ps 与 stats 之间主动移除自建标签容器，真实 Docker 返回非零；采样响应为 partial/stats_failed，保留已成功的枚举并给缺测 null。
- finally 仅清理这两只自建容器，测试容器已清理；没有提交业务任务、调用 LLM 或运行其他用户容器的生命周期命令。

复现：MONITOR_CONTAINER_TESTS=1 python -m pytest tests/test_monitoring_container_integration.py --no-cov -q -s。默认离线/CI 跳过此 opt-in，环境需自行提供 Docker daemon 和 python:3.11-slim。该证据是实际 Docker CLI + 离线 HTTP 授权/响应测试，不是生产集群或 API→Redis/Celery→模型→结果的真实端到端联调；Windows daemon 语义仅有边界单测，没有真实 Windows Docker 测试。

## 规格与交付

禁用/身份边界、标签范围、空/缺失/异常数据、预算/输出/样本限制、并发/缓存/关闭均有对应测试；成功与容器退出竞态另有真实 Docker 证据。proposal、design、delta spec 与实现一致，Tweak 未新建完整 Classic 技术设计。

运行期间 main 又新增 #241（worker running 检查点恢复），只涉及其他 worker 文件及测试，不与本轮文件冲突；本次完整回归的代码基线仍明确为8d8714f，不冒称对新主线已重跑全库。交付 PR 的 base 为 main，最新平台结果按 PR 头与检查记录核对。

#157 的 LLM 性能、跨 worker 缓存和新增配额等仍未完成，保持开放。新提交显式排除 .comet/.claude/.codex/.agents/skills-lock.json，未自动归档或合并。

PR #243 已创建，base=main，Refs #157；本轮功能、回归、真实 Docker 与复审证据已提交。平台 CI 的结论以最终头为准，创建 PR 不代表 CI 已完成。

Runtime 实际编译检查成功（95f2b44b-b795-4289-a153-61db1e0a03a7.log），定向93 passed、2 skipped（f391af05-d3ef-44e5-a9b3-4d317e2696d5.log）。build 14/14、verify 5/5 守卫通过，由 Runtime 记录 verify_mode=full、verify_result=pass、phase=archive，归档确认保持 pending。
