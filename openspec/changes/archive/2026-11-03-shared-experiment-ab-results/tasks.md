## 1. 结果根与启动校验

- [x] 1.1 新增 `api/results.py`（`results_root`、`ensure_results_root`、`resolve_results_path`），在 `Settings` 与 `.env.example` 增加 `RESULTS_ROOT`；API lifespan 与 `src/celery_app.py` 启动时校验可写。验证：单位测试覆盖默认/自定义/相对解析、历史 `results/...` 映射、目录不可写时报明确错误。

## 2. 实验与 A/B 使用共享根

- [x] 2.1 实验与 A/B 的 `output_dir`、`checkpoint_dir` 改为基于 `results_root()` 的绝对路径；结果/对比/面板读取先用 `resolve_results_path` 解析历史相对路径。验证：API 测试把 `RESULTS_ROOT` 指向临时目录，执行完成后切换 cwd 仍能读取结果、对比与面板，且产物位于共享根。

## 3. 部署资产与文档

- [x] 3.1 `Dockerfile.api`、`Dockerfile.worker` 创建并授权 `/app/results`；两套 compose 为 api/worker 挂载 `results_data:/app/results` 并声明卷；同步 `.env.example`、`docs/deployment/async-tasks.md`、`docs/deployment/deploy.md`。验证：部署配置测试断言卷、目录与字段，`yaml.safe_load` 可解析。

## 4. 验证

- [x] 4.1 运行相关 pytest、格式与类型检查，以及 `comet classic openspec -- validate shared-experiment-ab-results --type change --strict --no-interactive`。验证：目标测试通过、工作区改动文件格式检查通过、OpenSpec 校验通过。
