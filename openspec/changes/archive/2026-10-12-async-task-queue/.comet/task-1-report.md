# Task 1 实施报告：Celery 基础设施搭建

## 实施概要

成功搭建了 Celery + Redis 异步任务队列的基础设施，包括 Celery 应用配置、依赖管理、环境变量配置和 worker 启动脚本。遵循 TDD 原则，先编写测试，观察失败，然后实现最小代码使测试通过。

## 创建的文件

1. **src/celery_app.py** - Celery 应用实例和配置
   - 创建 `celery_app` Celery 实例，应用名称为 "llm_harness"
   - 实现 `configure_celery()` 函数配置 Celery 参数
   - 配置 broker URL、result backend、序列化器为 JSON
   - 配置任务路由：evaluation 任务路由到 evaluations 队列
   - 配置两个队列：default 和 evaluations
   - 设置 worker 参数：prefetch_multiplier=1, max_tasks_per_child=50
   - 启用任务跟踪和 acks_late 模式

2. **.env.example** - 环境变量模板
   - CELERY_BROKER_URL=redis://localhost:6379/0
   - CELERY_RESULT_BACKEND=redis://localhost:6379/0
   - TASK_SERVICE_ROOT=./data/tasks

3. **scripts/start_worker.sh** - Worker 启动脚本
   - 设置 PYTHONPATH
   - 启动 Celery worker，并发度为 4
   - 监听 evaluations 和 default 队列
   - 已赋予执行权限 (chmod +x)

4. **tests/test_celery_app.py** - Celery 应用测试
   - 测试 celery_app 实例存在和名称正确
   - 测试 broker URL 配置
   - 测试 result backend 配置
   - 测试任务序列化器使用 JSON
   - 测试队列配置（default 和 evaluations）
   - 测试任务路由配置

5. **tests/test_config_celery.py** - 配置设置测试
   - 测试 Settings 类包含 CELERY_BROKER_URL
   - 测试 Settings 类包含 CELERY_RESULT_BACKEND
   - 测试 Settings 类包含 TASK_SERVICE_ROOT

## 修改的文件

1. **requirements.txt** - 添加依赖
   ```txt
   # Async Task Queue
   celery[redis]>=5.3.0
   redis>=5.0.0
   ```

2. **api/config.py** - 添加 Celery 配置项到 Settings 类
   ```python
   # Celery 配置
   CELERY_BROKER_URL: str = "redis://localhost:6379/0"
   CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"

   # TaskService 存储路径
   TASK_SERVICE_ROOT: str = "./data/tasks"
   ```

## TDD 流程记录

### 第一轮：Settings 配置测试
- **RED**: 编写 `tests/test_config_celery.py`，3 个测试失败（AssertionError: hasattr 返回 False）
- **GREEN**: 修改 `api/config.py`，添加三个配置字段
- **VERIFY**: 所有 3 个测试通过 ✓

### 第二轮：Celery 应用测试
- **RED**: 编写 `tests/test_celery_app.py`，6 个测试失败（ModuleNotFoundError: No module named 'src.celery_app'）
- **GREEN**: 
  1. 添加依赖到 requirements.txt
  2. 安装依赖：`pip install celery[redis]>=5.3.0 redis>=5.0.0`
  3. 创建 `src/celery_app.py` 按规格实现 Celery 配置
- **VERIFY**: 所有 6 个测试通过 ✓

### 第三轮：创建辅助文件
- 创建 `.env.example` 环境变量模板
- 创建 `scripts/start_worker.sh` worker 启动脚本
- 赋予脚本执行权限

## 测试命令及输出

### 测试执行
```bash
python3 -m pytest tests/test_celery_app.py tests/test_config_celery.py -v
```

**结果**：9 个测试全部通过
- tests/test_celery_app.py::test_celery_app_exists PASSED
- tests/test_celery_app.py::test_celery_app_broker_url_configured PASSED
- tests/test_celery_app.py::test_celery_app_result_backend_configured PASSED
- tests/test_celery_app.py::test_celery_app_task_serializer_json PASSED
- tests/test_celery_app.py::test_celery_app_queues_configured PASSED
- tests/test_celery_app.py::test_celery_app_task_routes_configured PASSED
- tests/test_config_celery.py::test_settings_has_celery_broker_url PASSED
- tests/test_config_celery.py::test_settings_has_celery_result_backend PASSED
- tests/test_config_celery.py::test_settings_has_task_service_root PASSED

