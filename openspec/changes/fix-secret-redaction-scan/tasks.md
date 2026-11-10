## 1. 赋值扫描修复

- [x] 1.1 复现缺口（traceback / 无空白 JSON dump / 未引号值三种形态）
- [x] 1.2 补文本扫描回归测试（先 RED）
- [x] 1.3 改为逐匹配扫描：非敏感键从匹配内部重扫，敏感键正常脱敏（GREEN）
- [x] 1.4 更新 HTML 报告 traceback 契约测试为脱敏后断言，并做变异验证
- [x] 1.5 全量 pytest、覆盖率门禁（src/api）、ruff、black、mypy（零新增）通过
