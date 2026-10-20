# 验证报告：deploy-config（issue #159 部署配置与生产环境）

- 日期：2026-10-20
- 分支：comet/deploy-config（交付目标 tweak/20261020/deploy-config）
- 基线：ab0497e（upstream/main），8 个提交，22 文件变更（+1556/−32）
- 验证模式：full（规模评估：13 任务 / 1 delta spec / 22 文件）
- 集成审查：复用 build 阶段两轮独立审查（general-purpose 只读子代理）：第一轮全量 REQUESTS_CHANGES（2 P1 + 8 P2）→ 074f6c4 修复 → 第二轮定点复审 **APPROVE**（附 2 条注释级备注，已在 80012fc 清理）。审查后增量仅注释措辞与 tasks 勾选，无行为变化，审查结论仍有效。

## 1. Completeness（完整性）

| 检查项 | 结果 | 证据 |
| --- | --- | --- |
| tasks.md 13/13 全部勾选 | PASS | `grep -c "^- \[x\]"` = 13，未勾选 0 |
| delta spec 6 条需求全部有实现载体 | PASS | 见 §2 映射表 |
| proposal 目标（8 个任务块）满足 | PASS | 容器化/编排/环境/依赖/迁移/日志/nginx/文档均有对应交付 |

## 2. Correctness（正确性）：需求与场景映射

| Spec 需求 | 实现 | 场景覆盖 |
| --- | --- | --- |
| 容器化交付 | Dockerfile.api/worker（多阶段、USER harness、HEALTHCHECK、docker:cli 复制） | test_deployment_config::TestDockerfiles（6 项）；镜像实际构建/运行依赖本地 Docker，CI 无 daemon，为静态断言 + 独立审查核线的既定验证口径（见"限制"） |
| 一键编排 | docker-compose.yml（开发全栈，redis 服务逐字节保留）/ docker-compose.prod.yml（restart、必需密钥、日志轮转、健康检查全覆盖、worker 迁移门） | TestDevCompose（4）+ TestProdCompose（9） |
| 反向代理 | deploy/nginx/nginx.conf（gzip、auth/api 双限流分区、/api/v1/ws 升级、100m 对齐、HTTPS 模板） | TestNginx（5） |
| 环境配置样例与校验 | .env.example 全字段 + 防漂移测试；生产缺密钥由 AuthSettings 校验器拒绝（上游既有行为，复审实测 Fernet 拒绝占位符，fail-closed） | TestEnvExample（3）+ 上游 auth 配置测试 |
| 结构化日志 | api/logging_config.py + LOG_LEVEL/LOG_FORMAT 字段 + create_app 接线 | test_api_logging_config（13 项，含 invalid level/format、接线防回归、JSON 透传/包装边界） |
| 数据迁移与种子 | 启动迁移（既有 EvaluationResultsService.__init__ → run_migrations）+ scripts/seed_data.py 幂等 upsert + 回滚文档（'0001'） | test_seed_data（2，重复执行不重复插入、部分更新原地生效） |

## 3. Coherence（一致性）

- design.md 关键决策 7 项全部落实：compose 双文件布局、redis 服务不动、镜像策略（python:3.11-slim 多阶段/非 root/urllib 健康检查/docker-cli）、依赖拆分与 pip-tools 文档化、种子幂等、nginx 结构、无 Docker 依赖的测试策略。
- 实现与设计的一处字面出入（SUGGESTION，已接受并记录）：设计写"日志装配在 lifespan 启动时调用"，实际接线在 `create_app()` 起始处（api/main.py:69）。行为等价——uvicorn CLI 顺序下 create_app 于导入期执行、lifespan 随后才运行，两者均晚于 uvicorn 安装默认 handler，清除动作同样有效；create_app 位置使接线可被 test_create_app_wires_logging_assembly 直接锁定（lifespan 位置反而难测）。不改动的理由：纯措辞级、修复需 reopen build 并作废全部检查证据，收益为零。
- 无 Design Doc（tweak 预设不产生 docs/superpowers/specs 文档），检查项 7 记为 N/A。
- 代码模式一致性：新 Python 文件遵循仓库约定（显式 `encoding="utf-8"`、类型标注、ruff/black 干净、mypy src/ 不受影响）。

## 4. Runtime 检查证据

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| build：`python3 -m pytest -q --cov-fail-under=0` | exit=0 | openspec/changes/deploy-config/.comet/checks/7b1748fc-….log（2674 passed, 6 skipped） |
| verify：同命令（本报告定稿后经 `comet check run verify` 采集） | 见 .comet/checks/ 最新日志 | 2674 passed, 6 skipped；全库覆盖 91.74%，api/* 94.24%（门禁 81%） |
| lint/type（CI 口径） | PASS | `ruff check .` 全绿；`black --check .` 全绿；CI mypy 范围 src/ 未触碰 |
| 安全 | PASS | 无硬编码密钥（.env.example 占位符有测试断言）；.dockerignore 排除 .env；bandit 范围 src/ 未触碰 |

## 5. 限制与偏差声明

- Docker 镜像构建与 compose 实际拉起未在本环境执行（CI/验证环境无 Docker daemon）；以 YAML/文本静态断言 + 独立审查（含 uvicorn 0.40 默认值、busybox pidof、Fernet 校验等库行为实测）替代，风险集中在"镜像可构建性"这一项，建议合并后由维护者跑一次 `docker compose -f docker-compose.prod.yml build` 冒烟。
- `FORWARDED_ALLOW_IPS="*"` 在 dev 编排下信任本机进程的 X-Forwarded-For（复审备注，纵深防御层单点，生产拓扑正确并有注释说明）。

## 结论

三维验证无 CRITICAL、无 WARNING（1 条 SUGGESTION 已记录并说明接受理由）；两轮独立审查最终 APPROVE。**验证通过，可进入归档确认。**
