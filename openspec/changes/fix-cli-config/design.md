## Context

当前可执行逻辑集中在 `src.main` 的 argparse 入口，但打包脚本错误地引用 `src.cli:cli`。`src.main` 又单独实现了仅支持 JSON 的加载器，而 `src.utils.config` 已通过 YAML 解析器兼容 YAML 和 JSON。现有参数默认值会掩盖用户是否显式传参，无法正确应用配置优先级。

## Goals / Non-Goals

**Goals:**

- 让安装命令与模块命令复用同一个 `main()`。
- 在进入 Harness 前得到唯一、已验证的 `HarnessConfig`。
- 用行为测试覆盖配置优先级、筛选参数和错误条件。

**Non-Goals:**

- 不把 argparse 迁移到 Click。
- 不改变模型请求协议、题目 Schema 或报告模块。
- 不实现跨平台密钥管理；继续使用模型客户端现有的环境变量回退。

## Decisions

1. **保留 argparse，并把打包入口改为 `src.main:main`。** 这能最小化行为变化。另建 `src.cli` 或迁移到 Click 会制造两套入口或扩大改动范围。
2. **让参数默认值使用 `None` 表示“未显式提供”。** 读取配置文件的原始映射后，先合并非 `None` 的 CLI 值，再构造 `HarnessConfig`，从而允许 `--dataset` 补足配置文件缺失的数据集，并防止默认参数覆盖文件值；没有配置文件时再创建默认配置。
3. **统一调用 `src.utils.config.load_config`。** YAML 的 safe loader 能读取 JSON 子集；加载器额外验证顶层必须是映射，避免空文件或列表产生难懂异常。
4. **在 CLI 配置解析阶段验证策略和 limit，在 Harness 加载阶段验证空筛选结果。** 前者无需启动评测即可发现，后者只有读取实际题集后才能确定。
5. **保留 `--output`，同时接受文档和旧测试中出现的 `--output-dir` 别名。** 两者写入同一个目标字段，不引入迁移成本。

## Risks / Trade-offs

- [配置文件中的未知额外筛选键会在调用加载器时失败] → 保持 Pydantic/函数签名的显式失败，不静默忽略拼写错误。
- [YAML 可以解析 JSON，但错误类型来自 YAML 库] → CLI 统一捕获并输出错误文本，文档只承诺格式支持，不承诺具体异常类。
- [筛选为空从零结果报告变为失败] → 这是 Issue 的明确验收行为，并通过 Harness 测试固定。

## Migration Plan

现有 `python -m src.main --dataset ...` 和 `--output` 命令继续可用。重新安装项目后，`harness` 命令即可使用；回滚只需恢复打包入口和本次 CLI 解析改动。
