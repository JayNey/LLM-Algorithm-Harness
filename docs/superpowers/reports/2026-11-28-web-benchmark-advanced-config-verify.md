# 验证报告：web-benchmark-advanced-config

## 结论

通过。任务 5/5 完成，两项新增需求和六个场景均有实现与验证证据。改动与已批准设计一致，无 CRITICAL、WARNING 或 SUGGESTION。共 10 个交付文件，分类为实现 5（含共享控件）、翻译配置 2、测试及验收脚本 3；均在用户批准范围内，授权见 rulings.md。

## 完整性与正确性

| 需求 / 场景 | 实现与证据 |
| --- | --- |
| 高级配置提交 | benchmarks/types.ts 使用共享类型；validation.ts 序列化完整策略与筛选；validation.test.ts 与双语浏览器脚本检查精确请求 |
| 默认值及策略切换 | runStrategies 仅返回当前选择的名称；空字段省略、显式零温度保留；单测验证被移除策略不泄漏配置 |
| 非法输入 | 验证迭代、温度、Token、难度、数量上限及共享自定义参数白名单；单测覆盖非法 JSON、非对象、越界及非整数；浏览器阻止非法提交并保留输入 |
| 组合筛选与真实执行 | executor.py 按套件顺序应用共享过滤；test_web_benchmark_config.py 从 API 创建和持久化到真实服务、执行器、Harness 及 self_consistency，验证实际调用参数、执行 ID b、结果题数、准确率与成本进入历史 |
| 空交集 | 执行器在创建 Harness 前明确抛错；测试确认不调用 Harness，不改写原配置 |
| 旧配置兼容 | 无筛选时执行套件题目；前端名称流程仍只生成 name；已有 API、预算和任务回归通过；双语浏览器展示无高级字段的旧历史 |

实现遵循设计：复用共享高级字段、草稿与参数白名单；既有 API、预算、任务、冻结和历史协议未修改。使用配置副本，正常及异常路径清理临时数据；测试覆盖执行失败后的清理及原配置不变。新增依赖为零。

## 实际检查

详见 openspec/changes/web-benchmark-advanced-config/checks.json，全部最终命令返回成功：

- 前端 `npm test`：384 passed，0 failed。
- 后端 `pytest --no-cov` 新增测试、基准预算、任务和 API 回归：100 passed。最终调整配置副本的异常清理边界后，新测试再次 4 passed。
- 双语浏览器 mock：精确请求、非法输入、运行导航、旧历史和 320px 无整体溢出均通过，无 pageerror。证据 `/tmp/issue528-browser/checks.json`，同目录含桌面与窄屏截图；已人工查看英文窄屏截图。
- TypeScript/Vite 构建、ESLint、修改前端文件 Prettier、Python Ruff 与格式、`git diff --check`、OpenSpec 严格校验通过。

## 验证边界与已解决的执行问题

review_mode=off，未派发独立审查，结论来自主会话验证。未调用付费模型，模型 SDK 与沙箱使用受控 mock，业务执行路径使用真实实现；未运行仓库全量 Python 测试。首次定向 pytest 的测试用例全部通过，但全局覆盖率 90% 门槛未满足，命令失败；后续按定向检查使用 `--no-cov`，不宣称全局覆盖率达标。现有构建包大小警告与 Python 弃用警告不影响本次功能。

浏览器最初在沙箱内启动受限，已通过平台授权运行；首轮脚本误写 URL 参数为 run，经实际导航日志确定是 run_id 后修正，最终两种语言均通过。已修复脚本 ESLint 导入和文件格式问题，最终 lint/format 通过。
