# API 性能测试（issue #158，第 5 节）

从仓库根目录执行。安装项目及可选工具：

```bash
python3 -m pip install -e '.[dev,performance]'
```

## 响应时间与数据库查询基准

```bash
python3 tests/performance/benchmark.py --rows 1000 --samples 100 --concurrency 4 --output /tmp/api-baseline.json
python3 tests/performance/benchmark.py --rows 10000 --samples 100 --concurrency 16 --output /tmp/api-large.json
```

每次创建临时文件 SQLite，运行真实迁移、认证和数据查询，在题目、评估、任务三张表各预置指定行数；结束后清理数据库、上传目录及连接池。不需要 Redis、Celery worker、LLM 凭据或 Docker。不会修改开发数据库。

测量健康检查、认证评估列表、认证任务列表三个 API；数据库测量唯一键题目查询、深分页、计数、按用户评估列表（含关联任务物化）。HTTP 使用 TestClient 与线程池，数据库查询串行执行。初始化及每项 3 次预热不计时；单次延迟包含完成请求或物化结果的时间，吞吐量使用整批 wall time。JSON 含 Python、系统、依赖版本、数据规模、并发、样本数、错误类型、mean/p50/p95/p99 毫秒值及每秒吞吐量；分位数使用 nearest-rank 算法。失败样本不会被过滤。

默认因请求/查询错误返回非零，不对机器相关延迟强制设限。设置 `--max-p95-ms 250` 可启用统一 p95 门限，超限返回 1；适合固定 runner 上的回归门禁。比较时保持机器、依赖、行数、并发和预热一致，并重复运行；100 样本只适合作为起点，稳定尾延迟需要更多样本。

## Locust：负载、压力、并发

在第一个终端启动隔离目标（只监听 loopback）：

```bash
python3 tests/performance/benchmark.py --serve --rows 1000 --port 8099 --token-file /tmp/harness-performance.token
```

等待服务显示 `Application startup complete`。临时用户 token 写入权限为 0600 的文件；文件必须不存在，正常退出时自动删除。异常中断后确认进程已结束再移除旧文件。token 有效期 24 小时，过期后重新启动 fixture。下列命令在第二个终端依次执行，避免争用目标：

```bash
export PERF_TOKEN_FILE=/tmp/harness-performance.token
export PERF_USERS=10
export PERF_STAGE_SECONDS=60
export PERF_MAX_P95_MS=1000

PERF_PROFILE=load locust -f tests/performance/locustfile.py --headless --stop-timeout 10 --host http://127.0.0.1:8099 --csv /tmp/api-load --html /tmp/api-load.html
PERF_PROFILE=stress locust -f tests/performance/locustfile.py --headless --stop-timeout 10 --host http://127.0.0.1:8099 --csv /tmp/api-stress --csv-full-history --html /tmp/api-stress.html
PERF_PROFILE=concurrency locust -f tests/performance/locustfile.py --headless --stop-timeout 10 --host http://127.0.0.1:8099 --csv /tmp/api-concurrency --html /tmp/api-concurrency.html
```

- `load`：5 秒左右递增至 `PERF_USERS`，保持至 1 个阶段结束。
- `stress`：4 个阶段分别为 1、2、4、8 倍用户，逐步增加压力；默认总计 240 秒。提高用户数/阶段时间直到出现延迟门限失败或服务错误，观察历史 CSV，定位首次退化的阶段。此场景用于探索拐点，没有预设“生产容量”结论。
- `concurrency`：以每秒 `PERF_USERS` 的生成速率快速增加至目标并发，持续 1 个阶段；每用户随机等待 0.1–0.5 秒。它是高生成速率的并发读场景，不保证所有 HTTP 请求在同一时刻到达。

负载按健康检查:评估列表:任务列表 = 1:3:2 分配；分页固定 20。所有读取通过真实认证边界，验证状态码、success 与分页结构。凭据缺失导致零样本也会失败。任何请求失败（包括 401、429、5xx、timeout、非法 JSON）或聚合 p95 大于 `PERF_MAX_P95_MS` 均返回非零；CSV 和 HTML 保留失败率、吞吐量及响应分位数。默认 HTTP timeout 为 10 秒。使用 shape 时通过以上环境变量控制负载，不传 `-u/-r/-t`。

针对既有测试部署可用 `PERF_TOKEN` 提供有效 bearer token，并替换 `--host`；使用已有非空测试数据。fixture 的受保护接口限额为每用户每分钟 10000 次，保持实际限流逻辑；单用户高压力可能首先触发 429，应据此识别配额瓶颈。真实部署可能有更低配额。此套件不启动评估或产生 LLM 费用，评估执行性能由独立执行器测试覆盖。

## 自检与已记录基准

```bash
python3 -m pytest tests/performance/test_tools.py --no-cov -q
```

普通测试检查统计、错误保留、退出门限、参数验证及小规模真实并发；安装 performance extra 后额外验证三种 Locust shape。完整长时压测为手动任务，避免给普通 CI 引入机器相关时间断言。

[baseline.json](baseline.json) 保存本次 1000 行、每项 100 样本、4 HTTP 并发的实测和短时 Locust 验证。环境与每个场景参数均在文件中。该数据仅代表本地进程内 SQLite 与 loopback 的初始基准，不能解释为生产 SLA 或最大容量；LLM、网络、PostgreSQL、worker 执行时间需在目标环境另测。

本次短时验证：load 为 10 用户/20 秒，569 请求、0 错误、聚合 p95 84 ms；concurrency 为 10 用户/20 秒，626 请求、0 错误、p95 96 ms；stress 每阶段 10 秒，实际峰值 80 用户，1164 请求、0 HTTP 错误、p95 5800 ms，因超过 1000 ms 门限退出 1。这是保留的过载诊断结果，不是压力容量验收通过。对应 HTML/CSV 可通过上述命令重新生成；fixture 会保留 429 等错误，不能用降低门禁或忽略失败取得通过。
