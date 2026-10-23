## Why
部署种子题库三道题全部不能通过 worker 的 domain Problem 校验。`expected` 应为 `expected_output`，且 function 输入必须为参数字典，输出必须保留数组、布尔、整数类型。

## What Changes
- 修正三道种子题的六个测试用例，题面明确 solution 入口。
- 新增真实 SQLite 导入、worker domain 转换、沙箱执行回归测试。
- 文档说明旧部署重新运行 seed 可原位修复。

## Capabilities
无新增或修改规格；修复已有部署示例，不改变接口或数据库 schema。

## Impact
scripts/seed_data.py、tests/test_seed_data.py、docs/deployment/deploy.md。

## 根因与失败证据
python3 逐个执行 Problem.model_validate(SEED_PROBLEMS)；三道题均在 public_test_cases.0/1.expected_output 报 Field required。旧测试仅检查幂等和标题更新，未验证 worker 可消费性。

## 修复目标
全部示例导入后可被 _to_domain_problem 转换，并由标准 solution 函数通过所有公开用例；保留既有幂等更新机制。

## 回归与根因消除证据
新增参数化回归在旧代码上为 3 failed / 2 passed，失败均为 expected_output 缺失。修复后相关测试 98 passed，三道题首次导入及模拟旧行重播后均可由 worker 转换并执行通过。六个用例均已改为字典输入与原生输出，无旧 expected 字段和赋值文本残留。未新增 capability、API 或 schema，改动为三个实施文件。
