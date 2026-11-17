# Preset file-count authorization

- status: active
- workflow: tweak
- decision: continue-on-file-count-only
- scope: GitHub #490 的 CLI 增量执行及题目指纹、旧历史兼容、复用来源和断点恢复，共 4 个实现文件与 3 个测试文件
- allowed-file-categories: implementation, tests
- authorization-basis: user-explicit
- reason: `tests/test_fingerprint.py` 的旧断言把标题、标签和难度归为审计字段，需要与已批准的验收规则对齐。用户明确选择继续 tweak 并批准 7 个文件。
