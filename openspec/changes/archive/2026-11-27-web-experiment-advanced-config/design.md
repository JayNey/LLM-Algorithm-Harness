# 轻量设计

## Context

动机及范围见 proposal.md。ExperimentCreateRequest 已接受完整 StrategyConfig、problem_filters 和 ProblemBudget；ExperimentService 持久化并创建 ExperimentConfig，ExperimentRunner 通过 ProblemLoader 过滤题目。当前前端丢弃部分响应字段，草稿只支持单预算。

## Decisions

1. 在现有创建页增加可折叠的高级策略配置。max_tokens 为空时省略，否则为 100–8000 整数；system_prompt 保留非空正文。custom_params 使用 JSON 对象并展示当前策略可用键和示例，校验未知键、类型、范围及枚举，错误定位到具体策略和字段。白名单覆盖 self_consistency 的 num_candidates、temperature，tree_of_thoughts 的 branching_factor、max_depth、search_strategy、pruning_threshold，few_shot_learning 的 num_examples、similarity_metric、min_similarity_score，以及 reflexion 的 reflection_context_chars；实际名称以策略注册表为准。不会开放 example_manifest 等路径或连接配置。相较任意 JSON 透传，白名单可避免无效及越界配置；相较大量单独控件，JSON 可保持表单紧凑。
2. 筛选采用难度选择、标签与题目 ID 列表、正整数 limit。省略空字段，标签任一命中，各条件取交集，按原数据集顺序最后应用 limit；不宣称未预览的数据集已匹配多少题。创建前后及持久化详情显示条件摘要。列表输入保留 ID 中的标点，支持逗号或换行分隔并去重。
3. 预算使用三个独立可选输入，均空为 null；填写的维度一起提交。文案说明每题重置，任一限制触发停止，tokens 按已知 provider 用量结算，seconds 沿用共享执行语义。旧草稿若仅有 budget_kind/budget_value 仍可转换；旧任务缺失高级字段时展示默认语义。
4. 请求与响应类型补齐高级字段，持久化详情回显实际配置；空值不写入温度或 max_tokens，保持 #492 的参数继承。若后端有配置链路遗漏，仅补齐原字段传递。

## Risks / Trade-offs

- JSON 输入容易写错：提供支持键、示例和字段级错误，提交失败后保留草稿供修正。
- 旧测试及客户端存在单预算草稿：保留兼容转换，新增表单以多维预算为准。
- 参数可能到达请求却未被策略使用：离线测试经过请求解析、持久化、ExperimentConfig、Runner、真实策略构造及 mock LLM 调用核对有效值。
- 过滤摘要不是精确题目预览：明确展示条件语义，通过固定小题库的执行结果核对实际题目。

## Validation

前端单元测试覆盖空配置、组合预算、筛选归一、非法参数、响应保留和创建请求。Python 小题库与 mock LLM/sandbox 验证实际过滤题目、custom_params 策略行为、参数继承及组合预算。运行相关测试、前端构建、lint 和修改文件格式检查，并用本地 mock 浏览器流程检查控件、错误修正、提交 payload 和配置回显。验证不启动真实 Eval，不调用付费模型。
