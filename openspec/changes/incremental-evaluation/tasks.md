## 1. 基础设施与模型扩展

- [x] 1.1 创建 `src/incremental/` 模块目录结构，包含 `__init__.py`、`fingerprint.py`、`history.py`、`detector.py` 文件，并验证 Python 能够正常导入该模块
- [x] 1.2 在 `src/incremental/fingerprint.py` 中实现 `compute_problem_fingerprint(problem: Problem) -> str` 函数，使用 SHA256 对题目核心字段计算指纹，并验证单元测试覆盖字段变化检测
- [x] 1.3 在 `src/incremental/fingerprint.py` 中实现 `compute_dataset_fingerprint(problems: List[Problem]) -> Dict[str, str]` 函数，生成题目 ID 到指纹的映射，并验证测试通过
- [x] 1.4 创建 `results/.incremental/` 目录及 `.gitkeep` 文件，并验证目录在版本控制中存在

## 2. 历史记录管理

- [x] 2.1 在 `src/incremental/history.py` 中定义 `RunRecord` 和 `IncrementalHistory` 数据类（使用 dataclass），包含 run_id、timestamp、strategy、model、dataset_fingerprint、result_path 等字段，并验证类型检查通过
- [x] 2.2 实现 `IncrementalHistory.load(path: Path) -> IncrementalHistory` 方法，支持加载现有历史或创建空历史，处理文件不存在和 JSON 解析错误，并验证单元测试覆盖所有分支
- [x] 2.3 实现 `IncrementalHistory.save(path: Path)` 方法，使用文件锁（`fcntl.flock` 或 `portalocker`）避免并发写入冲突，并验证并发测试通过
- [x] 2.4 实现 `IncrementalHistory.add_run(record: RunRecord)` 方法，追加新的运行记录到历史索引，并验证单元测试确认记录正确追加

## 3. 增量检测逻辑

- [x] 3.1 在 `src/incremental/detector.py` 中实现 `find_matching_run(history: IncrementalHistory, current_fingerprint: Dict[str, str], strategy: str, model: str) -> Optional[RunRecord]` 方法，匹配策略、模型和数据集指纹，并验证单元测试覆盖完全匹配和无匹配场景
- [x] 3.2 实现 `detect_changes(current_fingerprint: Dict[str, str], historical_fingerprint: Dict[str, str]) -> Tuple[Set[str], Set[str], Set[str]]` 方法，返回新增、修改、删除的题目 ID 集合，并验证单元测试覆盖所有变化类型
- [x] 3.3 实现 `should_use_incremental(changes: Tuple) -> bool` 辅助函数，判断是否启用增量（如仅有新增/修改且数量合理），并验证单元测试通过
- [x] 3.4 在 `detector.py` 中实现 `load_historical_results(result_path: Path, problem_ids: Set[str]) -> Dict[str, ExecutionResult]` 方法，从历史结果文件中提取指定题目的结果，处理文件缺失和格式错误，并验证单元测试覆盖异常情况

## 4. CLI 集成

- [x] 4.1 在 `src/main.py` 的 argument parser 中添加 `--incremental` 布尔标志，并验证 `--help` 输出包含该选项说明
- [x] 4.2 修改 `src/main.py` 的主评估流程，在加载数据集后计算当前数据集指纹，并验证指纹计算逻辑执行
- [x] 4.3 在 `--incremental` 模式下，加载历史索引并执行增量检测，输出检测摘要（未变化/新增/修改题目数），并验证输出格式正确
- [x] 4.4 实现增量评估逻辑：过滤出需要评估的题目子集传入策略，加载历史结果用于未变化题目，并验证集成测试确认只评估变化题目
- [x] 4.5 实现结果合并逻辑：将新评估结果与历史结果合并为完整的 `StrategyReport`，并验证统计信息（成功率、总题数）准确

## 5. 结果保存与追溯

- [x] 5.1 在评估完成后调用 `IncrementalHistory.add_run()` 保存当前运行记录到历史索引，并验证 `history.json` 文件包含新记录
- [x] 5.2 在生成的结果 JSON 中添加 `incremental_mode` 字段，标识是否使用增量模式，并验证结果文件包含该字段
- [x] 5.3 为每个 `ExecutionResult` 添加可选的 `source` 字段（`"evaluated"` 或 `"reused"`），记录结果来源，并验证合并后的结果包含来源信息

## 6. 错误处理与回退

- [ ] 6.1 在指纹计算失败时（如题目字段缺失）捕获异常，记录错误日志并禁用增量模式，回退到全量评估，并验证集成测试确认回退行为
- [ ] 6.2 在历史索引文件损坏时（JSON 解析失败），记录警告并忽略历史，执行全量评估，并验证测试覆盖该场景
- [ ] 6.3 在历史结果文件缺失或损坏时，记录警告并回退到全量评估，并验证测试覆盖文件缺失和 JSON 错误
- [ ] 6.4 在并发写入历史索引时使用文件锁，失败时重试最多 3 次，并验证并发测试确认无数据损坏

## 7. 测试覆盖

- [ ] 7.1 编写 `tests/test_fingerprint.py`，覆盖题目指纹计算、字段变化检测、数据集指纹生成，并验证测试通过且覆盖率 ≥ 95%
- [ ] 7.2 编写 `tests/test_history.py`，覆盖历史记录加载、保存、追加、文件锁、JSON 错误处理，并验证测试通过且覆盖率 ≥ 95%
- [ ] 7.3 编写 `tests/test_detector.py`，覆盖变化检测、匹配历史运行、策略/模型不一致拒绝、历史结果加载，并验证测试通过且覆盖率 ≥ 95%
- [ ] 7.4 编写 `tests/test_incremental_integration.py`，端到端测试增量评估流程：初次全量评估 → 无变化增量评估 → 部分变化增量评估，并验证测试通过且结果正确
- [ ] 7.5 编写性能测试 `tests/test_incremental_performance.py`，验证增量模式在 80% 题目未变化时评估时间显著减少（≥ 70% 时间节省），并验证测试通过

## 8. 文档与示例

- [ ] 8.1 更新 `README.md`，添加 `--incremental` 选项说明、使用示例、工作原理简述，并验证文档准确性
- [ ] 8.2 创建 `docs/incremental-evaluation.md` 详细文档，包含设计原理、指纹算法、匹配规则、错误处理、FAQ，并验证文档完整性
- [ ] 8.3 添加 `examples/incremental_example.py` 示例脚本，演示启用增量模式的完整评估流程，并验证示例可执行

## 9. 代码质量与 CI

- [ ] 9.1 运行 `pytest` 确保所有新增测试通过，并验证测试覆盖率报告显示增量模块覆盖率 ≥ 95%
- [ ] 9.2 运行 `mypy src/incremental/` 确保类型检查通过，无类型错误，并验证 mypy 报告无错误
- [ ] 9.3 运行 `ruff check src/incremental/` 和 `ruff format src/incremental/` 确保代码风格符合项目规范，并验证无 lint 错误
- [ ] 9.4 运行完整的 CI 测试套件（包括现有测试），确保增量功能不破坏现有功能，并验证所有 CI 检查通过
