# 真实评估 QA：fixture 与 live 联调

2026-10-27 已在 PR #284 原分支完成真实登录→模型选项→创建/启动→Redis/Celery→DeepSeek→Docker→实时进度→结果页。最终运行通过，1 题、1 个 vanilla 策略、179 tokens、1/1 成功。两次真实生成的应用记录费用合计 US$0.0001362，授权累计上限 US$0.10。该金额按配置价格估算，不是供应商结算账单。

前置 #231 已通过 [PR #292](https://github.com/JayNey/LLM-Algorithm-Harness/pull/292) 合入 main（`7efbecb`），本分支包含该提交。原 PR 的“未进行真实端到端联调”盘点已由本次实际证据更新。

## 验证层级与证据

- 浏览器：本机 Chrome/Playwright，真实 React 路由、Cookie 登录和 CSRF；没有业务 HTTP 拦截或 socket 替换。使用既有 Frontier 外壳，截图为 Orbit 深色桌面；完整外观矩阵属于独立 fixture 验证。
- API/数据库：本机 FastAPI `127.0.0.1:8000`，独立认证 SQLite 和业务 SQLite；专用测试账号和本人授权的 provider key，未覆盖原数据库。
- 队列：独立 Redis `127.0.0.1:6380/0`、真实 Celery solo worker。任务有独立 AsyncTask/Celery ID 及开始/结束时间。
- 模型：`deepseek` provider，固定 `https://api.deepseek.com`，实际模型枚举、模型验证和两次 `/chat/completions` HTTP 200；应用缓存关闭。账号日/月调用计数均为 2（两种周期，不是 4 次调用）。
- 沙箱：实际 Docker `python:3.11-slim`，2 个公开用例；独立静态加法预检和模型生成代码均通过。镜像 digest、版本及独立计量见环境 JSON。
- 实时进度：真实 Cookie 认证 WebSocket，URL 不带 token；最终收到 `connected`、`task.snapshot`、`subscribed`、`task.started`、`problem.completed`、`task.progress`、`task.completed`。
- 结果：持久化成功单元 1/1、179 tokens、单轮 US$0.0000681。API 的 `run_id` 为 null，页面明确“运行记录：未关联”；没有用 evaluation/AsyncTask ID 冒充 run_id。

公开证据随仓库保存，不依赖临时 CI artifact 的有效期：

- [最终通过运行](assets/evaluations/live/run-20261027091524702.json)：源代码 `9fab9b7`，UTC 请求状态/进度、哈希 ID、结果和预算。
- [结果页截图](assets/evaluations/live/run-20261027091524702-result.png)：用户名、评估及任务标识已遮盖；只包含公共合成题目。
- [独立环境/调用/沙箱核对](assets/evaluations/live/environment-20261027.json)。
- [第一次运行失败记录](assets/evaluations/live/run-20261027090748797.json)：模型/沙箱完成，但 WebSocket 未连接；如实保留 `pass=false`。
- [验证命令与退出码](assets/evaluations/live/checks-20261027.json)及[完整验收报告](../superpowers/reports/2026-10-26-evaluation-live-evidence-verify.md)。

未覆盖：PostgreSQL、生产部署、多 worker 并发、其他供应商真实调用、移动端真实模型运行、故意耗尽余额或禁用模型/沙箱的付费负向试验。本次小规模 smoke 不代替这些专项验收，也不代表 #233 交付汇总完成。

## 失败与修复

首次浏览器预探测因 Ant Design 双字按钮的可访问名称带空格而没有提交注册，未产生生成调用；脚本改为匹配真实可访问名称。第一次付费运行的结果已成功，但新装的 Uvicorn 没有 WebSocket 传输库，服务器返回 upgrade 警告和 404，页面正常降级轮询。补充 `websockets` 运行依赖、重启隔离 API 后，第二次运行在剩余预算内验证了完整实时事件。后续独立审查还将守卫加强为同一评估的完整生命周期事件（提交 `2dd4188`），16 项纯自检和历史成功/失败 JSON 正反复核通过；没有为这次脚本加强再调用模型，原 live 源码 SHA 仍为 `9fab9b7`。live 脚本现在先做真实 WebSocket 握手，失败即停止，不先消耗生成额度。

两次单轮均为 179 tokens 和 US$0.0000681；worker 日志分别存在真实供应商 POST 200，缓存关闭，并非重复使用第一次结果。公开文件只保存聚合事实，不提交原始日志、模型凭证、密码、Cookie 或私有数据库。

## Fixture 复现

在 `frontend/` 启动 Vite（所需 `VITE_*` 见下一节），另一个终端运行：

```bash
EVALUATION_BASE_URL=http://localhost:3000 \
EVALUATION_QA_DIR=/private/tmp/harness-evaluation-fixture \
PLAYWRIGHT_MODULE="$LIVE_RUNTIME_DIR/browser/node_modules/playwright" \
CHROME_PATH='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' \
node scripts/verify-evaluations.mjs --scenario all
```

