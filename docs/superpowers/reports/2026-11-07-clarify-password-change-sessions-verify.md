# 改密后会话说明验证

变更 `clarify-password-change-sessions`，实现提交 `a39d188a`。[GitHub #377](https://github.com/JayNey/LLM-Algorithm-Harness/issues/377)

## 结论

PASS。规模评估将 12 个 Comet 和 OpenSpec 产物纳入文件数。实际修订涉及两个文档来源、一个任务，按轻量模式验证。

## 检查结果

1. **任务完成**。OpenSpec 任务 1/1 已勾选，严格校验通过。
2. **范围一致**。API.md、生成的 OpenAPI 改密操作和 `new_password` 字段均说明当前会话与其他已登录会话继续有效。指南与操作说明明确令牌仍按原规则使用，字段说明包含 12–1024 个字符的限制。
3. **编译通过**。`python3 -m compileall -q api` 返回 0。Black、Ruff 和 Git 空白检查通过。
4. **回归通过**。`python3 -m pytest -q --no-cov tests/test_api_auth.py tests/test_api_documentation.py` 通过 105 项。临时 SQLite 的 HTTP 实测中，改密返回 204，当前与另一独立会话的原访问令牌均返回 200，原刷新令牌均可轮换且轮换后重放返回 401。旧密码登录返回 401，新密码登录返回 200。
5. **安全检查通过**。改动限于说明文字和流程记录。核对了现有会话有效期、刷新轮换和旧密码失效的行为。
6. **集成检查**。人工对照任务、最终文档 diff 和实际 OpenAPI 输出。Tweak 的 `review_mode: off` 跳过独立自动审查。
