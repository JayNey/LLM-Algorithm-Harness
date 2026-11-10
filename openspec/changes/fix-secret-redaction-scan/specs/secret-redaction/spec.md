# secret-redaction Specification

## ADDED Requirements

### Requirement: 赋值扫描不吞噬相邻凭证赋值

文本脱敏 MUST 逐个识别 `key: value` 与 `key=value` 赋值形态：非敏感键的赋值不得作为整体匹配吞掉紧随其后的敏感键赋值；敏感键的带引号与未引号值 MUST 被替换为脱敏占位符，非敏感赋值的值保持原样。

#### Scenario: traceback 源语句中的带引号令牌

- **WHEN** 异常文本形如 `RuntimeError: token: "sk-secret"`，即非敏感赋值的值与敏感赋值之间无空白分隔
- **THEN** 脱敏结果为 `RuntimeError: token: "[REDACTED]"`，原始值不再出现在任何输出通道

#### Scenario: 非敏感值不受影响

- **WHEN** 文本包含 `warning: token count exceeded`、`elapsed: 12:30:45` 等含冒号的普通内容
- **THEN** 脱敏前后文本一致，不产生误报替换