fixture 会替换身份、业务 HTTP 和进度事件，覆盖创建、任务、权限、结果及外观矩阵。它与 `verify-evaluations-live.mjs` 独立；输出目录也要分开。本轮脱敏断言见 [fixture summary](assets/evaluations/live/fixture-summary-20261027.json)；既有外观截图索引见 [QA.md](QA.md#229-验收证据与截图索引)。fixture 通过不能作为真实依赖可用的证据。其他系统可设置 `CHROME_PATH`，或安装 Playwright Chromium。

## Live 复现：隔离配置

以下从仓库根操作，要求 Python 3.11、Node/npm、uv、Redis、Docker 和可用 Chrome。先更新 main 并确认 #231 前置。需要新的真实调用时，必须仍有用户授权的凭证范围和预算；不要重置本轮已用完的 2 次账号配额来追加调用。

```bash
umask 077
export LIVE_RUNTIME_DIR="$(mktemp -d /private/tmp/harness-live-232-XXXXXX)"
python3.11 -m venv "$LIVE_RUNTIME_DIR/venv"
uv pip install --python "$LIVE_RUNTIME_DIR/venv/bin/python" -e '.[dev]'
npm --prefix frontend ci
npm --prefix "$LIVE_RUNTIME_DIR/browser" install playwright
export LIVE_PYTHON="$LIVE_RUNTIME_DIR/venv/bin/python"
export PLAYWRIGHT_MODULE="$LIVE_RUNTIME_DIR/browser/node_modules/playwright/index.mjs"
```

已有、获授权的 `config.json` 须含 `llm_config.api_key` literal、`model=deepseek-flash` 和官方 `base_url=https://api.deepseek.com`。脚本将其作为 DeepSeek 提交，不复制其中可能历史遗留的 `provider=openai`。不要将配置文件加入 Git，不从 Codex/其他用户账号获取供应商凭证。

生成私有配置（不输出任何密钥值）：

```bash
"$LIVE_PYTHON" - <<'PY'
import json, os, secrets
from pathlib import Path
from cryptography.fernet import Fernet
r = Path(os.environ['LIVE_RUNTIME_DIR']).resolve()
r.chmod(0o700)
values = {
    'SECRET_KEY': secrets.token_urlsafe(48),
    'ENCRYPTION_KEY': Fernet.generate_key().decode(),
    'AUTH_DATABASE_PATH': str(r / 'auth.sqlite3'),
    'DATABASE_URL': 'sqlite:///' + str(r / 'business.sqlite3'),
    'UPLOAD_DIR': str(r / 'uploads'),
    'TASK_SERVICE_ROOT': str(r / 'tasks'),
    'CELERY_BROKER_URL': 'redis://127.0.0.1:6380/0',
    'CELERY_RESULT_BACKEND': 'redis://127.0.0.1:6380/0',
    'AUTH_RATE_LIMIT': '1000', 'AUTH_PROTECTED_RATE_LIMIT': '1000',
    'USER_DAILY_API_CALL_LIMIT': '2', 'USER_MONTHLY_API_CALL_LIMIT': '2',
    'CORS_ORIGINS': '["http://localhost:3000","http://127.0.0.1:3000"]',
}
(r / 'services.env').write_text(''.join(f'{k}={json.dumps(v)}\n' for k, v in values.items()))
name = 'live232_' + secrets.token_hex(6)
(r / 'credentials.json').write_text(json.dumps({
    'username': name, 'email': name + '@example.invalid',
    'password': secrets.token_urlsafe(24), 'budget_usd': '0.10',
    'project_config': str(Path('config.json').resolve()),
}))
for name in ('services.env', 'credentials.json'):
    (r / name).chmod(0o600)
PY
```

API 和 worker 必须加载同一个 `services.env`，否则 Cookie/加密密钥或数据库不一致会导致认证失败。强 `SECRET_KEY` 与有效 Fernet `ENCRYPTION_KEY` 是必填；不能只设置供应商 API key 来代替应用认证配置。

## Live 复现：启动、预检和执行

先确认 8000、3000、6380 空闲；6380 若已占用，改用新的独立端口，并同步 env 中 broker/backend，不能连接其他任务的 Redis。

```bash
redis-server --bind 127.0.0.1 --port 6380 --save '' --appendonly no \
  --daemonize yes --pidfile "$LIVE_RUNTIME_DIR/redis.pid" \
  --logfile "$LIVE_RUNTIME_DIR/redis.log"
docker info
docker pull python:3.11-slim
```

从仓库根，在两个前台终端分别启动 API 和 worker；两个终端都要使用相同的 `LIVE_RUNTIME_DIR`：

```bash
"$LIVE_PYTHON" -m dotenv -f "$LIVE_RUNTIME_DIR/services.env" run -- \
  "$LIVE_PYTHON" -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

```bash
"$LIVE_PYTHON" -m dotenv -f "$LIVE_RUNTIME_DIR/services.env" run -- \
  "$LIVE_PYTHON" -m celery -A src.celery_app worker \
  --pool=solo --concurrency=1 --loglevel=INFO --hostname='live232@%h'
```

第三个终端在 `frontend/` 启动真实前端：

```bash
VITE_API_BASE_URL=/api/v1 \
VITE_WS_URL=ws://localhost:3000/api/v1/ws/progress \
VITE_APP_NAME='Harness Live QA' \
npm run dev -- --host 127.0.0.1 --port 3000 --strictPort
```

在仓库根检查 `curl -f http://127.0.0.1:8000/api/v1/health`、`redis-cli -p 6380 ping` 和 worker ready。API 启动迁移完成后，导入公开合成题目并执行真实沙箱预检（不调用模型）：

```bash
"$LIVE_PYTHON" - <<'PY'
import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(os.environ['LIVE_RUNTIME_DIR']) / 'services.env', override=True)
from api.db.engine import make_engine, make_session_factory, business_database_url
from api.db.problem_store import ProblemStore
from src.models import Problem, SandboxConfig
from src.sandbox_executor import SandboxExecutor
record = {
    'problem_id': 'live232-add', 'title': 'Live QA: add two integers',
    'description': 'Implement solution(a, b) returning the sum of two integers. Return only a Python function.',
    'difficulty': 'easy',
    'test_cases': [
        {'input': {'a': 2, 'b': 3}, 'expected_output': 5},
        {'input': {'a': -1, 'b': 4}, 'expected_output': 3},
    ],
}
engine = make_engine(business_database_url())
ProblemStore(make_session_factory(engine)).upsert_import([record])
result = SandboxExecutor(SandboxConfig()).execute('def solution(a, b):\n    return a + b\n', Problem(**record))
assert result.status == 'success' and result.all_passed
engine.dispose()
print('PASS: isolated problem import and real Docker sandbox')
PY
```

在 `frontend/` 运行：

```bash
node scripts/verify-evaluations-live.mjs --self-test
LIVE_QA_DIR=../docs/frontend/assets/evaluations/live \
node scripts/verify-evaluations-live.mjs
```

脚本创建专用账号并真实登录、保存本人密钥、加载供应商模型列表、选择单题/vanilla、设置预算后真实创建/启动。默认本地 UI；可用 `LIVE_UI_URL` 指定 localhost origin，`CHROME_PATH` 指定浏览器。输出仅包含状态、UTC、哈希 ID、数值和脱敏截图；原始错误仅写入私有 runtime 目录。不要将整个 runtime 打包上传。

本轮以 [官方价格页](https://api-docs.deepseek.com/quick_start/pricing/) 2026-10-27 高峰 cache-miss 价格作为保守单价：输入 US$0.30/百万 tokens、输出 US$1.20/百万 tokens。生成上限 2000 tokens、关闭 thinking、SDK 重试关闭、账号日/月生成尝试最多 2 次；实际 prompt 616 bytes 加 256 余量，计算双次上界 US$0.0053232。脚本为该模型保存应用价格 override；模型验证/枚举不计生成尝试。未来复现先重新确认价格，变价后同步守卫与 override。

`browser-state.json` 防止失败后重复提交；有已确认 ID 时默认只恢复观察。仅在核对上次 completed、费用和剩余授权后，才使用一次 `--retry-completed` 创建新的 smoke；脚本保留之前评估与费用，拒绝第二次重试，服务器配额仍是累计 2 次。未知提交结果时先调查私有数据库，不删除状态文件重试。禁止用关闭失败断言或重放 fixture 的方式生成通过证据。

## 退出与清理

核对终态和公开证据后，停止本轮 API/worker/Vite 前台进程（Ctrl-C）。若用后台进程，先核对私有 pid 文件对应的命令，再发 SIGTERM，不按进程名批量停止。对本轮 Redis 使用 `redis-cli -p 6380 shutdown nosave`。沙箱容器由执行器自动移除，不清理全局 Docker 资源。

既有 evaluation worker 的 TaskService 仍使用 `data/tasks/<evaluation_id>/`，不读取 API 的 `TASK_SERVICE_ROOT`。它会在仓库下生成本轮两个未跟踪运行记录（仅公共合成题目）。本轮已按私有 browser state 确认归属后将其移入受限 runtime，未提交或删除其他任务文件；未来复现须同样只处理本轮 ID 对应目录。API `run_id=null` 的现状仍如实保留，本 change 未修改这两项既有行为。

保留公开 JSON、已遮盖截图和校验清单；在证据目录执行 `shasum -a 256 -c SHA256SUMS` 可检查文件完整性。私有目录只保留本地诊断所需时间，随后删除其中测试账号、加密 key、数据库、日志和浏览器状态；不要删除源 `config.json`、原有用户库或其他任务目录。清理后重新运行必须重新建立隔离环境，并另行核对调用授权和累计预算。
