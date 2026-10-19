# Design: 密钥列表掩码

## 掩码算法

创建密钥时由明文计算一次并持久化：

- 取密钥 UTF-8 字符串的前缀，长度 `min(7, len(key))`。
- 总展示长度固定为 35：前缀 + 若干 `*` 填满剩余位；密钥短于 35 时仍只展示前缀与星号，不补全真实字符。
- 禁止单独暴露末尾四位；禁止在 API 中返回除 `masked_preview` 外的任何密钥片段。

示例：`sk-live-abc...` → `sk-live**************************`（7 + 28）。

## 存储

`AuthStore` 启动时对 `auth_keys` 执行 `PRAGMA table_info`，缺失则 `ALTER TABLE ... ADD COLUMN masked_preview TEXT`。`INSERT` 写入该列；已有行保持 `NULL`。

`KEY_FIELDS` 增加 `masked_preview`。`key_metadata` 原样透出（可为 `null`）。

## 前端

- `ApiKeyRecord.masked_preview: string | null`
- `readApiKey` 接受可选字符串字段；非法类型则整条记录解析失败。
- `KeyRow` 在名称下方渲染掩码（仅当非空）；保留「密钥保存后不再显示」说明，指添加表单不保留输入。

## 测试

- Python：掩码函数单元测试 + 创建密钥后列表含 `masked_preview`。
- Node：`readApiKey` / 展示辅助函数测试。
