## ADDED Requirements

### Requirement: 基准运行高级策略与题目筛选

套件运行表单 SHALL 为已选策略提供 max_iterations、temperature、max_tokens、system_prompt 和已有有效 custom_params 输入，并发送完整策略对象；留空 SHALL 省略相应覆盖值。表单 SHALL 提供 difficulty、tags、problem_ids、limit 筛选及明确校验反馈，说明条件与固定套件取交集后按套件顺序截取数量。原有只填名称的流程及历史展示 SHALL 保持可用。

#### Scenario: 高级配置提交
- **WHEN** 用户填写合法高级策略参数与筛选后启动运行
- **THEN** 请求携带对应策略对象与 problem_filters，现有运行任务及结果历史链路继续可用

#### Scenario: 默认值及策略切换
- **WHEN** 用户仅选择策略名称或未填写某项覆盖值
- **THEN** 请求省略未填字段并沿用已有默认或继承语义，移除策略不会将其配置提交给其他策略

#### Scenario: 非法输入
- **WHEN** 参数越界、迭代或数量非正整数、难度无效、JSON 非对象或自定义参数不受支持
- **THEN** 表单显示对应错误并阻止提交，保留输入供修正

