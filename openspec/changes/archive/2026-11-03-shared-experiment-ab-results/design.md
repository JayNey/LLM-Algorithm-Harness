# 实验/A/B 结果共享卷设计

## Context

实验与 A/B 的 Celery 任务在 worker 进程执行，完成后把 `output_dir` 写回业务库；结果、对比与面板端点则由 API 进程按该路径读取。此前路径是相对于进程 cwd 的 `results/...`：

- API 与 worker 在 compose 中是两个容器，只有 `uploads_data` 和 `task_data` 是共享卷；
- 两个镜像都没有创建 `/app/results`，非 root 的 `harness` 用户无法写入；
- worker 重启或多副本后，暂停恢复所依赖的 `execution/` 检查点随容器文件系统消失。

因此“completed 但结果不可读”和“恢复找不到检查点”是同一个存储边界问题。

## Goals / Non-Goals

Goals：让实验/A/B 的结果、对比、面板和检查点在 API 与全部 worker 之间可用；配置可覆盖；目录不可写时启动即失败；容器/编排/文档/测试同步。

Non-Goals：不改变执行结果内容或统计口径；不迁移历史 `results/` 文件；不把产物写入数据库或对象存储；不改 API 响应与前端。

## Decisions

1. **结果根可配置且与 cwd 无关**：新增 `api/results.py`，提供 `results_root()`、`ensure_results_root()`、`resolve_results_path()`。`Settings.RESULTS_ROOT` 默认 `results`；相对值统一相对仓库根解析，绝对路径原样使用，使 API 与 worker 在不同 cwd 下仍指向同一位置。
2. **写入路径全部根化**：实验输出/检查点为 `<root>/experiments/api/{id}/execution`，A/B 为 `<root>/ab-tests/api/{id}/execution`；两者都通过 `results_root()` 生成绝对路径。既有“checkpoint_dir 即输出目录”的语义保持不变。
3. **读取兼容历史相对路径**：新增相对路径解析：绝对路径直接使用；`results/...` 这类历史相对路径去掉 `results/` 前缀后映射到当前 `RESULTS_ROOT`；其他相对路径也相对 `RESULTS_ROOT` 解析。新建记录的 `output_dir` 为绝对路径，因此共享卷挂载在同一路径即可跨进程读取。
4. **启动可写性检查**：`ensure_results_root()` 创建目录并用临时探针文件验证可写，失败抛出带路径的 `RuntimeError`。API 在 lifespan 起始调用；`src/celery_app.py` 在模块加载（worker 启动入口）时调用，确保 worker 不会带着不可写根开始消费任务。
5. **部署资产**：两个镜像创建 `results` 并 `chown harness:harness`；两套 compose 为 api、worker 挂载 `results_data:/app/results` 并声明命名卷；`.env.example`、`docs/deployment/async-tasks.md` 与 `docs/deployment/deploy.md` 同步。
6. **测试**：单测覆盖根解析、不可写报错与历史相对路径映射；API 测试把 `RESULTS_ROOT` 指到临时目录，实验/A/B 完成后切换 cwd 仍能读取结果、对比与面板；部署测试校验卷、镜像目录和 `.env.example` 字段。

## Risks / Trade-offs

- 共享卷要求所有进程使用同一 `RESULTS_ROOT` 与相同挂载路径；不同挂载路径的部署不在本次范围，文档会明确约束。
- 历史产物未迁移；旧记录仍可通过相对路径映射在默认布局下读取，但不保证任意自定义根都能找到旧文件。
- 命名卷不提供跨主机复制；多主机 worker 需要平台层提供共享存储，沿用文档既有“可共享结果卷”前提。

## Validation

- 单测：默认/自定义 `RESULTS_ROOT` 解析；相对历史路径映射；目录不可写时启动检查报错。
- API 测试：实验与 A/B 在 `RESULTS_ROOT` 下产出后，换 cwd 仍可 200 返回结果、对比与面板；`output_dir` 指向共享根。
- 部署测试：两套 compose 的 api/worker 都挂载 `results_data:/app/results`，顶层声明卷；Dockerfile 创建并授权 `results`；`.env.example` 含 `RESULTS_ROOT`。
- 运行相关 pytest、格式/类型检查与 OpenSpec 校验。
