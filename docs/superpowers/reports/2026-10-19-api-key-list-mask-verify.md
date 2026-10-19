# api-key-list-mask 验证报告

- **change**: `api-key-list-mask`
- **workflow**: tweak
- **结论**: PASS
- **review_mode**: off（tweak 预设，未派发集成审查子代理）

## 证据

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 掩码单元 | `python3 -m pytest tests/test_key_preview.py tests/test_api_auth.py::test_keys_encrypted_isolated_editable_and_survive_restart -q --no-cov` | 3 passed |
| 前端单测 | `cd frontend && npm test` | 84 passed |
| 前端构建 | `cd frontend && npm run build` | exit 0 |
| OpenSpec | `comet classic openspec -- validate api-key-list-mask --type change --strict` | valid |

## 规格对照

- 创建密钥后 `GET /api-keys` 含 `masked_preview`，响应无完整 `KEY` 明文与 `ciphertext`（`test_keys_encrypted_isolated_editable_and_survive_restart`）。
- 掩码为前 7 字符 + 星号至长度 35；轮换密钥时 `update_key` 更新 `masked_preview`。
- 前端 `readApiKey` 解析 `masked_preview` 且不保留 `api_key`；列表行在字段非空时渲染掩码。
- 无 `masked_preview` 的旧库行保持 `null`，不显示掩码行（delta spec「旧记录无掩码」）。

## 偏差

无。
