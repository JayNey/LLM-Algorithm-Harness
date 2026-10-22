# fix-compose-sandbox-mount 验证报告

结论：PASS（配置修复及自动化回归通过；本机无 Docker daemon，真实容器端到端验证未执行）。

- 分支：`hotfix/20261022/fix-compose-sandbox-mount`
- 实现提交：`984dedc`、`752e0e8`
- 基线：`f73fe710e742eadb84eba695853cb8c940957bdc`
- 验证模式：light。自动规模评估因 12 个 Comet/OpenSpec 状态产物加 4 个实现文件共 16 文件而选 full；实际修复仅两份 Compose、部署指南、部署测试，3 tasks、0 delta，依照 verify_mode 覆盖机制采用轻量验证。
- 审查模式：hotfix 默认 `review_mode: off`，跳过自动集成代码审查；仍核对安全边界、最终 diff 与根因。

## 六项检查

1. PASS：tasks.md 三项全部完成，已保留 RED/GREEN 证据。
2. PASS：实现变更与任务相符；其余提交文件均为本 change 的工作流元数据，未混入用户修改。
3. PASS：真实 Docker Compose CLI 解析开发/生产 × 默认/自定义目录共 4 组模型；TMPDIR、bind source、target 同值，create_host_path=false。`python3 -m compileall -q tests/test_deployment_config.py` 通过。本次无应用源码或镜像构建配置变更，不声称完成镜像构建。
4. PASS：`python3 -m pytest tests/test_deployment_config.py tests/test_sandbox_executor.py tests/test_sandbox_docker.py tests/test_harness.py --no-cov -q`：116 passed、2 skipped。verify 阶段另跑部署测试 39 passed。`--no-cov` 用于定向回归，不将部分测试冒充全仓覆盖率结果。
5. PASS：未增加密钥或权限；worker 保持非 root，共享根目录建议 UID/GID 1000、0700；候选代码继续只读挂载各自随机子目录，未暴露共享根目录。缺目录拒绝 Compose 自动创建 root 属主目录。
6. PASS：自动 code review 按 review_mode=off 跳过。检查中发现新测试需要跨平台解析 Linux 路径与 POSIX 权限，于 verify-fail 返回 build，改用 PurePosixPath、仅在 POSIX 检查权限位，重新提交后再验证。未声称在 Windows 实际执行。

## 根因消除与回归

原 `_run_in_docker` 在 worker 私有临时目录写 runner 后，把其路径直接交给宿主 Docker；两份原 Compose 都未共享该目录。新增回归在修复前共 8 failed，均因 TMPDIR 缺失而无法满足宿主目录可见性。

现在 worker 的 TMPDIR 有相同绝对路径的可写 host bind，原执行器无需路径换算。4 个配置断言覆盖开发/生产与默认/自定义路径；4 个执行回归使用实际 tempfile、runner 生成、Python 函数和 stdin/stdout，模拟宿主 bind source 解析，检查权限、只读沙箱挂载、重复执行目录唯一性与清理，全部通过。

`python3 /tmp/verify-compose-sandbox-20261022.py` 调用真实 `docker compose --env-file /dev/null -f <file> config --no-env-resolution --format json`；使用仅校验用的数据库口令及 GID，不读取部署密钥。默认 `/tmp/llm-harness-sandbox`、覆盖 `/srv/llm-harness/sandbox` 在两套 Compose 中均解析一致。

## 其他验证

- `python3 -m black --check tests/test_deployment_config.py`：通过。
- `python3 -m ruff check tests/test_deployment_config.py`：通过。
- `git diff --check`：通过。
- `comet classic openspec -- validate fix-compose-sandbox-mount --strict`：通过；修复恢复原行为，skip_specs=true，无 delta。

## 环境边界与部署步骤

`docker info --format '{{.ServerVersion}}'` 报本机 Docker socket 不存在，未运行真实 Docker 隔离测试（2 项 opt-in 用例跳过），也未构建镜像。没有将此环境限制伪装成容器验证通过。

部署者需在 Linux Docker 宿主执行 `sudo install -d -m 0700 -o 1000 -g 1000 /tmp/llm-harness-sandbox`（或 `.env` 中 SANDBOX_WORKDIR 的绝对路径），拉取默认沙箱镜像，重建 worker。部署指南已提供 worker 内 TMPDIR 可写与 tempfile 不回退检查，以及真实 `SandboxExecutor.health_check()` 命令。

## 状态与归档

工作区未提交内容仅为本 change 验证报告及 Comet 阶段状态。branch_status 保持 pending。通过 verify guard 后等待用户按 comet-archive 最终确认归档及交付方式。

### 归档交付选择

用户已明确选择 C：完成归档、创建唯一归档提交、推送当前绑定分支并创建 PR。归档已移动至 `openspec/changes/archive/2026-10-22-fix-compose-sandbox-mount`；按此授权将归档状态置为 branch_status=handled。该字段表示交付方式已确认，推送及 PR 创建的实际结果以最终交付为准。
