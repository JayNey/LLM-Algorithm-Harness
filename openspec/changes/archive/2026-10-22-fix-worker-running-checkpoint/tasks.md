## 修复与验证

- [x] 1.1 新增 worker 丢失后重投递的真实检查点回归测试及指纹不匹配测试，记录失败证据。RED：3 failed，均因同名检查点 already exists。
- [x] 1.2 将 running 检查点纳入恢复路径，确认新增测试和相关回归、格式检查及构建通过。GREEN：新增 3 passed；相关测试 87 passed、2 skipped；ruff、black、OpenSpec strict 校验及 pip wheel 构建通过。