### 验证命令
```bash
python3 -c "from src.celery_app import celery_app; print(celery_app.conf.broker_url)"
```

**输出**：`redis://localhost:6379/0` ✓

### Worker 启动脚本验证
```bash
ls -l scripts/start_worker.sh
```

**输出**：`-rwxr-xr-x@ 1 charlesleclerc staff 253 Oct 12 15:26 scripts/start_worker.sh` ✓

## Git 提交

**Commit Hash**: fa2a7e55b5d6e0c9c1d45f25b1b68a2d8229d745

**Commit Message**: 
```
feat: add Celery基础设施配置

- 添加 Celery 和 Redis 依赖到 requirements.txt
- 创建 src/celery_app.py 配置 Celery 应用
- 更新 api/config.py 添加 Celery 配置项
- 创建 .env.example 环境变量模板
- 创建 scripts/start_worker.sh worker 启动脚本
- 添加测试覆盖 Celery 配置和应用
```

**变更统计**:
- 7 files changed, 168 insertions(+)
- create mode 100644 .env.example
- create mode 100755 scripts/start_worker.sh
- create mode 100644 src/celery_app.py
- create mode 100644 tests/test_celery_app.py
- create mode 100644 tests/test_config_celery.py

## 验收标准检查

- [x] Celery 依赖已添加到 requirements.txt
- [x] Celery 依赖已成功安装
- [x] `src/celery_app.py` 文件已创建，包含完整配置
- [x] `api/config.py` 已添加 Celery 相关配置字段
- [x] `.env.example` 文件已创建，包含 Celery 环境变量
- [x] `scripts/start_worker.sh` 已创建且具有执行权限
- [x] 验证命令成功执行，输出正确的 broker URL
- [x] 所有变更已提交到 Git

## 风险信号评估

根据风险信号清单评估：

- ❌ 跨模块/跨子系统协调变更：否 - 仅添加新的独立模块
- ❌ 安全敏感区域：否 - 配置不涉及认证、授权或加密
- ✅ **并发、锁、共享可变状态**：是 - Celery 是异步任务队列，涉及并发执行
- ❌ 数据或模式迁移：否 - 无数据库迁移
- ❌ 公共 API 契约或外部接口变更：否 - 内部基础设施
- ❌ 返回 DONE_WITH_CONCERNS：否
- ❌ 单任务 diff 超过 200 行：否 - 总共 168 行新增

**命中的风险信号**：
1. **并发、锁、共享可变状态** - Celery worker 将并发执行任务，需要注意：
   - 任务应该是幂等的
   - 避免在任务间共享可变状态
   - 数据库操作需要在事务内完成（已在全局约束中声明）
   - worker 配置了 `task_acks_late=True` 和 `task_reject_on_worker_lost=True` 提高可靠性

## 决策和关注点

### 决策
1. **使用 JSON 序列化器**：选择 JSON 而非 pickle，提高安全性和跨语言兼容性
2. **队列设计**：创建 default 和 evaluations 两个队列，将评估任务隔离到专用队列
3. **Worker 配置**：
   - prefetch_multiplier=1：避免长时间运行任务阻塞其他任务
   - max_tasks_per_child=50：定期重启 worker 进程防止内存泄漏
4. **延迟配置**：使用 `configure_celery()` 函数延迟导入 settings，避免循环依赖

### 关注点
1. **Redis 依赖**：基础设施需要 Redis 服务运行，在 README 或部署文档中需要说明
2. **任务发现**：配置了 `autodiscover_tasks(["src.tasks"])`，但 `src/tasks` 目录尚未创建，将在后续任务中实现
3. **环境变量**：`.env.example` 仅为模板，实际部署需要创建 `.env` 文件
4. **错误处理**：全局约束要求区分业务错误和基础设施错误，需要在后续任务实现中注意

## 接口契约履行

### Produces（已实现）
- ✅ `celery_app: Celery` - 配置好的 Celery 应用实例已导出
- ✅ 环境变量：`CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `TASK_SERVICE_ROOT` 已定义

### Consumes
- 无依赖

## 总结

Task 1 已成功完成，所有验收标准均已满足。Celery 基础设施已搭建完毕，为后续任务（TaskService、评估任务实现、API 端点）提供了坚实的基础。遵循 TDD 原则，所有代码均有测试覆盖，测试先行确保了实现的正确性。
