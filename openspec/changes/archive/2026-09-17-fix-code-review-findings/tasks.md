# Tasks: 修复代码审查发现的三个缺陷

## 任务清单

- [x] 修复 src/harness.py:163 - 保留原始错误信息
  - 在隐藏评估失败时，只在error_message为空时才设置通用错误信息
  - 保留公开测试产生的具体错误信息以便调试

- [x] 修复 src/strategies/multi_round_feedback.py:134 - 移除冗余赋值
  - 删除`if success:`块内的`success = True`死代码
  - 保留logger和break语句

- [x] 修复 src/strategies/multi_round_feedback.py:168 - 完善系统错误识别
  - 在resource_statuses集合中添加`sandbox_error`
  - 在resource_statuses集合中添加`backend_unavailable`
  - 确保系统错误被正确分类而非误判为wrong_answer
