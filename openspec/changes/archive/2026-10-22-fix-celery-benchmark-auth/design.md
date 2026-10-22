## 修复方案

execute_benchmark 延迟导入 AuthSettings、AuthService 与 BenchmarkService，创建配置完整的认证服务并以 auth 参数传入基准服务，保留 recover=False。执行使用 try/finally 释放基准服务的 engine，与 execute_experiment 的生命周期一致。

认证仍由 AuthService.llm_config 执行所有权校验和持久化密钥解密，不将明文密钥写入 Celery 参数或运行配置。

## 验证

先补会失败的构造注入断言及真实任务入口测试。真实路径使用临时认证库和业务库，保存加密测试密钥；只替换 BenchmarkExecutor.execute，检查收到的模型配置和完成指标。参数化覆盖其他用户密钥拒绝；另检查异常时释放连接。修复后运行回归、相关基准与实验任务测试、格式检查和 Python 编译。
