## Why

`_KEY_VALUE` 对非敏感键的赋值返回原样后，扫描从匹配终点继续：当非敏感赋值的未加引号值与后续敏感赋值的 `key:` 之间没有空白分隔时（traceback 源语句最常见），敏感赋值前缀被整体吞掉，带引号凭据漏脱敏。#343 的验证报告已把该缺口记录为契约限制；本修复关闭它。

## What Changes

- 文本赋值扫描改为逐匹配处理：非敏感键不再整体消费匹配文本，而是从匹配内部重扫，使紧随其后的敏感键赋值可见并被脱敏。
- 非敏感赋值的保留行为不变，不产生新的误报替换。
- 更新 HTML 报告 traceback 契约测试：来源语句中的带引号凭据从「仅转义」升级为「已脱敏」。
- 补 `secret-redaction` 文本扫描回归测试（traceback、JSON dump、未引号值与非误报形态）。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `secret-redaction`：新增赋值扫描不得吞噬相邻凭证赋值的验收场景。

## Impact

- 仅影响 `src/utils/secrets.py` 的文本扫描路径与相关测试；调用方（日志、异常记录、报告导出）契约保持不变。
