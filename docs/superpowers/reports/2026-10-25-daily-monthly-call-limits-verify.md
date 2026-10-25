# 日/月调用限制验证

Change: daily-monthly-call-limits。分支：tweak/20261024/daily-monthly-call-limits。

## 完整性与一致性
- tasks 2/2 完成；proposal 目标、design 实现与 api/llm-call-metrics delta requirement 一致。
- tweak 不要求独立 Superpowers 深度 Design Doc；以 change/design.md 为设计依据。
- 新增环境变量非负校验、私有预调用钩子、BEGIN IMMEDIATE 原子双周期计数、QUOTA_EXCEEDED/503、quota 查询均有实现。
- 并发与双周期：多连接及三个子进程竞争，恰好准入上限数量，拒绝无计数写入。
- 重试及隔离：按用户隔离，失败和真实重试各计数，超额不调用 SDK；无限时保留旧行为。
- 周期边界与重启：旧计量回归覆盖午夜、闰月、月/年切换与重启；限额测试覆盖日重置仍受月限额约束、跨年重置。
- 用量查询：真实服务绑定生成后 used/limit/remaining/status 一致，另一用户零用量。
- 故障及隐私：数据库失败为 503，事务中途失败两周期回滚，私有钩子不序列化；公共 generate 保留可信额度异常。

## 自动化证据
- 初始额度测试 RED：8 failures，因配置、准入及预调用钩子尚未实现。
- 相关回归：179 passed；补充跨进程测试后专用额度集 11 passed。
- 最终审查发现数据库锁等待计入模型重试时限，补充测试复现 RED；修复后调用相关测试 44 passed。
- ruff check、black --check、python3 -m compileall -q api src、OpenSpec strict validate 均 exit 0。
- 最终认证/监控/计量/额度回归：181 passed；增加部署配置及空值覆盖后：221 passed。
- 全量首轮 python3 -m pytest -m 'not online'：3146 passed、8 skipped、1 failed，coverage 91.94% >= 90%。唯一失败为 test_deployment_config.py::TestEnvExample::test_covers_settings_fields，因注释形式额度示例未满足全字段覆盖。
- 已补充空值配置解析的 RED 测试并修正 .env.example；该测试、部署检查与相关回归 221 项通过。
- 修正后的全量离线复跑 python3 -m pytest -m 'not online' --no-cov -q：3150 passed、8 skipped、127 warnings，exit 0，314.12 秒。警告为现有依赖弃用/测试类收集提示。

## 集成审查
使用 requesting-code-review 技能派发独立 reviewer，对 c5358cf..最终实现审查；无额度绕过和 CRITICAL 问题。唯一 P2 为锁等待占用重试时限，已通过复现测试修复并验证。
Comet tweak Runtime 的 review_mode 仅接受默认 off（设 standard 后后续状态写入报 build configuration incomplete，已恢复 off）；额外独立审查仍已实际执行，结果如上。

## 环境说明
裸 pytest 收集因 tests 包导入路径失败，改用 CI 的 python3 -m pytest 后正常收集；不修改项目源码解决命令启动差异。
Comet task 可选记忆插件因全局 ~/.comet/plugins/state.json.lock 写权限不可用，不影响源码、测试及工作流阶段守卫。

## 结论
PASS。任务、功能场景、设计一致性、构建、相关回归及全量离线套件均通过；审查问题已修复，无未解决 CRITICAL/IMPORTANT。可进入归档最终确认。

## 归档交付确认
用户选择 C：归档、推送 tweak/20261024/daily-monthly-call-limits 并创建 PR。归档目录为 openspec/changes/archive/2026-10-25-daily-monthly-call-limits，主 spec 已按 delta 语义同步。
