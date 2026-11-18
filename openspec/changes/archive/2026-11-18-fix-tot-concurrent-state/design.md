# 技术设计

## Context
见 proposal.md。最新代码仍在 search_tree 重置四个实例属性；Harness worker 复用同一实例。

## Decisions
建立内部搜索状态数据类，保存 iterations、responses、call context 和 budget stop。用 ContextVar 将状态绑定到一次 search_tree 调用；进入时创建新状态，finally 中 reset，生成记录和结果提取读取当前状态。独立调用分支/评分辅助方法时使用临时状态，保留既有可直接调用语义。线程之间及嵌套调用不共享可变状态。

相比每题重建 runtime，该方案保留工厂、客户端和沙箱的生命周期；相比整段加锁，保留并行能力。仅给 append 加锁不能修复归属与重置冲突。

## Risks / Trade-offs
上下文未恢复可能污染同线程后续调用，因此必须在 finally 恢复，并覆盖异常和连续复用。仅修复 ToT 保存的终止原因，不改变预算客户端。无需数据迁移，回滚可撤销本次代码提交。

## 验证
真实 Harness 工厂、ToT、host sandbox 和 task-service，两 worker 模拟供应商用 Barrier/Event 建立确定性交错，不使用 sleep。正常题各有两次调用，检查提示、响应、迭代、token、定价元数据及持久化文件；异常和预算题与正常题交错，验证状态不传播。运行现有 ToT、Harness、task-service 相关测试和格式检查。
