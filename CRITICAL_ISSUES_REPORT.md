# 代码审查 CRITICAL 问题修复清单

## 状态
验证失败，需修复后重新验证（失败计数：1/3）

## CRITICAL-1: Resume 端点不创建新 Celery 任务 ⏳ 待修复

**位置**: `api/routes/tasks.py:172-207`

**问题**: `/api/v1/tasks/{task_id}/resume` 端点只更新数据库状态为 "running"，但未提交新 Celery 任务。原始 Celery 任务已不存在，无法恢复执行。

**修复步骤**:
1. 参考 `api/services/evaluation_service.py:337` 的 `resume_evaluation()` 方法
2. 改造 resume 端点调用 `manager.create_task()` 而非手动更新状态
3. 移除 line 196 的未使用 `celery_app` import
4. 更新文档字符串确保描述准确

## CRITICAL-2: Worker 函数是占位符 ⏳ 待修复

**位置**: `src/tasks/evaluation.py:157-165`

**问题**: `worker()` 函数返回模拟数据 `{"success": True, "mock": True}`，注释标注为占位符。评估永不真正执行。

**修复步骤**:
1. 实现真实评估逻辑
2. 调用 LLM 执行引擎（参考 `src/main.py` 或策略模块）
3. 返回真实执行结果（success, cost, output 等）
4. 修复后需更新对应单元测试

## CRITICAL-3: 数据库会话工厂未初始化 ✅ 已修复

**位置**: `api/db/engine.py` + `api/main.py`

**修复验证**: `api/main.py:41` 确认已调用 `set_session_factory(session_factory)`

**状态**: 该 CRITICAL 问题已解决 ✅

---

## 下一步行动

1. 修复 CRITICAL-1 和 CRITICAL-2
2. 运行完整测试套件验证
3. 提交 git commit: `fix: resolve critical issues from code review`
4. 返回 verify 阶段重新验证
