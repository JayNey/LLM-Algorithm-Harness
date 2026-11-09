# 登录与注册字段可访问性验证

变更 `fix-auth-form-accessibility`，实现提交 `c6d9df7f`。OpenSpec 任务 1/1 完成，`frontend/auth-session` 的增量规格通过严格校验。 [Issue #429](https://github.com/JayNey/LLM-Algorithm-Harness/issues/429)

## 验收结果

- 修复前，Chromium 在登录和注册页的中英文组合中均返回空字段名称及缺失的错误描述，新增 8 项断言全部失败。
- 修复后，Chromium 在 320px 下确认登录的身份、密码和注册的用户名、邮箱、密码、确认密码均有与可见标签一致的中英文名称。Tab 依次到达各字段，回车触发表单校验，各无效输入均在可访问树中提供对应的错误描述及无效状态。错误展开后页面无横向溢出。
- 生产构建浏览器复验覆盖 320px 下由登录进入注册、有效输入回车发出登录 POST、HTTP 400 字段错误关联，以及清除旧校验错误后的可访问属性。
- 语言切换冒烟确认输入不会重新挂载，已填写内容和错误文案随语言切换正确保留或更新。
- 两个表单使用原生标签关联和显式错误描述，符合精简设计及增量规格。Tweak 状态为 `review_mode: off`，以最终改动核对和上述测试作为验证证据。

## 验证命令

- `npm test` 通过 344 项。
- `npm run lint`、`npm run format:check` 和 `git diff --check main...HEAD` 通过。
- `npm run build` 通过。Vite 提示现有 CompareCharts 构建产物超过默认大小阈值。
- `node scripts/verify-direct-load.mjs` 使用本机 Chrome 和生产预览，通过 75 项断言，失败和未知 API 请求均为 0。
- `node scripts/verify-i18n.mjs` 使用本机 Chrome 和生产预览，通过 11 项检查。
- `comet classic openspec -- validate fix-auth-form-accessibility --strict` 通过。

## 结论

PASS。可归档。
