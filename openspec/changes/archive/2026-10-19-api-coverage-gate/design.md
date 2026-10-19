## Context

已有 pytest-cov、覆盖率 90% 总门槛和 Codecov 上传。pytest-cov 的裸 --cov 会清除显式 source，需让本地与 CI 使用同一范围。真实 Redis/Celery 测试可能因服务不可达而跳过，报告不得宣称这些流程已执行。

## Decisions

- pytest 默认同时收集 src、api，保留总覆盖率 90% 下限，输出 term-missing、HTML 和 XML。
- 使用 coverage report --include="src/*" --fail-under=90 和 --include="api/*" --fail-under=81，两个独立 CI 步骤避免总覆盖率掩盖单模块回退；使用 coverage 原生 2 位小数精度，无数据时命令失败。
- coverage 从仓库根目录收集（source = ["."]），通过 report.include = ["src/*", "api/*"] 统一限定所有报告与总门槛的业务代码范围，并设置 relative_files。这样既统计未导入业务文件与动态加载的 Alembic 迁移，又保留完整相对路径，避免 src/models.py 与 api/models.py 在 XML 中互相覆盖。不使用 source_pkgs，因其漏记动态迁移模块；也不使用多个 source 目录，因其 XML 报告会剥除各目录前缀。
- 设置 include_namespace_packages = true，确保没有 __init__.py 的迁移目录中的未执行文件也计入分母；开发依赖显式声明 coverage[toml]>=7.0，匹配该选项的最低版本，不增加运行时依赖。
- CI 测试与分模块检查为独立步骤，检查和报告上传使用非取消条件，即使测试失败仍留存证据；Codecov 服务失败不替代本地硬门禁。
- 不实现自定义 XML 解析器。以临时小型真实 coverage 报告验证未导入文件仍被统计、门禁成功/失败、缺失数据的退出码。

## Risks / Trade-offs

先记录完整套件基线；若现有覆盖率不足或测试存在既有失败，明确记录并定位，不能通过忽略业务代码或降低既有 src 门槛掩盖。
