# #443 生产 Web 与执行链验收

2026-11-09，候选提交 `73e7050acea7787803856b023168bfeada8667d5`。从 `git archive` 导出的源码构建，运行实际生产 Nginx、FastAPI、PostgreSQL、Redis、Celery worker/beat 和 Docker 沙箱。验收环境为 Docker Desktop Linux ARM64，唯一浏览器入口为 `http://127.0.0.1:18443`。使用独立 Compose 项目 `harness-443-acceptance`、独立数据卷、隔离账号和三道合成加法题。

## 镜像与脱敏配置

- 构建成功。最终 Nginx 镜像 `733110b53715`，API `22e26c421daa`，worker `8bf5dab39979`，beat `aa6246018b2d`，PostgreSQL `aae6554de426`，Redis `c5d34a98396a`，Docker 沙箱及替身基础镜像 `ae952e0a5713`。
- Headless Chrome 156，Docker 29.7.2，Compose v5.4.0，Nginx 1.31.8，PostgreSQL 15.19，Redis 7.4.12，Python 3.11.18，Celery 5.7.0。
- 沿用生产编排中的 PostgreSQL 数据库、Redis broker/backend、Nginx 就绪门禁、API 与 worker 的 uploads/data/results 共享卷。覆盖镜像标签和回环绑定端口，使用临时应用密钥和 PostgreSQL 密码。Docker socket 组 ID 为 0，沙箱临时目录在宿主与 worker 内路径一致。
- 替身仅接管 Compose 网络内的 `api.openai.com`，API 和 worker 信任隔离自签证书。模型目录返回 `gpt-4o-mini`，生成固定 Python 加法函数和 120 输入 / 30 输出 tokens。替身记录题目标记，不保存提示词或授权头。模型使用占位密钥，真实供应商联调待授权。

## 生产入口

Chromium 登录和受保护 API 返回 200，确认 HttpOnly Cookie。禁用缓存硬刷新 `/experiments/new` 返回 200，33 个 JavaScript 响应和两个公共 SVG 均为 200，缺失分包返回 404。初次导出误用了过严的 umask，导致两个 SVG 的权限不足。使用标准检出权限从同一 SHA 重建 Web 镜像后复核通过。原生 WebSocket 收到 `connected`，发送 `{"action":"ping"}` 后收到 `pong`。

停止隔离 PostgreSQL 后，`/login` 和 API 存活探针返回 200，就绪、`/users/me` 和新 WebSocket 握手返回 503。恢复 PostgreSQL 后，就绪与 `/users/me` 返回 200，WebSocket 收到 `pong`。随后实验与 A/B 的首次创建和基准套件列表各出现一次 HTTP 500，API 记录 `OperationalError`。用候选版本的 `make_engine` 对 PostgreSQL 池预热并复现中断。就绪恢复 200 后，旧池连接的第一次 `SELECT 1` 返回 `AdminShutdown`，SQLAlchemy 标记连接失效，下一次查询返回 1。该问题使原候选的完整就绪恢复验收未通过。修复复测见下文。

沙箱预检在生产 worker 内执行一条真实 Docker 用例，1/1 通过。

## 复现入口检查

在干净候选源码中按部署指南生成隔离 `.env`，设置 Docker GID 与同路径沙箱目录。Compose 覆盖文件为四个应用镜像设定独立标签，将 Nginx `ports` 覆盖为 `127.0.0.1:18443:80`，挂载模型替身证书并为替身加网络别名。以下操作针对本次独立项目。

```sh
qa() {
  docker compose -p harness-443-acceptance -f docker-compose.prod.yml -f acceptance.override.yml -f mock.override.yml "$@"
}
qa build
qa up -d --wait --wait-timeout 100
qa images
qa ps
curl -fsS http://127.0.0.1:18443/api/v1/health/ready
qa stop postgres
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:18443/api/v1/health/ready
qa start postgres
```

