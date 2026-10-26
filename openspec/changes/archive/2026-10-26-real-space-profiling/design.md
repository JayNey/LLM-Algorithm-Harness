## 实现方案
保留现有沙箱超时、输出限制、Docker 隔离和清理链路，在 runner 内编译后启动 tracemalloc，通过每次运行唯一的 stderr 标记回传 current/peak 字节。采样覆盖候选代码加载和调用及少量包装器开销，不覆盖解释器启动、原生库未追踪分配或整个进程 RSS，不据此推断 Big-O。

默认仅使用原始公开测试（scale=1）；显式请求缩放时保留 Problem 协议并按 TestCase.input 递归缩放，缩放输出不与原始 expected_output 比较。原始输入执行失败、结果错误、超时、后端不可用或缺失采样均不形成有效样本；不运行隐藏测试。

SpaceAnalyzer 接收可选 Problem（保留已有 test_input 参数兼容），编排层传递 Problem；缺少上下文或采样失败时返回空指标及说明。多用例取最大峰值，MB=bytes/1048576，效率=clamp(100*(1-peak_bytes/(memory_limit_mb*1048576)),0,100)，表示预算余量，不声称理论最优比值。

## 验证
真实 host 子进程比较常量返回与临时分配 8 MiB 后释放的函数；覆盖类方法、stdin/stdout、公开测试隔离、错误/超时/无采样和 Docker runner 链路；检查报告消费者兼容。
