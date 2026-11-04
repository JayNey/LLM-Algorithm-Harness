## Context

Host 和 Docker function wrapper 均生成随机 marker，并把 marker 传给同一个解析器。解析器当前缺少 marker 时无条件回退 stdout，造成提前正常退出的假阳性。

## Decisions

保持专用 stderr 通道和 JSON 解析逻辑，在 stdout 回退处增加 result_marker is None 条件。显式 marker 缺失返回现有结构化 runtime_error；非法 payload 不回退 stdout。不改 stdin/stdout 分支。

## Validation

先编写失败回归并记录 RED，再实施最小修复。解析器覆盖缺失、错误、非法 marker payload、合法 JSON（含 null）及 legacy；Host 实跑打印后退出；Docker 提供 mock 通道边界测试和受 RUN_DOCKER_TESTS 控制的真实容器回归。已有成功 Docker mocks 改为产生本次 wrapper 的实际 marker，避免依赖漏洞。运行相关测试、全套测试、ruff 和构建；如 Docker 环境不可用如实报告，不当作通过。

## Spec 同步

execution-protocol 的既有定义仍在未归档 change 中，main spec 尚不存在。本 change 使用 ADDED 单独命名的“显式函数结果通道必须完整”要求，补充已有能力的严格通道契约，避免 MODIFIED 指向不存在的主规范要求；不修改其他 change。
