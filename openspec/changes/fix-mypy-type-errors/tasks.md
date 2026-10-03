# Tasks: Fix Mypy Type Errors

## 阶段 1: 高影响文件

- [x] 修复 `src/harness.py` 的类型错误（83 个错误）
- [x] 修复 `src/sandbox_executor.py` 的类型错误（63 个错误）
- [x] 修复 `src/main.py` 的类型错误（57 个错误）
- [x] 修复 `src/ab_testing.py` 的类型错误（48 个错误）
- [x] 修复 `src/llm_client.py` 的类型错误（44 个错误）
- [x] 阶段 1 完成后运行测试确保无回归

## 阶段 2: Debug 模块文件

- [x] 修复 `harness/debug/debugger.py` 的类型错误（23 个错误）
- [x] 修复 `harness/debug/cli.py` 的类型错误（21 个错误）
- [x] 修复 `harness/debug/breakpoint.py` 的类型错误
- [x] 修复 `harness/debug/editor.py` 的类型错误
- [x] 阶段 2 完成后运行测试

## 阶段 3: 剩余核心文件

- [ ] 修复 `src/cache.py` 的类型错误
- [ ] 修复 `src/reporting/markdown_generator.py` 的类型错误
- [ ] 修复 `src/utils/logging.py` 的类型错误
- [ ] 修复剩余 30 个文件中错误较少的文件
- [ ] 阶段 3 完成后运行测试

## 阶段 4: 最终验证

- [ ] 运行 `mypy src/ --ignore-missing-imports` 并验证零错误
- [ ] 运行完整测试套件确保无功能回归
- [ ] 验证 CI 类型检查作业通过
- [ ] 如需要使用 black 格式化代码

## 注意事项

- 每个任务应增量完成，每个文件完成后提交
- 每个文件后运行 mypy 以跟踪进度
- 参考 PR #122 中正确类型注解的示例
- 提交消息格式：`fix: resolve mypy errors in <filename>`
