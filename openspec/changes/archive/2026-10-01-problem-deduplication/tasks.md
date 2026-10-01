## 1. 依赖和模块设置

- [x] 1.1 在 pyproject.toml 中添加 scikit-learn 依赖，运行 `poetry install` 验证安装成功
- [x] 1.2 创建 src/harness/utils/deduplication.py 模块并验证文件结构正确

## 2. 相似度检测实现

- [x] 2.1 实现 compute_similarity() 函数，使用 TfidfVectorizer 和 cosine_similarity 计算题目相似度，验证单元测试通过
- [x] 2.2 实现 find_similar_pairs() 函数，基于阈值检测相似题目对，验证返回正确的题目对列表
- [x] 2.3 添加单元测试 test_compute_similarity_high 验证高相似度题目检测（相似度 > 0.9）
- [x] 2.4 添加单元测试 test_compute_similarity_low 验证不同题目不被误判（相似度 <= 0.9）

## 3. 指纹匹配实现

- [x] 3.1 实现 generate_fingerprint() 函数，基于 source_platform 和 source_problem_id 生成唯一指纹，验证返回正确格式
- [x] 3.2 实现 find_fingerprint_duplicates() 函数，检测完全相同题目，验证返回正确的重复组
- [x] 3.3 添加单元测试 test_fingerprint_exact_match 验证完全相同题目检测
- [x] 3.4 添加单元测试 test_fingerprint_missing_source 验证缺失来源信息的处理

## 4. 合并策略实现

- [x] 4.1 实现 select_primary_problem() 函数，基于字段完整度选择主版本，验证选择逻辑正确
- [x] 4.2 实现 merge_problems() 函数，合并列表字段（tags、test_cases）并添加 merged_from 记录，验证合并结果包含所有信息
- [x] 4.3 添加单元测试 test_merge_strategy_completeness 验证字段完整度优先策略
- [x] 4.4 添加单元测试 test_merge_strategy_list_fields 验证列表字段正确合并去重

## 5. CLI 命令实现

- [x] 5.1 在 src/harness/cli.py 中添加 problems 命令组（如不存在），验证命令结构正确
- [x] 5.2 实现 deduplicate 子命令，支持 --dataset、--threshold、--auto-merge、--dry-run 参数，验证参数解析正确
- [x] 5.3 实现交互式模式，提示用户确认每对重复题目，验证用户可选择保留或合并
- [x] 5.4 实现自动模式（--auto-merge），自动合并所有重复题目，验证合并逻辑正确执行
- [x] 5.5 实现预览模式（--dry-run），仅显示重复题目不修改文件，验证文件未被修改

## 6. 去重报告实现

- [x] 6.1 实现去重报告生成函数，统计扫描题目数、相似度检测发现的重复对、指纹匹配发现的重复对、实际合并数、跳过数，验证统计准确
- [x] 6.2 在命令执行完成后输出报告，验证报告格式清晰易读

## 7. 集成测试

- [x] 7.1 创建测试数据集包含重复题目（相似度检测和指纹匹配各一对），运行 `harness problems deduplicate --dry-run` 验证检测到所有重复
- [x] 7.2 在测试数据集上运行交互式去重，验证用户可以选择保留或合并
- [x] 7.3 在测试数据集上运行自动去重（--auto-merge），验证重复题目被正确合并且数据集文件更新
- [x] 7.4 验证合并后的题目包含 merged_from 字段且信息完整

## 8. 文档和清理

- [x] 8.1 在 CLI help 中添加 deduplicate 命令的使用说明，运行 `harness problems deduplicate --help` 验证显示正确
- [x] 8.2 运行所有单元测试确保通过，运行 `pytest tests/test_deduplication.py -v` 验证全部通过
