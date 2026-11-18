# Preset file-count authorization

- status: active
- workflow: tweak
- decision: continue-on-file-count-only
- scope: issue #494 已批准提案中的 A 防泄漏、B 最小快照/历史加载/集合追溯、正式实验固定集合及恢复校验，保留 Few-Shot 禁用增量复用。
- allowed-file-categories: implementation, tests, user-docs, config, generated
- authorization-basis: user-explicit
- reason: 用户在展示 10–12 个交付文件、可选结果字段与冻结格式的提案后回复“1”，明确选择按方案继续 tweak；仅在同一范围、验收及风险条件下复用，实际范围扩大时失效。
