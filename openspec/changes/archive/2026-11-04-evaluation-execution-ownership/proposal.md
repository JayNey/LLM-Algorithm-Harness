## Why
Issue #341：同代 running 消息可重复执行，短事务锁不能覆盖模型调用及检查点写入。
## What Changes
- 同一评估跨进程持有执行期排他锁，进程死亡自动释放，重复消息重投递。
- 恢复入口拒绝仍活跃的旧执行者；取消等待在途线程收尾后释放执行权。
- 保持 #337 检查点重放和费用差额记账。
## Capabilities
### New Capabilities
无。
### Modified Capabilities
- `api/evaluation-execution`：执行独占和故障接管。
## Impact
worker、TaskService 取消收尾、TaskManager、评估恢复入口、共享任务卷和回归测试。无需迁移或新增依赖。