按[生产 Web 发布验收指南](https://github.com/JayNey/LLM-Algorithm-Harness/blob/73e7050acea7787803856b023168bfeada8667d5/docs/deployment/deploy.md#web-发布验收)检查浏览器登录、硬刷新和同源 WS。数据库恢复后也要提交实验和 A/B，并打开基准列表，以覆盖各业务连接池。

## 浏览器执行链与恢复

四条链由 Chromium 在生产 Nginx 入口提交。应用请求、WebSocket、队列、数据库和沙箱均使用实际服务。仅模型目录、生成和用量响应来自可控替身。

- **评估**。创建 201，启动 202，Celery 任务 `9d3a4df39d5f` 完成。一道合成题通过，结果页读回 1/1，单次成功率显示 1/1，通过页面下载 Markdown，报告请求返回 200。
- **实验**。创建 201，启动 202，任务 `bf952a29f75c` 在创建后移走原始 `data/qa443.json` 的条件下，使用 SHA-256 为 `772a3c757e59d86bba10987cd837f3f6f57b803bcfe048434f36409edfb5bbc0` 的快照完成 3 道题。刷新读回对比报告，独立重启 API 后结果内容一致，报告生成时间随请求变化。
- **基准**。显式选择 `vanilla`，套件 `0445c8f4f2c9` 的运行 `84636bf4624c` 经 Celery 完成 3 道题，刷新后可读取学习曲线。另以 USD 0.000001 启动运行 `3a327e1629f3`，一次替身调用后任务进入 `paused`，点击「刷新运行」后状态一致。现行 Web 规格覆盖暂停显示和手动核对。本轮按该范围验收，Web 发起恢复入口留待产品范围确认。表单将策略标作可选，留空的运行接受提交后在 worker 失败，错误为 `No strategies configured`。
- **A/B**。创建 201，启动 202，任务 `0b387a16af3f` 完成，刷新后可访问 A/B 通过率对比表及分层统计。独立重启 API 后返回相同结果，worker 保持运行。
- **评估断线及同任务恢复**。主动关闭原生 WebSocket，观察到评估详情的 HTTP 回读与新的 WS 订阅。暂停后确认已持久化 1 个单元，worker 的共享任务卷中存在检查点。独立重启 worker，刷新后点击「恢复任务」，同一任务 `338ccde7a2d1` 使用新 Celery generation 完成。恢复前替身仅收到 `QA443_ALPHA`，完成后依次收到 `QA443_ALPHA`、`QA443_BETA`、`QA443_GAMMA`，三题各一次。刷新读回 3/3，单次分析和 Markdown 报告可用。

上文任务和运行标识为 SHA-256 前 12 位。本轮连续自动探测曾触发发布限流，重跑间隔放宽后完成同任务结果回读。回环环境使用 HTTP 和 WS。

## 测试与复核

```sh
python3 -m pytest tests/test_deployment_readiness.py tests/test_benchmark_run_budget.py tests/test_benchmark_task.py -q --no-cov
comet classic openspec -- validate release-web-execution-acceptance --type change --strict --no-interactive
git diff --check
```

35 项相关测试通过。首次在受限沙箱运行时，17 个需要回环监听的测试在初始化时被拒绝，允许回环绑定后复跑通过。前端生产构建由 Nginx 多阶段 Dockerfile 执行。

## 结论与未执行项

本候选的四条模型替身链均到达预期终态。原候选的 PostgreSQL 恢复问题已在修复镜像中复测通过。基准留空策略会导致 worker 失败，成功链使用显式策略。真实供应商及公网 TLS 证据未执行。现行 Web 暂停恢复用例覆盖评估，基准 Web 恢复入口范围待产品确认。

复现包 `issue-443-evidence.zip` 包含浏览器和连接池探针、脱敏 JSON 结果、编排覆盖与运行指引。ZIP SHA-256 为 `291aa23c03513ef4436caa905be5f91c4a1d8cff48f036a5066e741a03a391c0`，解包后可用 `shasum -a 256 -c SHA256SUMS` 检查内容。验收后停止本次 Compose 服务，保留独立卷供复查。

## PostgreSQL 就绪恢复修复复测

在同一隔离 Compose 环境对比 `73e7050a` 与加入连接池修复的源码。修复镜像为 API `70393d5a230e` 和 worker `075fa9811676`，使用原生产 Web 镜像。PostgreSQL 连接池在借出连接前检查可用性，失效时换用新连接。

- **数据库回归**。用真实 PostgreSQL 15.19 终止一条空闲池连接，控制连接等待终止确认。基线首次借用后查询抛出 `AdminShutdown`。修复后首次查询成功并返回新 backend PID。用例位于 `tests/test_api_database.py`，通过 `TEST_POSTGRESQL_URL` 选择隔离 PostgreSQL 实例。
- **生产入口回归**。Chromium 登录后通过 Nginx 预热三个业务池。停止 PostgreSQL 时，就绪和业务请求均为 503。恢复就绪 200 后，实验创建、A/B 创建、基准套件列表的首次请求在基线均为 500，修复后分别为 201、201、200。故障注入前后 API 容器标识与启动时间一致。
- **入口门禁复测**。修复镜像上登录、深链接、分包和 SVG 均返回 200。数据库不可用时静态入口返回 200，业务和新 WS 握手返回 503，恢复后同源 WS 收到 `connected` 和 `pong`。
- **相关测试**。`python3 -m pytest tests/test_api_database.py tests/test_api_readiness.py tests/test_api_experiment_benchmark.py -q --no-cov` 返回 105 通过、1 跳过。跳过项为上述需要真实 PostgreSQL 的用例，已在隔离容器内分别执行失败与通过检查。
- 本轮取证范围是数据库恢复和生产入口。本节的四条业务链取证沿用原候选。两项修复后的统一复验见下文。

## 2026-11-10 统一候选复验

候选提交 `96951b4fa0ed7aa4df5beb1c24526b34ca1cdd64` 同时包含 PostgreSQL 恢复和基准默认策略修复。从干净源码构建生产镜像，在 Docker Desktop Linux ARM64 上启动独立项目 `harness-443-candidate`。镜像 ID 为 Web `28cf19591d25`、API `8e778db9fdb0`、worker `afe27a8153d5`、beat `c65757d1e8c2`。初次构建的镜像站对 Node 与 Docker CLI 基础镜像返回 503，从 Docker 官方 registry 取得相同摘要后构建通过。

- **发布入口与 PostgreSQL**。Chromium 登录、硬刷新受保护路由、分包与公共 SVG 均为 200。真实 PostgreSQL 停止时就绪、业务请求和新 WS 握手均为 503，静态入口保持 200。就绪恢复后，首次实验创建、A/B 创建及基准套件列表为 201、201、200。WS 收到 `connected/pong`。真实 PostgreSQL 空闲连接终止用例及真实 Docker 沙箱预检通过。
- **基准**。浏览器保持策略留空。实际 worker 使用 `vanilla` 完成 3/3，准确率 100%，刷新后的学习曲线包含该运行。策略同样留空的低预算运行仅调用一次替身后暂停，点击「刷新运行」读回暂停状态。自动回归分别覆盖省略策略、空数组及显式策略参数。前两种在修复前失败，修复后三种均通过。
- **实验与 A/B**。浏览器创建并启动，真实 Celery 和 Docker 沙箱执行完成。分别重启 API 后，比较报告和 A/B 统计可回读。实验在启动前移走原数据集文件，仍使用冻结快照执行三道题。
- **评估**。浏览器创建并启动三题评估，主动断开 WebSocket 后观察到 HTTP 回读及重新订阅。一个单元完成后暂停，重启 worker，再用同一任务 ID 恢复。替身共收到三个题目标记，各一次。刷新读回 3/3，通过页面下载 Markdown，单次分析可读。
- **回归测试**。143 通过，1 项 PostgreSQL 用例在宿主跳过后，于候选 API 容器连接真实 PostgreSQL 单独通过。Black、Ruff、Markdown 格式和 OpenSpec 严格校验通过。

```sh
python3 -m pytest tests/test_api_experiment_benchmark.py tests/test_benchmark_task.py tests/test_benchmark_run_budget.py tests/test_api_database.py tests/test_api_readiness.py tests/test_deployment_readiness.py -q --no-cov
./compose build
./compose up -d --wait --wait-timeout 100
./verify-candidate.sh
```

模型目录和生成仍由隔离替身提供。真实供应商联调待专用凭证和预算授权。脱敏包 `issue-443-candidate-evidence.zip` 包含本次结果与复现命令，SHA-256 为 `4024ce8875f9004a26bf1f1fd1de9ad62ae843796c5453259158836957ee50e3`。
