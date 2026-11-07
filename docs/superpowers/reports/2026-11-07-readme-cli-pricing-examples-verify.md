# README 导入与定价示例验证

[GitHub #378](https://github.com/JayNey/LLM-Algorithm-Harness/issues/378) · 实现提交 `131b10d0` · 结论 **PASS**

1. 任务 **通过**。OpenSpec 任务 1/1 完成，严格校验通过。本次为说明修正，使用 `skip_specs: true`。
2. 范围 **通过**。实现差异仅为 README。规模脚本把 OpenSpec 和 Comet 产物计入文件数，按单个文档改动采用轻量验证。
3. 构建 **通过**。用 `PIP_NO_INDEX=1 python3 -m pip wheel --no-deps --no-build-isolation --wheel-dir /tmp/issue-378-verify-wheel.EJuJTr .` 构建 wheel。
4. 测试 **通过**。导入、定价、离线评测、HTML 和 Markdown 报告相关的 80 项 pytest 用例通过。CLI 帮助检查通过，从 README 提取的导入命令在本地夹具中预览出一道困难题。离线评测通过 `latest.json` 定位汇总，核对了自定义价、已知零价和未知费用的汇总及逐次调用标记。
5. 安全 **通过**。示例引用配置文件和供应商密钥，差异中无密钥或危险操作。验证使用本地缓存文件及模型响应替身。
6. 集成审查 **通过**。已对照任务、CLI 解析、价格匹配和结果文件检查 README 差异。`review_mode: off` 为当前 tweak 的自动审查设置。
