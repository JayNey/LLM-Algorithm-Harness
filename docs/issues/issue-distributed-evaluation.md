# [功能] 分布式评估支持

## 背景与目标

当前评估在单机上运行，大规模测试（1000+ 题目 × 多模型）耗时过长。分布式评估支持可将任务分发到多台机器并行执行，显著提升评估效率，适合工业级评测场景。

- 分类：任务执行
- 建议优先级：P3（低优先级，复杂度高，单机暂时够用）
- 相关文档：[feature-roadmap.md](../feature-roadmap.md#8-分布式评估支持)

## 工作范围

### 1. Master-Worker 架构
- Master 节点职责：
  - 任务调度和分发
  - Worker 心跳监控
  - 结果聚合
- Worker 节点职责：
  - 接收任务单元
  - 执行评估
  - 上报结果和进度

### 2. Redis 队列管理
- 使用 Redis 作为任务队列和状态存储
  - 任务队列：`LPUSH/RPOP` 实现
  - 结果存储：Hash 结构
  - Worker 心跳：TTL 机制
- 支持任务优先级（高优先级队列）
- 失败任务自动重试（Dead Letter Queue）

### 3. 负载均衡
- 动态任务分配：
  - 根据 Worker 负载调整分配策略
  - 慢 Worker 自动降低分配权重
- 任务粒度优化：
  - 单题作为最小任务单元
  - 避免长任务阻塞

### 4. 容错机制
- Worker 失败检测：
  - 心跳超时重新分配任务
  - 任务执行超时自动取消
- 部分失败处理：
  - 单个题目失败不影响整体
  - 失败任务重试 3 次

## 验收标准

- [ ] Master 节点可启动并管理多个 Worker
- [ ] 任务正确分发到 Worker 并收集结果
- [ ] Worker 崩溃后任务自动重新分配
- [ ] 结果聚合正确，与单机模式一致
- [ ] 性能测试：3 Worker 并行速度达到单机 2.5x+
- [ ] 文档更新：分布式部署指南

## 边界

- 仅支持本地多进程/多机部署，不支持 K8s 编排
- 不涉及跨数据中心分布式
- Redis 单实例即可，不要求高可用集群

## 依赖与关联

- 前置：#14 [功能] 可复用评测任务服务（已完成）
- 关联：云端执行功能（AWS Lambda 等）
- 后续扩展：动态扩缩容、资源调度优化

## 技术要点

### Redis 任务队列
```python
import redis

r = redis.Redis(host='localhost', port=6379)

# Master 分发任务
r.lpush('task_queue', json.dumps(task))

# Worker 拉取任务
task = r.brpop('task_queue', timeout=5)

# 上报结果
r.hset(f'result:{run_id}', problem_id, result)
```

### Worker 心跳
```python
def heartbeat_loop(worker_id):
    while True:
        r.setex(f'worker:{worker_id}:heartbeat', 30, 'alive')
        time.sleep(10)
```

### 任务重试
```python
# 失败任务进入重试队列
r.lpush('retry_queue', json.dumps({
    'task': task,
    'retry_count': 1,
    'last_error': str(error)
}))
```

## 预期收益

- 实现工作量：约 10-14 天
- 性能提升：理论上 N Worker = N 倍速度
- 适用场景：工业级大规模评测
- 成本优化：可使用多台低配机器替代单台高配

## 备注

**建议延后实现**，理由：
1. 当前单机 + TaskService 并发已能满足大部分需求
2. 复杂度高，维护成本大
3. 优先实现更高价值功能（策略、模型对比）
