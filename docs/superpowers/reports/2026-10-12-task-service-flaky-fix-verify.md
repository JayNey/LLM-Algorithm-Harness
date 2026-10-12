# 验证报告：task-service-flaky-fix（CI 稳定性修复）

- 日期：2026-10-12
- 分支：comet/task-service-flaky-fix（基线 fa79b5a + #151/#175 之后的最新 main）
- 验证模式：light（纯测试稳定性修复，无 delta spec；tweak 预设 review_mode=off，独立审查以跳过原因记录替代：测试文件单点修改、根因与修复均有确定性证据）
- comet change：task-service-flaky-fix（rebind 至 comet 自己创建的 comet/task-service-flaky-fix 分支——首次 workspace prepare 因未提交的报告文件失败，状态被过早绑定到旧分支；第二次 prepare 成功创建本分支并返回绑定，属可据证据补齐的状态）

## 检查结果简表（light 清单）

| # | 检查项 | 结果 | 证据 |
|---|--------|------|------|
| 1 | tasks.md 全部完成 | PASS | 2/2 `[x]` |
| 2 | 改动与 tasks 一致 | PASS | 仅 tests/test_task_service.py 一个测试函数重写 |
| 3 | 构建/测试通过 | PASS | build check exit=0（log 1df02bab）：1281 passed / 4 skipped，coverage 90.43%，门禁 90 原样 |
| 4 | 相关测试通过 | PASS | 目标测试连续 5 次运行稳定通过（旧断言在本机同样会随负载假红） |
| 5 | 无安全问题 | PASS | 纯测试文件修改 |
| 6 | 最终集成代码审查 | PASS（跳过记录） | review_mode=off；单文件、确定性根因与回归锁（峰值并发断言在池退化串行时必红） |
| 7 | 核心场景验证 | PASS | 串行峰值 == 1、并行峰值 >= 2、两条 run 全单元 completed——池退化串行时断言必红，比原墙钟断言更强 |

## 根因与修复

旧断言 `duration_parallel < duration_serial / 1.5` 以墙钟加速比判定并发性，runner 负载波动压缩 sleep 窗口即假红：2026-10-12 连续三次阻塞 PR #176 的 windows job（py3.12），PR #144 亦曾中招。修复以 lock 保护的峰值并发计数替代计时断言：串行必须峰值 1、并行必须 >1，run 全部完成——池一旦退化串行断言必红，与计时无关。

## 交付门禁

推送并创建引用 #176/#144 flake 记录的 PR；由队长决定合入顺序（可与 #176 独立合入，之后重跑 #176 的失败 job 即可转绿）。
