## 1. 服务预设与密钥边界

- [ ] 1.1 先增加 siliconflow 预设的 Mock 测试（默认 base_url、密钥回退顺序、显式覆盖、既有 provider 不回归），再在模型客户端接入 siliconflow 分支
- [ ] 1.2 先增加模型列表与连接检查的 Mock 测试（成功列表、失败原因、手动配置引导、规模未知标注、无计费说明），再实现查询方法与错误映射

## 2. CLI、配置与文档

- [ ] 2.1 先增加 `--list-models` / `--check-connection` 的参数测试，再接入 CLI 入口（含计费说明与失败引导）
- [ ] 2.2 更新 `config.example.json` 无密钥示例与 README 三策略调用说明；注册 `online` 标记并补在线单题验证用例（无凭证自动跳过）

## 3. 验证

- [ ] 3.1 运行全量测试、静态检查与 OpenSpec 严格校验
