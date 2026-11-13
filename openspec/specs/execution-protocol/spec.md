# execution-protocol Specification

## Purpose
定义 Host 与 Docker 函数返回结果通道的完整性和标准输出隔离要求，明确结果标记缺失、标记不匹配及非法 JSON 的失败语义，并保持 legacy 解析与 stdin/stdout 题目的各自契约，防止提前正常退出的候选程序产生判题假阳性。

## Requirements

### Requirement: 显式函数结果通道必须完整
系统 MUST 使用独立结果通道解析函数返回值，函数向 stdout 打印调试信息不得破坏结果解析。Host 和 Docker function 路径显式请求 result_marker 时 MUST 仅接受匹配该 marker 的合法 JSON payload；缺失或非法时 MUST 返回 runtime_error，且不得接受 stdout 代替返回值。仅未请求显式 marker 的 legacy 解析调用 MAY 回退到 JSON stdout。stdin/stdout 题仍 SHALL 按题目协议比较 stdout。

#### Scenario: 函数打印调试信息
- **WHEN** solution 返回合法值并打印调试信息
- **THEN** 判题只比较 marker 中的函数返回值

#### Scenario: 打印期望值后提前退出
- **WHEN** function 候选打印期望 JSON 并 SystemExit(0)，未产生本次 marker
- **THEN** Host 和 Docker 均返回 runtime_error 且 all_passed 为 false

#### Scenario: 非法结果 payload
- **WHEN** 本次 marker 后的 payload 非法，即使 stdout 是合法期望 JSON
- **THEN** 返回 runtime_error 且不回退 stdout

#### Scenario: 错误 marker
- **WHEN** stderr 只有默认或另一次执行的 marker
- **THEN** 显式请求本次 marker 的调用失败

#### Scenario: 明确 legacy 兼容
- **WHEN** 解析调用未提供显式 marker 且无默认 marker
- **THEN** 允许解析合法 stdout JSON

#### Scenario: 标准输入输出兼容
- **WHEN** 题目使用 stdin_stdout 并打印正确答案
- **THEN** 按原有输出规则判题成功，无需函数 marker

### Requirement: 零测试用例题目不可评估

CLI 和 Web SHALL 在策略求解前识别公开、反馈、隐藏用例均为空的题。每个对应单元 SHALL 产生 `not_evaluable` 结果，记录缺少测试用例的原因，并从成功数、模型失败数及已评估通过率分母中排除。

#### Scenario: 多策略评估缺少测试用例的导入题

- **WHEN** 一道待补全的导入题缺少全部测试用例且使用多个策略评估
- **THEN** 每个策略均保留一个 `not_evaluable` 明细，且无需请求模型或执行候选代码

#### Scenario: 仅有隐藏用例或反馈用例

- **WHEN** 一道题只有隐藏用例或只有反馈用例
- **THEN** 系统仍按对应判题阶段运行用例并保留执行结果

### Requirement: 函数题按题目配置选取并比较结果

CLI 和 Web 的共享函数判题 SHALL 支持从函数返回值或指定的命名输入参数采集结果。选择命名输入参数时，题目所有用例 MUST 提供该参数，执行器 MUST 在调用成功后读取其当前值，并继续使用独立的 JSON 结果通道。

#### Scenario: LeetCode 原地修改题

- **WHEN** 导入或加载缺省判题规则的 LeetCode 73 或 88 公开导入记录并运行符合题面签名的解答
- **THEN** 系统分别比较调用后的 `matrix` 或 `nums1` 与预期值

#### Scenario: 字符串分组允许两层重排

- **WHEN** 导入或加载缺省判题规则的 LeetCode 49 公开导入记录
- **THEN** 判题允许组间和组内重排，并拒绝遗漏、额外重复和分错组的结果

#### Scenario: 普通函数题及显式规则

- **WHEN** 函数题使用普通返回值规则或现有的比较模式
- **THEN** 判题采集返回值并按题目配置比较，要求顺序时仍拒绝重排

### Requirement: LeetCode 节点题按样例协议判题

CLI 和 Web 共享的函数判题 SHALL 为公开导入的 LeetCode 105、106、133 和 138 使用题目指定的节点协议。转换 MUST 在现有隔离执行器内部完成，并通过现有 JSON 结果通道返回。

#### Scenario: 返回二叉树

- **WHEN** 解答为 105 或 106 返回二叉树
- **THEN** 判题按层序比较节点值及内部空位，空根对应空列表

#### Scenario: 克隆有环图

- **WHEN** 解答为 133 返回克隆图
- **THEN** 判题要求从编号 1 的根得到相同的邻接关系，允许邻居重排，并拒绝复用原节点或原邻居列表

#### Scenario: 复制随机链表

- **WHEN** 解答为 138 返回复制链表
- **THEN** 判题比较 next 顺序、节点值和 random 的目标位置，并拒绝原节点、next 环及指向链表外的 random

#### Scenario: 空输入及既有导入

- **WHEN** 133 或 138 的样例输入为空，或加载缺省适配的既有公开导入记录
- **THEN** 空输入传给解答为 None，且记录使用同一节点协议，包含 133 既有的 adjList 样例键

#### Scenario: 尚未支持的节点类型

- **WHEN** 新导入题的 Python 入口使用尚未支持的节点类型
- **THEN** 题目携带明确的不可评估原因，执行时保留该原因，既有题可重新导入获取诊断
