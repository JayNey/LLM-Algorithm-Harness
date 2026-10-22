## Why

官方开发与生产 Compose 中，worker 通过宿主 docker.sock 创建兄弟沙箱容器。执行器在 worker 私有 `/tmp` 下写入 runner，却将该路径作为宿主 bind source，宿主无法读取 runner，导致预检及评测失败（blocker）。

## What Changes

- 将 worker 的 TMPDIR 指向宿主共享目录，bind source 与 worker target 使用完全相同的绝对路径。
- 两套 Compose 使用同一默认值，支持部署者覆盖目录；缺失目录时拒绝自动创建 root 属主目录。
- 增加部署回归测试及 Linux 非 root 目录初始化、实际预检说明。

## Capabilities

无新增 capability；恢复 deployment / sandbox-preflight 已有承诺，不改变验收语义，不添加 delta spec。

## Impact

实现范围：两份 Compose、tests/test_deployment_config.py、docs/deployment/deploy.md。不涉及应用 API、数据库或沙箱隔离策略变更。

## 根因与复现

`_run_in_docker` 使用 `tempfile.TemporaryDirectory`，`_build_docker_command` 将其绝对路径原样传给 `docker run --mount type=bind`；现有两份 Compose 只共享 uploads/data/socket，没有覆盖临时目录。先新增配置与执行链路回归，记录 RED 后修复。

当前宿主 Docker daemon 未运行（docker info 报 socket 不存在），真实容器验证需在 Docker 宿主补跑；本轮自动化模拟宿主路径解析并实际运行生成 runner。

### 失败证据与结果

- 修复前：`python3 -m pytest tests/test_deployment_config.py -k 'sandbox_tmpdir or sandbox_runner' --no-cov -q`，8 failed；两份 Compose 都缺少 TMPDIR，无法定位共享 bind，失败与报告根因一致。
- 修复后：部署、执行器、Docker 后端、harness 四组测试合计 116 passed、2 skipped（真实 Docker 用例）。开发/生产默认与自定义目录共四种配置经真实 `docker compose config --no-env-resolution --format json` 解析，TMPDIR/source/target 一致。
- 构建检查以 Compose 模型解析及 Python compileall 为本次配置改动的有效检查；未声称完成镜像构建或真实容器执行。
