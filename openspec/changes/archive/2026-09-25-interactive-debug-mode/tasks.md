## 1. 模块结构和依赖设置

- [x] 1.1 创建 `harness/debug/` 模块目录结构并添加 `__init__.py`，验证模块可被导入
- [x] 1.2 在项目依赖中确认 Python 标准库 `cmd` 模块可用，验证 `import cmd` 成功

## 2. 策略 Hook 点扩展

- [x] 2.1 在 `harness/strategies/base.py` 的 `StrategyBase` 中添加 `_before_generate(prompt)` hook 方法（默认空实现），验证子类策略运行不受影响
- [x] 2.2 在 `StrategyBase` 中添加 `_before_execute(code)` hook 方法（默认空实现），验证批量测试通过
- [x] 2.3 在 `StrategyBase` 中添加 `_after_feedback(feedback)` hook 方法（默认空实现），验证现有策略行为不变

## 3. 断点管理模块

- [x] 3.1 实现 `harness/debug/breakpoint.py` 中的 `BreakpointManager` 类，支持启用/禁用断点（generate、execute、feedback），验证断点状态正确切换
- [x] 3.2 为 `BreakpointManager` 添加 `should_break(location)` 方法，验证断点逻辑正确判断是否暂停

## 4. 策略装饰器

- [x] 4.1 实现 `harness/debug/strategy_wrapper.py` 中的 `DebugStrategyWrapper` 类，包装现有策略并在 hook 点检查断点，验证装饰器能正确调用原策略方法
- [x] 4.2 在 `DebugStrategyWrapper` 中实现暂停逻辑，当遇到断点时返回控制权给调试器，验证暂停和恢复流程正确

## 5. 轨迹记录和可视化

- [x] 5.1 实现 `harness/debug/trace.py` 中的 `TraceRecorder` 类，记录每轮的 prompt、响应、执行结果和用户干预，验证轨迹数据结构完整
- [x] 5.2 为 `TraceRecorder` 添加 `display_summary()` 方法显示轨迹摘要，验证输出格式清晰易读
- [x] 5.3 为 `TraceRecorder` 添加 `display_round(round_number)` 方法显示单轮详情，验证详细信息显示正确
- [x] 5.4 为 `TraceRecorder` 添加 `export_json(filepath)` 方法导出 JSON 格式轨迹，验证导出的 JSON 结构有效且可解析

## 6. Prompt 编辑功能

- [x] 6.1 实现 `harness/debug/editor.py` 中的 `edit_prompt(current_prompt)` 函数，优先使用 $EDITOR 环境变量指定的编辑器，验证编辑器成功打开并返回修改后的内容
- [x] 6.2 为 `edit_prompt` 添加降级到内联多行输入的后备机制，验证无编辑器时仍可输入新 prompt

## 7. 调试器主循环

- [x] 7.1 实现 `harness/debug/debugger.py` 中的 `Debugger` 类（继承 `cmd.Cmd`），支持基本命令循环，验证交互提示符正常显示
- [x] 7.2 实现 `do_next` 命令执行下一步，验证单步执行后显示结果并再次暂停
- [x] 7.3 实现 `do_continue` 命令继续到下一断点，验证跳过中间步骤直到断点或完成
- [x] 7.4 实现 `do_skip` 命令跳过当前步骤，验证跳过逻辑正确
- [x] 7.5 实现 `do_break` 和 `do_unbreak` 命令管理断点，验证断点启用/禁用生效
- [x] 7.6 实现 `do_edit_prompt` 命令调用 prompt 编辑功能，验证编辑后的 prompt 被使用
- [x] 7.7 实现 `do_set` 命令动态修改策略参数（temperature、max_rounds 等），验证参数修改生效且类型检查正确
- [x] 7.8 实现 `do_inject` 命令注入自定义提示到下一轮 prompt，验证注入内容出现在 prompt 预览中
- [x] 7.9 实现 `do_trace` 命令显示轨迹摘要和单轮详情，验证输出与 `TraceRecorder` 方法一致
- [x] 7.10 实现 `do_export` 命令导出轨迹，验证文件正确保存
- [x] 7.11 实现 `do_exit` 和 `do_quit` 命令退出调试会话，询问是否保存轨迹，验证退出流程完整

## 8. CLI 命令入口

- [x] 8.1 在 `harness/cli/debug.py` 中实现 `debug` 命令，接受 `--problem`、`--strategy`、`--model` 参数，验证参数解析正确
- [x] 8.2 在 `debug` 命令中添加 `--trace-output` 可选参数用于自动导出轨迹，验证指定路径时自动保存
- [x] 8.3 实现问题 ID 验证逻辑，当问题不存在时显示错误和可用 ID 列表，验证错误提示清晰
- [x] 8.4 在 `debug` 命令中集成 `Debugger` 和 `DebugStrategyWrapper`，启动交互式调试会话，验证完整流程从启动到退出正常工作

## 9. 显示和格式化

- [x] 9.1 实现执行过程的格式化输出，使用清晰的分隔符和标题区分 prompt、响应、执行结果和反馈，验证输出可读性
- [x] 9.2 为代码部分添加语法高亮（使用 `pygments` 或类似库），验证代码显示带颜色

## 10. 集成测试和文档

- [x] 10.1 编写端到端测试：启动调试会话、设置断点、单步执行、修改参数、导出轨迹，验证完整场景通过
- [x] 10.2 运行现有批量评估测试套件，验证新增 hook 点不影响批量模式性能和行为
- [x] 10.3 创建交互式调试使用指南文档，包含命令参考和示例会话，验证文档内容准确且可操作
- [x] 10.4 更新项目 README 或主文档，添加调试模式章节，验证文档链接和描述正确
