## 1. 后端

- [x] 1.1 实现掩码计算、`auth_keys.masked_preview` 列迁移，并在创建密钥时写入；扩展 `KEY_FIELDS` 与测试
- [x] 1.2 创建密钥的 API 测试断言列表响应含掩码且不含明文

## 2. 前端

- [x] 2.1 解析 `masked_preview` 并在密钥列表行展示；更新 Node 测试

## 3. 验证

- [x] 3.1 运行相关 pytest 与 `cd frontend && npm test`、生产构建；OpenSpec validate
