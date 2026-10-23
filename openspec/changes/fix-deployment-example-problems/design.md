## 修复方案
只修正种子数据：input 使用函数关键字参数字典，expected_output 使用原生 JSON 类型；题面声明 solution(nums, target) 或 solution(s)。不放宽 worker 校验、不添加旧 expected 别名、不改 schema。
回归测试使用临时 SQLite，真实 seed/ProblemStore/_to_domain_problem/SandboxExecutor，覆盖三道题和再次 seed 修复旧行。使用 host 沙箱执行固定的可信参考解，无模型、网络或 Docker 依赖。
既有 test_cases 按当前协议迁移为 public_test_cases，不推断隐藏用例；本次不改变正式评分语义。
