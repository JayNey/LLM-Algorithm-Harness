"""Documentation-only enrichment of FastAPI's generated OpenAPI document.

Keep wire models and security dependencies in the routes. This module supplies
human explanations and illustrative payloads for the existing API, including
open dictionary responses that cannot be inferred from Python annotations.
"""

from __future__ import annotations

import json
import shlex
from copy import deepcopy
from typing import Any
from urllib.parse import urlencode

from fastapi import FastAPI

from api.middleware.errors import HTTP_CODES, ErrorCode

STAMP = "2026-10-19T00:00:00Z"
USER = {"id": "user-demo", "username": "demo", "email": "demo@example.com", "created_at": STAMP}
KEY = {
    "id": "key-demo",
    "provider": "openai",
    "key_name": "Demo key",
    "created_at": "2026-10-19T00:00:00Z",
    "last_used_at": None,
    "usage_count": 0,
    "verification_count": 0,
    "last_verified_at": None,
    "verified": False,
    "masked_preview": "sk-***demo",
}
EVALUATION = {
    "evaluation_id": "eval-demo",
    "created_at": STAMP,
    "updated_at": STAMP,
    "status": "pending",
    "can_start": True,
    "can_cancel": False,
    "execution_progress": {"completed_units": 0, "total_units": 1, "percentage": 0.0},
    "strategy_names": ["vanilla"],
    "model": "gpt-4o-mini",
    "problem_count": 1,
    "spent_usd": 0.0,
    "budget_cap_usd": 1.0,
    "error_message": None,
    "progress": None,
}
TASK = {
    "id": "task-demo",
    "task_type": "evaluation",
    "entity_id": "eval-demo",
    "celery_task_id": "celery-demo",
    "status": "pending",
    "progress": None,
    "error_message": None,
    "created_at": STAMP,
    "started_at": None,
    "completed_at": None,
    "updated_at": STAMP,
}
JOB = {
    "id": "experiment-demo",
    "name": "Demo",
    "status": "pending",
    "config": {},
    "error_message": None,
    "created_at": STAMP,
    "updated_at": STAMP,
}
SUITE = {
    "id": "suite-demo",
    "name": "Demo suite",
    "version": "1.0",
    "description": "One problem",
    "frozen": False,
    "problems": ["two-sum"],
    "created_at": STAMP,
    "updated_at": STAMP,
}
BUDGET = {
    "global_cap_usd": 10.0,
    "difficulty_caps": {"easy": 2.0},
    "action": "pause",
    "created_at": STAMP,
    "updated_at": STAMP,
}
RULE = {
    "id": "rule-demo",
    "name": "Budget alert",
    "threshold_pct": 80,
    "channel": "log",
    "target": "",
    "enabled": True,
    "created_at": STAMP,
    "updated_at": STAMP,
}
FILE = {
    "id": "file-demo",
    "filename": "problems.json",
    "suffix": ".json",
    "category": "upload",
    "size": 128,
    "sha256": "0000000000000000000000000000000000000000000000000000000000000000",
    "created_at": 1792368000,
    "expires_at": 1792454400,
    "run_id": None,
}


def page(items: list[Any]) -> dict[str, Any]:
    return {"items": items, "total": len(items), "limit": 20, "offset": 0, "has_more": False}


# Handler name -> purpose, response data. Aliased paths share the same contract.
# Examples show representative data; empty aggregates mean no stored results.
OPERATIONS: dict[str, tuple[str, Any]] = {
    "health_check": (
        "检查 API 进程存活；不检查数据库、队列或执行器。",
        {
            "status": "healthy",
            "scope": "api_liveness_only",
            "version": "0.1.0",
            "service": "LLM Algorithm Harness API",
        },
    ),
    "register": ("注册用户；用户名或邮箱已被使用时返回 409。密码至少 12 个字符。", USER),
    "login": (
        "使用用户名或邮箱及密码登录，返回访问令牌和可轮换刷新令牌。",
        {
            "access_token": "ACCESS_TOKEN",
            "refresh_token": "REFRESH_TOKEN",
            "token_type": "bearer",
            "expires_in": 1800,
        },
    ),
    "refresh": (
        "轮换刷新令牌并取得新令牌对；旧刷新令牌立即失效。",
        {
            "access_token": "NEW_ACCESS_TOKEN",
            "refresh_token": "NEW_REFRESH_TOKEN",
            "token_type": "bearer",
            "expires_in": 1800,
        },
    ),
    "logout": ("撤销当前登录会话；该会话的访问令牌和刷新令牌随即失效。", None),
    "me": ("查询当前用户资料和由服务器配置决定的 user/admin 角色。", {**USER, "role": "user"}),
    "update_me": ("修改自己的用户名或邮箱；冲突返回 409。", USER),
    "change_password": ("校验当前密码后修改密码，并撤销该用户所有会话；随后需要重新登录。", None),
    "list_keys": ("列出自己的 LLM 提供商密钥元数据；不会返回明文或密文。", [KEY]),
    "add_key": ("加密保存提供商密钥，返回密钥 ID 和遮罩预览，供评估请求引用。", KEY),
    "update_key": ("修改自己保存的密钥名称或替换密钥值；不可访问其他用户密钥。", KEY),
    "delete_key": ("删除自己的提供商密钥。", None),
    "verify_key": (
        "使用自己的已保存密钥进行提供商连接检查；不执行评估。",
        {"ok": True, "provider": "openai", "message": "Connection verified"},
    ),
    "options": (
        "查询执行器支持的策略和有效题目来源；本人导入的同 ID 题目覆盖共享题目，仅列出非空来源。",
        {
            "strategies": [{"name": "vanilla"}],
            "sources": [{"id": "shared", "label": "共享题库", "problem_count": 1}],
        },
    ),
    "problems": (
        "按来源分页查询共享题库和本人导入的有效题目元数据；不返回题干、测试用例或他人题目。",
        page(
            [
                {
                    "problem_id": "two-sum",
                    "title": "Two Sum",
                    "difficulty": "easy",
                    "source": "shared",
                }
            ]
        ),
    ),
    "models": (
        "使用自己的 api_key_id 查询提供商真实模型列表；最多返回 500 个 ID。"
        "来源固定为 source=provider_api、scope=user_api_key，与监控配置的动态查询一致。"
        "complete=false 表示列表可能不完整；单次请求最多等待 5 秒，总预算 10 秒，不自动重试。"
        "查询期间密钥被修改返回 409，提供商调用失败返回脱敏的 503。",
        {
            "provider": "openai",
            "models": ["gpt-4o-mini"],
            "complete": True,
            "source": "provider_api",
            "scope": "user_api_key",
        },
    ),
    "create_evaluation": (
        "创建待运行评估，引用自己的 api_key_id 和已存在的题目；随后调用 start。",
        EVALUATION,
    ),
    "list_evaluations": ("分页查询自己的评估，可按状态过滤。", page([EVALUATION])),
    "get_evaluation": ("查询自己的单个评估及状态、预算和进度。", EVALUATION),
    "update_evaluation": ("仅修改 pending 评估的预算或单题超时；其他状态返回 400。", EVALUATION),
    "delete_evaluation": ("删除自己的评估及关联文件；不允许删除仍在运行的评估。", None),
    "start_evaluation": (
        "提交评估到后台队列；202 表示已受理，不表示已完成。",
        {**EVALUATION, "can_start": False, "can_cancel": True},
    ),
    "get_evaluation_progress": (
        "查询评估当前完成数量、总量及进度百分比。",
        {"current": 0, "total": 1, "message": None, "completed": 0, "percentage": 0.0},
    ),
    "cancel_evaluation": (
        "取消自己的评估，返回取消后的评估状态。",
        {**EVALUATION, "status": "cancelled", "can_start": False},
    ),
    "create_task": (
        "创建通用异步任务并提交给 Celery；task_type 与处理器须匹配服务器支持的类型。",
        TASK,
    ),
    "list_tasks": ("分页列出自己的异步任务，可按类型和状态筛选。", page([TASK])),
    "get_task": ("查询自己的异步任务，包括状态、进度、时间和错误信息。", TASK),
    "cancel_task": (
        "终止 pending/running 异步任务并标记 cancelled；DELETE 返回任务 JSON。",
        {**TASK, "status": "cancelled"},
    ),
    "pause_task": (
        "请求暂停正在运行的任务；具体暂停能力由任务处理器决定。",
        {**TASK, "status": "paused"},
    ),
    "resume_task": (
        "重新入队已暂停的 evaluation 任务，沿用同一个任务 ID；不支持的类型返回 400。",
        TASK,
    ),
    "problem_history": (
        "查询自己对指定题目的历史执行单元，status 过滤执行结果状态。",
        page(
            [
                {
                    "problem_id": "two-sum",
                    "strategy": "vanilla",
                    "status": "success",
                    "iterations": 1,
                    "tokens": 100,
                    "execution_time": 0.1,
                    "run_id": "run-demo",
                }
            ]
        ),
    ),
    "list_results": (
        "分页查询自己的评估运行记录；题目过滤条件匹配至少一个执行单元。",
        page(
            [
                {
                    "id": "eval-demo",
                    "run_id": "run-demo",
                    "status": "completed",
                    "model": "gpt-4o-mini",
                    "strategy_names": ["vanilla"],
                    "created_at": STAMP,
                    "completed_at": STAMP,
                }
            ]
        ),
    ),
    "get_result": (
        "读取一次运行的所有策略汇总及一页题目明细；接受自己的 evaluation ID 或 run ID。",
        {
            "run_id": "run-demo",
            "status": "completed",
            "created_at": STAMP,
            "completed_at": STAMP,
            "strategies": [],
            "problems": page([]),
        },
    ),
    "analytics_success_rate": (
        "计算所选执行单元的通过率、平均耗时及难度/标签分组。未指定 run_id 时仅统计自己的已完成评估。",
        {
            "success_rate": 0.0,
            "solved": 0,
            "total": 0,
            "avg_execution_time": 0.0,
            "by_difficulty": {},
            "by_tag": {},
        },
    ),
    "analytics_tokens": (
        "汇总 token 与已知估算成本；未知成本单独计数。未指定 run_id 时仅统计自己的已完成评估。",
        {"total_tokens": 0, "avg_tokens": 0.0, "estimated_cost_usd": 0.0, "unknown_cost_count": 0},
    ),
    "analytics_iterations": (
        "汇总已记录的迭代次数；未记录次数保持未知，不计为零。未指定 run_id 时仅统计自己的已完成评估。",
        {"known_count": 0, "unknown_count": 0, "average": None, "distribution": []},
    ),
    "analytics_failure_modes": (
        "统计未成功执行单元保存的 failure_mode；缺失值归为 unknown。未指定 run_id 时仅统计自己的已完成评估。",
        {"logic_error": 1, "unknown": 1},
    ),
    "visualization_success_rate_chart": (
        "返回每个策略的通过率图表点；数据用于前端绘图。",
        {"points": [{"name": "vanilla", "success_rate": 1.0}]},
    ),
    "visualization_token_chart": (
        "返回按策略分组的逐题 token 曲线；未记录的 token 为 null。",
        {"series": [{"name": "vanilla", "points": [{"problem_id": "two-sum", "tokens": 100}]}]},
    ),
    "visualization_cost_accuracy": (
        "返回策略的准确率与已知估算成本散点。",
        {"points": [{"name": "vanilla", "success_rate": 1.0, "estimated_cost_usd": 0.01}]},
    ),
    "visualization_capability_radar": (
        "按模型返回能力维度雷达数据及题量；缺失维度得分为零。",
        {"dimensions": [], "series": [], "problem_counts": {}},
    ),
    "visualization_learning_curve": (
        "查询自己的已完成基准运行，按完成时间升序生成学习曲线。",
        {"series": []},
    ),
    "failures_by_tag": (
        "按题目标签汇总通过率、通过数和总数。",
        {"tags": {"array": {"success_rate": 0.5, "solved": 1, "total": 2}}},
    ),
    "failure_summary": (
        "汇总指定运行保存的失败模式、类别及规范化错误消息聚类。",
        {"modes": {}, "categories": {}, "clusters": []},
    ),
    "failure_cases": (
        "列出指定运行所有未成功的题目单元和已保存的错误消息。",
        {
            "items": [
                {
                    "problem_id": "two-sum",
                    "strategy": "vanilla",
                    "status": "failed",
                    "error_message": "Wrong answer",
                }
            ]
        },
    ),
    "compare_strategies": (
        "比较一次运行各策略的汇总指标；必须提供 run_id，否则返回 400。",
        {"strategies": []},
    ),
    "compare_models": ("按模型汇总自己已完成运行的策略表现。", {"models": []}),
    "compare_history": (
        "比较同模型、同策略集合的其他已完成运行；排除当前运行，必须提供 run_id。",
        {"series": []},
    ),
    "compare_ab_test": (
        "查询自己的 A/B 测试结果，与 ab-tests/{test_id}/results 使用同一结果服务。",
        {"test_id": "test-demo", "status": "pending"},
    ),
    "report_markdown": ("下载一次运行的 Markdown 报告，响应为 UTF-8 文本附件。", None),
    "report_html": ("下载一次运行的 HTML 报告，响应为 HTML 附件。", None),
    "report_csv": ("下载一次运行的题目明细 CSV，包含 UTF-8 BOM；未知指标留空。", None),
    "upload_file": (
        "以 multipart/form-data 上传一个文件，校验后保存并返回元数据。",
        {
            "file": {
                "id": "file-demo",
                "filename": "problems.json",
                "suffix": ".json",
                "category": "upload",
                "size": 128,
                "sha256": "0000000000000000000000000000000000000000000000000000000000000000",
                "created_at": 1792368000,
                "expires_at": 1792454400,
                "run_id": None,
            },
            "parsed": True,
        },
    ),
    "upload_problems": (
        "上传并同步导入题目；mode 为 append 或 overwrite，必须启用 schema 校验。",
        {"file_id": "file-demo", "job_id": "job-demo", "validation": {"valid": True}},
    ),
    "import_uploaded": (
        "把自己的已上传题目文件加入异步导入队列；轮询 imports/{job_id}。",
        {"job_id": "job-demo", "task_id": "task-demo", "status": "pending"},
    ),
    "import_progress": (
        "查询自己的导入任务进度、完成比例和校验结果。",
        {
            "job_id": "job-demo",
            "status": "pending",
            "processed": 0,
            "total": 0,
            "percentage": 0,
            "result": None,
        },
    ),
    "upload_config": (
        "上传并校验 harness 或 experiment YAML/JSON 配置；默认最大 1 MiB。",
        {
            "file": {
                "id": "file-demo",
                "filename": "config.yaml",
                "suffix": ".yaml",
                "category": "configs",
                "size": 128,
                "sha256": "0000000000000000000000000000000000000000000000000000000000000000",
                "created_at": 1792368000,
                "expires_at": 1792454400,
                "run_id": None,
            },
            "config_type": "harness",
            "config": {
                "llm_config": {
                    "provider": "openai",
                    "api_key": "[REDACTED]",
                    "model": "gpt-4o-mini",
                    "base_url": None,
                    "temperature": 0.7,
                    "max_tokens": 2000,
                    "timeout": 30,
                    "enable_thinking": None,
                    "retry_max_attempts": 3,
                    "retry_backoff_seconds": 0.5,
                    "retry_max_elapsed_seconds": 60.0,
                    "cache": {
                        "enabled": True,
                        "backend": "disk",
                        "ttl_days": 30,
                        "max_size_mb": 1000,
                    },
                },
                "sandbox_config": {
                    "backend": "docker",
                    "docker_image": "python:3.11-slim",
                    "timeout_seconds": 5,
                    "memory_limit_mb": 256,
                    "max_output_bytes": 1000000,
                    "max_processes": 16,
                    "allowed_imports": [
                        "math",
                        "itertools",
                        "collections",
                        "heapq",
                        "bisect",
                        "functools",
                        "sys",
                        "json",
                    ],
                },
                "dataset_path": "problems.json",
                "strategies": [
                    {
                        "name": "vanilla",
                        "max_iterations": 1,
                        "temperature": 0.7,
                        "max_tokens": 2000,
                        "system_prompt": None,
                        "custom_params": {},
                    }
                ],
                "output_dir": "./results",
                "max_workers": 5,
                "log_level": "INFO",
                "problem_filters": None,
                "difficulty_strategy": None,
                "budget_cap_usd": None,
                "budget_action": None,
                "budget_allocation": None,
                "cost_alerts": None,
                "enable_incremental": False,
                "enable_quality_analysis": False,
                "quality_analysis_config": None,
                "enable_evolution_analysis": True,
            },
            "credentials_removed": True,
        },
    ),
    "templates": (
        "列出可用的服务器配置模板名称和类型。",
        [{"name": "vanilla", "type": "harness"}, {"name": "experiment", "type": "experiment"}],
    ),
    "get_template": (
        "按名称返回可下载使用的配置模板内容；名称可从 configs/templates 获取。",
        {
            "type": "harness",
            "config": {
                "llm_config": {
                    "provider": "openai",
                    "api_key": "[REDACTED]",
                    "model": "gpt-4o-mini",
                    "base_url": None,
                    "temperature": 0.7,
                    "max_tokens": 2000,
                    "timeout": 30,
                    "enable_thinking": None,
                    "retry_max_attempts": 3,
                    "retry_backoff_seconds": 0.5,
                    "retry_max_elapsed_seconds": 60.0,
                    "cache": {
                        "enabled": True,
                        "backend": "disk",
                        "ttl_days": 30,
                        "max_size_mb": 1000,
                    },
                },
                "sandbox_config": {
                    "backend": "docker",
                    "docker_image": "python:3.11-slim",
                    "timeout_seconds": 5,
                    "memory_limit_mb": 256,
                    "max_output_bytes": 1000000,
                    "max_processes": 16,
                    "allowed_imports": [
                        "math",
                        "itertools",
                        "collections",
                        "heapq",
                        "bisect",
                        "functools",
                        "sys",
                        "json",
                    ],
                },
                "dataset_path": "problems.json",
                "strategies": [
                    {
                        "name": "vanilla",
                        "max_iterations": 1,
                        "temperature": 0.7,
                        "max_tokens": 2000,
                        "system_prompt": None,
                        "custom_params": {},
                    }
                ],
                "output_dir": "./results",
                "max_workers": 5,
                "log_level": "INFO",
                "problem_filters": None,
                "difficulty_strategy": None,
                "budget_cap_usd": None,
                "budget_action": None,
                "budget_allocation": None,
                "cost_alerts": None,
                "enable_incremental": False,
                "enable_quality_analysis": False,
                "quality_analysis_config": None,
                "enable_evolution_analysis": True,
            },
        },
    ),
    "file_metadata": ("查询自己的未过期文件元数据；不存在、过期或不属于自己时不可访问。", FILE),
    "download_file": ("下载自己的原始上传文件；Content-Type 根据已保存文件后缀决定。", None),
    "delete_file": ("删除自己的已上传文件及原始内容。", None),
    "export_problems": ("把自己的题库导出为 json 或 csv 附件。", None),
    "download_results": (
        "导出自己的运行结果；download 与 export 是同一接口的别名，支持 json/csv/md/markdown/html/png/zip。",
        None,
    ),
    "download_chart": ("下载自己的运行结果通过率 PNG；chart_name 仅支持 success-rate。", None),
    "detailed_health": (
        "查询配置基础设施的综合健康信息；可选执行沙箱检查；未知状态不会伪装成健康。",
        {
            "status": "partial",
            "scope": "configured_api_foundation",
            "checks": {},
            "pending_issues": [157],
        },
    ),
    "database_health": (
        "只读探测认证、文件、监控及业务数据库状态。",
        {"status": "ok", "business_database": {"status": "ok", "read_only": True}},
    ),
    "redis_health": (
        "查询配置的 Redis broker；默认关闭，设置 MONITOR_QUEUE_PROBES_ENABLED=true 后执行有超时和缓存的 PING，并只读采集配置业务队列的等待数量。",
        {
            "status": "not_checked",
            "reason": "disabled",
            "scope": "configured_celery_broker",
            "infrastructure_available": True,
            "timeout_seconds": 3.0,
            "backend": "redis",
            "queue_scope": "configured_business_queues",
            "queue_excludes": ["worker_reserved", "active", "unacked", "worker_scheduled"],
            "broker_queue": {
                "status": "not_checked",
                "reason": "disabled",
                "waiting": None,
                "queues": None,
            },
            "latency_ms": None,
            "cached": False,
            "age_seconds": None,
        },
    ),
    "worker_health": (
        "设置 MONITOR_QUEUE_PROBES_ENABLED=true 并重启升级后的 worker，可读取回复节点的安全数值负载；默认关闭，回复不代表完整集群或执行就绪。",
        {
            "status": "not_checked",
            "reason": "disabled",
            "scope": "responding_celery_workers",
            "infrastructure_available": True,
            "timeout_seconds": 3.0,
            "cluster_complete": False,
            "reserved_scope": "received_by_responding_workers_not_broker_queue_length",
            "evaluation_worker_implementation": "algorithm_harness",
            "real_evaluation_available": None,
            "execution_readiness": "not_checked",
            "worker_count": None,
            "workers": None,
            "active": None,
            "reserved": None,
            "concurrency": None,
            "cached": False,
            "age_seconds": None,
        },
    ),
    "sandbox_health": ("执行当前配置沙箱的可用性检查，返回检查结果。", {"status": "unavailable"}),
    "resources": (
        "读取 API 主机的 CPU、内存、上传磁盘和注册文件存储信息。",
        {
            "scope": "api_host",
            "cpu": {"status": "ok", "percent": 10.0, "sample_seconds": 0.1},
            "memory": {
                "status": "ok",
                "total_bytes": 10000,
                "available_bytes": 8000,
                "used_bytes": 2000,
                "percent": 20.0,
            },
            "disk": {
                "status": "ok",
                "scope": "upload_filesystem",
                "total_bytes": 10000,
                "used_bytes": 2000,
                "free_bytes": 8000,
                "percent": 20.0,
            },
            "file_storage": {
                "status": "ok",
                "active_files": 0,
                "active_bytes": 0,
                "scope": "registered_artifacts",
                "includes_unregistered_or_temporary_files": False,
            },
            "status": "ok",
        },
    ),
    "system_status": (
        "聚合当前 API 进程运行时间、任务计数、资源与依赖状态；MONITOR_CONTAINER_PROBES_ENABLED 可显式启用有标签沙箱资源采样，不是集群全局统计。",
        {
            "scope": "current_api_process",
            "uptime_seconds": 1.0,
            "task_counts": {},
            "async_task_counts": {},
            "containers": {
                "scope": "api_process_docker_context_labeled_running_sandboxes",
                "selector": "io.llm-algorithm-harness.sandbox=v1",
                "cluster_complete": False,
                "snapshot_atomic": False,
                "metrics_source": "docker_cli_rounded_stats",
                "timeout_seconds": 3.0,
                "sample_limit": 32,
                "cached": False,
                "age_seconds": None,
                "status": "not_configured",
                "reason": "disabled",
                "listed_count": None,
                "sampled_count": None,
                "truncated": None,
                "containers": None,
            },
        },
    ),
    "running_tasks": (
        "分页查询选定来源的运行中任务快照。",
        {"status": "ok", "items": [], "total": 0, "limit": 100, "offset": 0},
    ),
    "queued_tasks": (
        "分页查询选定来源的待运行任务快照。",
        {"status": "ok", "items": [], "total": 0, "limit": 100, "offset": 0},
    ),
    "api_stats": (
        "查询保留窗口内 API 请求、错误率及延迟统计。",
        {"window_seconds": 60, "total_requests": 0},
    ),
    "performance": (
        "汇总 API、评估、数据库和 LLM 性能指标；未接入的指标保留未知状态。",
        {"api": {}, "evaluations": {}, "database_queries": {}, "llm": {}},
    ),
    "llm_stats": (
        "查询共享认证数据库中真实生成请求的次数、成功率和平均耗时；可选 window_seconds（1–86400）按完成时间聚合，省略时累计。窗口不完整时主指标为 null，retained_sample 提供已保留样本；重试分别计数，采集为 best-effort。",
        {
            "status": "ok",
            "source": "persisted_llm_attempts",
            "scope": "recorded_completed_attempts_shared_auth_database",
            "collection_mode": "best_effort",
            "started_at": None,
            "total_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0,
            "success_rate": None,
            "avg_latency_ms": None,
            "recorded_usage_hooks": 0,
            "key_verification_count": 0,
        },
    ),
    "cache_stats": (
        "读取当前进程缓存后端统计；未配置后端时返回 not_configured。",
        {"status": "not_configured", "scope": "bound_cache_instance"},
    ),
    "strategies": (
        "列出服务器注册策略及其说明，用于配置评估策略。",
        {
            "strategies": [
                {
                    "name": "vanilla",
                    "defaults": {
                        "name": "vanilla",
                        "max_iterations": 1,
                        "temperature": 0.7,
                        "max_tokens": 2000,
                    },
                }
            ]
        },
    ),
    "providers": (
        "查询模型目录。省略 api_key_id 时返回固定公开配置中的静态支持示例，"
        "source=static_examples、scope=offline_example_catalog；示例并非完整模型支持清单。"
        "传入本人非空 api_key_id 时，按密钥查询供应商模型，source=provider_api、"
        "scope=user_api_key，providers 中返回 provider/models/complete，与评测模型查询复用同一逻辑。"
        "complete=false 表示截断或无法确认分页完整性。枚举成功不保证推理可调用。"
        "仍限管理员，不能使用他人密钥；失败返回脱敏错误，不回退静态目录。响应 no-store。",
        {
            "status": "ok",
            "scope": "offline_example_catalog",
            "source": "static_examples",
            "live_provider_availability_checked": False,
            "providers": [],
        },
    ),
    "system_config": (
        "返回当前 API 进程已加载的配置：api/auth/files/monitoring 四组显式字段白名单。"
        "仅输出数值、布尔或可空限额；凭据、连接串、主机地址、CORS 来源、管理员 ID、"
        "敏感路径及未知字段完全省略。不会重新读取环境变量或配置文件，也不执行外部探测。"
        "字段名保留原配置名，时间和容量单位见字段后缀。响应 Cache-Control: no-store。",
        {
            "scope": "api_process",
            "api": {
                "MAX_CONCURRENT_TASKS": 5,
                "MAX_CONCURRENT_EVALUATIONS_PER_USER": 5,
                "TASK_TIMEOUT_SECONDS": 3600,
            },
            "auth": {
                "ACCESS_TOKEN_EXPIRE_MINUTES": 30,
                "REFRESH_TOKEN_EXPIRE_DAYS": 7,
                "AUTH_RATE_LIMIT": 10,
                "AUTH_RATE_WINDOW_SECONDS": 60,
                "AUTH_PROTECTED_RATE_LIMIT": 120,
                "USER_DAILY_API_CALL_LIMIT": None,
                "USER_MONTHLY_API_CALL_LIMIT": None,
            },
            "files": {
                "FILE_UPLOAD_MAX_BYTES": 104857600,
                "FILE_CONFIG_MAX_BYTES": 1048576,
                "FILE_MAX_USER_BYTES": 536870912,
                "FILE_TTL_SECONDS": 86400,
                "FILE_CLEANUP_INTERVAL_SECONDS": 300,
                "FILE_UPLOAD_RATE_LIMIT": 10,
                "FILE_MAX_CONCURRENT_TRANSFERS": 2,
                "FILE_UPLOAD_TIMEOUT_SECONDS": 120,
                "FILE_UPLOAD_IDLE_SECONDS": 15,
                "FILE_MAX_CONCURRENT_IMPORTS": 2,
                "FILE_MAX_ACTIVE_IMPORTS": 8,
                "FILE_IMPORT_MAX_ITEMS": 10000,
                "FILE_IMPORT_TIMEOUT_SECONDS": 3600,
            },
            "monitoring": {
                "MONITOR_RETENTION_SECONDS": 604800,
                "MONITOR_MAX_ROWS": 10000,
                "MONITOR_API_WINDOW_SECONDS": 60,
                "MONITOR_PROBE_CACHE_SECONDS": 5,
                "MONITOR_QUEUE_PROBES_ENABLED": False,
                "MONITOR_QUEUE_TIMEOUT_SECONDS": 3.0,
                "MONITOR_QUEUE_CACHE_SECONDS": 5.0,
                "MONITOR_CONTAINER_PROBES_ENABLED": False,
                "MONITOR_CONTAINER_TIMEOUT_SECONDS": 3.0,
                "MONITOR_CONTAINER_CACHE_SECONDS": 5.0,
                "MONITOR_CONTAINER_MAX_ITEMS": 32,
                "MONITOR_SANDBOX_TIMEOUT_SECONDS": 5,
            },
        },
    ),
    "sandbox_config": (
        "返回当前沙箱配置的公开设置。",
        {
            "backend": "docker",
            "docker_image": "python:3.11-slim",
            "timeout_seconds": 5,
            "memory_limit_mb": 256,
            "max_output_bytes": 1000000,
            "max_processes": 16,
            "allowed_imports": [
                "math",
                "itertools",
                "collections",
                "heapq",
                "bisect",
                "functools",
                "sys",
                "json",
            ],
        },
    ),
    "quotas": (
        "查询自己的已执行存储、请求、导入及传输限额，以及评估并发上限、已用和剩余名额；评估仅计 pending/running 任务，日/月 API 配额未配置时为 null。",
        {
            "scope": "current_user_enforced_limits",
            "evaluation_concurrency": {"limit": 5, "used": 0, "remaining": 5},
            "storage": {
                "used_bytes": 0,
                "file_count": 0,
                "limit_bytes": 536870912,
                "includes_pending_cleanup": True,
            },
            "dataset": {
                "used_bytes": 0,
                "used_items": 0,
                "limit_bytes": 104857600,
                "limit_items": 10000,
                "separate_from_file_storage": True,
            },
            "protected_requests": {
                "used": 1,
                "limit": 120,
                "window_seconds": 60,
                "resets_at": 1792368060,
            },
            "imports": {
                "active_for_user": 0,
                "global_active_limit": 8,
                "per_process_concurrency": 2,
            },
            "transfers": {"per_process_concurrency": 2},
            "daily_api_calls": {
                "status": "metered",
                "limit": None,
                "remaining": None,
                "used": 0,
                "timezone": "UTC",
                "period_start": "2026-10-24T00:00:00+00:00",
                "resets_at": "2026-10-25T00:00:00+00:00",
                "scope": "owned_generation_sdk_attempts",
                "collection_mode": "best_effort_since_instrumentation",
            },
            "monthly_api_calls": {
                "status": "metered",
                "limit": None,
                "remaining": None,
                "used": 0,
                "timezone": "UTC",
                "period_start": "2026-10-01T00:00:00+00:00",
                "resets_at": "2026-11-01T00:00:00+00:00",
                "scope": "owned_generation_sdk_attempts",
                "collection_mode": "best_effort_since_instrumentation",
            },
        },
    ),
    "global_logs": (
        "分页查询保留的全局 API/任务生命周期日志，支持级别、时间和文本过滤。",
        {"items": [], "total": 0, "limit": 100, "offset": 0},
    ),
    "task_logs": (
        "查询自己的异步任务或评估运行日志；包含保留的生命周期、数值进度及逐单元执行事件。",
        {
            "task_id": "eval-demo",
            "items": [],
            "total": 0,
            "limit": 100,
            "offset": 0,
            "source": "retained_api_lifecycle_and_trusted_task_events",
        },
    ),
    "download_logs": (
        "下载自己任务的保留日志 JSONL 文本；导出忽略分页参数，受服务器导出行数上限控制。",
        None,
    ),
    "create_experiment": ("保存固定预算实验配置，引用数据集及提供商密钥；调用 run 启动。", JOB),
    "list_experiments": ("分页查询自己的实验，可按状态过滤。", page([JOB])),
    "get_experiment": ("查询自己的实验配置、状态和错误信息。", JOB),
    "delete_experiment": ("删除自己的已停止实验；运行中的实验不可删除。", None),
    "run_experiment": ("把自己的实验提交到后台；202 为受理状态，轮询实验详情。", JOB),
    "experiment_results": (
        "读取自己已完成实验的模型、策略和组合结果；未完成时返回 400。",
        {
            "experiment_id": "experiment-demo",
            "name": "Demo",
            "status": "completed",
            "created_at": "2026-10-19T00:00:00Z",
            "finished_at": "2026-10-19T00:00:00Z",
            "models": ["gpt-4o-mini"],
            "strategies": [],
            "combinations": [],
        },
    ),
    "experiment_comparison": (
        "读取已完成实验生成的比较报告；结果尚不可用时返回 400。",
        {"experiment": {"experiment_id": "experiment-demo"}, "combinations": []},
    ),
    "experiment_panel": (
        "把已完成实验的比较报告转换成前端面板数据。",
        {
            "experiment_id": "experiment-demo",
            "name": None,
            "radar": {"labels": ["隐藏通过率", "样例验证率", "修复率", "成本效益"], "datasets": []},
            "algorithm_radar": {"labels": [], "datasets": [], "dimension_counts": {}},
            "scatter": [],
            "bar": {"labels": [], "calls": [], "elapsed": [], "tokens": []},
            "matrix_tables": [],
            "cost_unknown_models": [],
            "error_categories": [],
            "failure_mode_categories": [],
            "capability": {
                "dimension_labels": [
                    "algorithm_design",
                    "code_implementation",
                    "debugging",
                    "optimization",
                    "boundary_handling",
                ],
                "dimension_descriptions": {
                    "algorithm_design": "正式/隐藏评测正确率",
                    "code_implementation": "公开样例通过率",
                    "debugging": "失败后修复率",
                    "optimization": "正式通过率与 Token 消耗的效率分数",
                    "boundary_handling": "独立隐藏测试通过率",
                },
                "models": {},
                "heatmap": [],
                "heuristic_note": "能力维度基于评测结果启发式估计，不代表对模型内部能力的因果测量。",
            },
            "generated_at": "2026-10-19T00:00:00Z",
        },
    ),
    "list_suites": (
        "列出自己的全部基准套件；响应使用分页结构但不截断列表。",
        {"items": [SUITE], "total": 1, "limit": 1, "offset": 0, "has_more": False},
    ),
    "create_suite": ("创建包含题目 ID 列表的基准套件，可在创建时冻结。", SUITE),
    "get_suite": ("读取自己基准套件的题目、版本和冻结状态。", SUITE),
    "update_suite": ("更新自己的未冻结套件；冻结套件拒绝修改。", SUITE),
    "run_suite": (
        "使用数据集、模型及密钥提交一次基准运行；202 表示受理。",
        {
            "id": "run-demo",
            "suite_id": "suite-demo",
            "status": "pending",
            "model": "gpt-4o-mini",
            "accuracy": None,
            "cost_usd": None,
            "error_message": None,
            "created_at": STAMP,
            "updated_at": STAMP,
        },
    ),
    "get_run": (
        "查询自己的基准运行状态及结果。",
        {
            "id": "run-demo",
            "suite_id": "suite-demo",
            "status": "pending",
            "model": "gpt-4o-mini",
            "accuracy": None,
            "cost_usd": None,
            "results": {},
            "error_message": None,
            "created_at": STAMP,
            "updated_at": STAMP,
        },
    ),
    "learning_curve": (
        "查询自己套件已完成运行的准确率/成本变化和趋势摘要。",
        {
            "suite_id": "suite-demo",
            "suite_name": "Demo suite",
            "data": [],
            "trends": {"accuracy_growth_rate": None, "cost_growth_rate": None},
        },
    ),
    "create_ab_test": (
        "保存具有两个唯一提示变体的 A/B 测试配置；调用 run 启动。",
        {**JOB, "id": "test-demo"},
    ),
    "list_ab_tests": (
        "分页查询自己的 A/B 测试，可按状态过滤。",
        page([{**JOB, "id": "test-demo"}]),
    ),
    "get_ab_test": ("查询自己的 A/B 测试配置、状态及错误。", {**JOB, "id": "test-demo"}),
    "delete_ab_test": ("删除自己的已停止 A/B 测试；运行中的测试不可删除。", None),
    "run_ab_test": (
        "启动自己的 A/B 测试；202 为已受理，轮询测试详情。",
        {**JOB, "id": "test-demo", "status": "running"},
    ),
    "ab_test_results": (
        "读取自己的 A/B 测试统计；未完成时返回测试 ID 和当前状态。",
        {"test_id": "test-demo", "status": "pending"},
    ),
    "pareto_analyze": (
        "对请求中的比较报告执行无状态 Pareto 分析；不创建评估或调用 LLM。",
        {
            "schema_version": "1.0",
            "accuracy_metric": "overall",
            "cost_basis": "mean_total_cost_usd_per_dataset_run",
            "sources": ["experiment-demo"],
            "points": [],
            "excluded": [],
            "frontier_ids": [],
            "best_value": {
                "feasible": False,
                "point_id": None,
                "basis": "expected_solved_per_usd; known zero-cost successes preferred",
            },
            "budget_recommendations": [{"budget_usd": 1.0, "feasible": False, "point_id": None}],
            "note": "Historical means and ranges are descriptive, not guaranteed future accuracy or billing.",
        },
    ),
    "optimize": (
        "对请求中的比较报告生成成本优化建议；不启动执行任务。",
        {
            "budget_plan": {
                "budget": 1.0,
                "coverage": 0,
                "estimated_accuracy": None,
                "estimated_cost": 0.0,
                "layers": {
                    "easy": {"feasible": False, "note": "无历史数据或无满足约束的组合"},
                    "hard": {"feasible": False, "note": "无历史数据或无满足约束的组合"},
                    "medium": {"feasible": False, "note": "无历史数据或无满足约束的组合"},
                },
                "min_accuracy": 0.0,
            },
            "experiment_id": "",
            "generated_at": "2026-10-19T00:00:00Z",
            "ranking": {"excluded": [], "ranking": []},
            "recommendations": {
                "best_value": {
                    "feasible": False,
                    "note": "无可用的成本已知组合",
                    "objective": "best_value",
                },
                "highest_accuracy": {
                    "feasible": False,
                    "note": "无可用的成本已知组合",
                    "objective": "highest_accuracy",
                },
                "lowest_cost": {
                    "feasible": False,
                    "note": "无满足约束的方案",
                    "objective": "lowest_cost",
                },
            },
            "selected_objective": "best_value",
        },
    ),
    "task_cost": (
        "读取自己的评估、实验、基准或 A/B 任务成本；不存在时返回 404。",
        {
            "task_id": "eval-demo",
            "source": "evaluations",
            "status": "pending",
            "total_cost_usd": 0.0,
            "budget_cap_usd": 1.0,
            "problem_count": 1,
        },
    ),
    "cost_summary": (
        "汇总自己时间区间内各来源任务成本（USD）。",
        {"since": None, "until": None, "total_cost_usd": 0.0, "task_count": 0, "by_source": {}},
    ),
    "cost_trends": ("按日期聚合自己的任务成本趋势。", {"since": None, "until": None, "data": []}),
    "cost_breakdown": (
        "按来源、模型和策略拆分自己的成本。",
        {"since": None, "until": None, "by_source": {}, "by_model": {}, "by_strategy": {}},
    ),
    "get_budget": ("读取自己唯一的预算配置；尚未配置时数据为空对象。", BUDGET),
    "upsert_budget": (
        "创建或替换自己的预算配置；cap 必须为正数，action 为 pause/downgrade。",
        BUDGET,
    ),
    "update_budget": ("局部更新自己的预算配置，未提供的字段保持不变。", BUDGET),
    "budget_usage": (
        "查询自己的全局及分难度预算用量、剩余额度和统计依据。",
        {
            "global_budget": {
                "cap_usd": 10.0,
                "used_usd": 0.0,
                "remaining_usd": 10.0,
                "percentage_used": 0.0,
            },
            "by_difficulty": {},
            "basis": "",
        },
    ),
    "list_alert_rules": ("列出自己的成本预警规则；目标地址遮罩展示。", [RULE]),
    "create_alert_rule": (
        "创建成本预警规则，阈值为预算百分比，支持 log/slack/webhook/smtp。",
        RULE,
    ),
    "update_alert_rule": ("局部更新自己的成本预警规则。", RULE),
    "delete_alert_rule": ("删除自己的成本预警规则。", None),
    "alert_history": ("读取自己的最近预警历史，最多返回 200 条。", []),
    "pricing_catalog": (
        "查询内置价格及自定义覆盖目录；金额为每千 token 的 USD 单价。",
        {
            "models": {
                "example-model": {
                    "prompt_per_1k": 0.001,
                    "completion_per_1k": 0.002,
                    "source": "override",
                }
            }
        },
    ),
    "pricing_history": (
        "查询一个模型的自定义价格历史。",
        [
            {
                "prompt_per_1k": 0.001,
                "completion_per_1k": 0.002,
                "created_by": "user-demo",
                "created_at": "2026-10-19T00:00:00Z",
            }
        ],
    ),
    "set_pricing_override": (
        "追加模型价格覆盖版本；两项 USD/千 token 单价均须为正。",
        {
            "model": "gpt-4o-mini",
            "prompt_per_1k": 0.001,
            "completion_per_1k": 0.002,
            "created_at": STAMP,
        },
    ),
    "task_cost_report": (
        "生成自己指定任务的成本报告，含报告来源信息。",
        {
            "task_id": "eval-demo",
            "source": "evaluations",
            "status": "pending",
            "total_cost_usd": 0.0,
            "budget_cap_usd": 1.0,
            "problem_count": 1,
            "percentage_used": 0.0,
            "pricing_metadata": {"source": "business_db", "data_root": "data"},
        },
    ),
    "cost_optimization_report": (
        "根据自己已存储实验组合生成成本优化建议。",
        {
            "generated_at": "2026-10-19T00:00:00Z",
            "experiment_id": "",
            "ranking": {"ranking": [], "excluded": []},
            "recommendations": {
                "highest_accuracy": {
                    "objective": "highest_accuracy",
                    "feasible": False,
                    "note": "无可用的成本已知组合",
                },
                "best_value": {
                    "objective": "best_value",
                    "feasible": False,
                    "note": "无可用的成本已知组合",
                },
                "lowest_cost": {
                    "objective": "lowest_cost",
                    "feasible": False,
                    "note": "无满足约束的方案",
                },
            },
            "selected_objective": "best_value",
        },
    ),
}

ADMIN_OPERATIONS = {
    "detailed_health",
    "database_health",
    "redis_health",
    "worker_health",
    "sandbox_health",
    "resources",
    "system_status",
    "running_tasks",
    "queued_tasks",
    "api_stats",
    "performance",
    "llm_stats",
    "cache_stats",
    "strategies",
    "providers",
    "sandbox_config",
    "system_config",
    "global_logs",
}
AUTH_OPERATIONS = {"register", "login", "refresh"}
UPLOAD_OPERATIONS = {"upload_file", "upload_problems", "upload_config"}
DOWNLOADS = {
    "report_markdown": {"text/markdown": "# Evaluation report\n"},
    "report_html": {"text/html": "<!doctype html><html><body>Evaluation report</body></html>"},
    "report_csv": {"text/csv": "\ufeffproblem_id,strategy,status\ntwo-sum,vanilla,success\n"},
    "download_logs": {"text/plain": '{"level":"INFO","message":"Task started"}\n'},
    "download_chart": {"image/png": "PNG binary file"},
    "export_problems": {"application/json": [], "text/csv": "problem_id,title\n"},
    "download_results": {
        "application/json": {},
        "text/csv": "problem_id,status\n",
        "text/markdown": "# Evaluation results\n",
        "text/html": "<!doctype html><html><body>Evaluation results</body></html>",
        "image/png": "PNG binary file",
        "application/zip": "ZIP binary file",
    },
    "download_file": {
        "application/json": [],
        "application/yaml": "problems: []\n",
        "text/csv": "problem_id,title\n",
        "image/png": "PNG binary file",
        "application/zip": "ZIP binary file",
        "application/octet-stream": "Binary file",
    },
}

REQUEST_EXAMPLES: dict[str, Any] = {
    "RegisterInput": {
        "username": "demo",
        "email": "demo@example.com",
        "password": "Example-password-123!",
    },
    "LoginInput": {"username": "demo", "password": "Example-password-123!"},
    "RefreshInput": {"refresh_token": "REFRESH_TOKEN"},
    "PasswordChange": {
        "current_password": "Example-password-123!",
        "new_password": "New-example-password-456!",
    },
    "ProfileUpdate": {"email": "updated@example.com"},
    "KeyCreate": {
        "provider": "openai",
        "key_name": "Demo key",
        "api_key": "REPLACE_WITH_PROVIDER_KEY",
    },
    "KeyUpdate": {"key_name": "Renamed demo key"},
    "EvaluationCreateRequest": {
        "api_key_id": "key-demo",
        "model": "gpt-4o-mini",
        "problem_ids": ["two-sum"],
        "strategy_names": ["vanilla"],
        "budget_cap_usd": 1.0,
    },
    "EvaluationUpdateRequest": {"budget_cap_usd": 2.0, "timeout_seconds": 120},
    "AsyncTaskCreateRequest": {
        "task_type": "evaluation",
        "entity_id": "eval-demo",
        "celery_task_name": "src.tasks.evaluation.run_evaluation_task",
        "celery_task_args": ["eval-demo"],
    },
    "ImportRequest": {"file_id": "file-demo", "mode": "append"},
    "ExperimentCreateRequest": {
        "name": "Demo",
        "dataset_path": "problems.json",
        "models": [{"model": "gpt-4o-mini"}],
        "strategies": [{"name": "vanilla"}],
        "api_key_id": "key-demo",
    },
    "BenchmarkSuiteCreateRequest": {"name": "Demo suite", "problems": ["two-sum"]},
    "BenchmarkSuiteUpdateRequest": {"description": "Updated description", "frozen": True},
    "BenchmarkRunRequest": {
        "api_key_id": "key-demo",
        "dataset_path": "problems.json",
        "model": "gpt-4o-mini",
        "strategies": [{"name": "vanilla"}],
    },
    "ABTestCreateRequest": {
        "name": "Prompt comparison",
        "dataset_path": "problems.json",
        "model": {"model": "gpt-4o-mini"},
        "strategy": {"name": "vanilla"},
        "prompt_variants": [{"id": "baseline"}, {"id": "treatment", "prefix": "Think carefully. "}],
        "api_key_id": "key-demo",
    },
    "ParetoAnalyzeRequest": {
        "comparisons": [{"experiment": {"experiment_id": "experiment-demo"}, "combinations": []}],
        "budgets": [1.0],
        "accuracy_metric": "overall",
    },
    "OptimizeRequest": {
        "comparison": {"combinations": []},
        "budget": 1.0,
        "objective": "best_value",
    },
    "BudgetUpsertRequest": {
        "global_cap_usd": 10.0,
        "difficulty_caps": {"easy": 2.0},
        "action": "pause",
    },
    "AlertRuleCreateRequest": {"name": "Budget alert", "threshold_pct": 80, "channel": "log"},
    "AlertRuleUpdateRequest": {"threshold_pct": 90, "enabled": True},
    "PricingOverrideRequest": {"prompt_per_1k": 0.001, "completion_per_1k": 0.002},
}

# Parameter explanations include coercion behavior only where handlers implement it.
PARAMETERS: dict[str, tuple[str, Any]] = {
    "evaluation_id": ("自己的评估 ID，由创建评估接口返回。", "eval-demo"),
    "task_id": ("自己的任务 ID；日志/成本接口按各自关联的运行记录解析。", "task-demo"),
    "run_id": (
        "自己的运行 ID；结果查询还接受 evaluation ID。分析接口省略时统计自己的已完成评估；compare/strategies 和 compare/history 必填。",
        "run-demo",
    ),
    "problem_id": ("题目唯一 ID，来自已导入题库。", "two-sum"),
    "experiment_id": ("自己的实验 ID，由创建实验返回。", "experiment-demo"),
    "suite_id": ("自己的基准套件 ID。", "suite-demo"),
    "test_id": ("自己的 A/B 测试 ID。", "test-demo"),
    "file_id": ("自己的已上传且未过期文件 ID。", "file-demo"),
    "key_id": ("自己保存的 LLM 提供商密钥 ID。", "key-demo"),
    "api_key_id": ("自己保存的提供商密钥 ID，用于查询可用模型。", "key-demo"),
    "source": ("有效题目来源：all 为全部，shared 为共享题库，personal 为本人导入。", "all"),
    "job_id": ("自己的题目导入任务 ID。", "job-demo"),
    "rule_id": ("自己的成本预警规则 ID。", "rule-demo"),
    "model_id": ("模型标识，用于价格查询或覆盖；作为单个 URL 路径段传入。", "gpt-4o-mini"),
    "chart_name": ("图表名称；目前仅支持 success-rate。", "success-rate"),
    "name": ("配置模板名称，从 GET /api/v1/configs/templates 获取。", "vanilla"),
    "status": (
        "按保存的状态精确匹配；任务常见 pending/running/paused/completed/failed/cancelled，题目历史使用执行单元状态，如 success。",
        "completed",
    ),
    "task_type": ("任务类型过滤，例如 evaluation、experiment、benchmark、import。", "evaluation"),
    "limit": ("每页条数；常规列表 1–100，越界回退 20；日志/监控 Query 约束以 schema 为准。", 20),
    "offset": ("从零开始的记录偏移；常规列表负值归零，日志/监控受 schema 边界约束。", 0),
    "strategy": ("策略名称精确过滤，例如 vanilla。", "vanilla"),
    "difficulty": ("难度精确过滤，如 easy、medium、hard。", "easy"),
    "tag": ("题目标签精确匹配，区分大小写。", "array"),
    "sort": ("排序字段：completed_at 或 created_at；其他值回退 completed_at。", "completed_at"),
    "order": ("排序方向；asc（不区分大小写）升序，其余值降序。", "desc"),
    "since": ("起始时间，ISO 8601，支持带时区值并转换为 UTC。", "2026-10-01T00:00:00Z"),
    "until": ("结束时间，ISO 8601；必须不早于 since。", "2026-10-19T00:00:00Z"),
    "format": (
        "导出格式；题库支持 json/csv，运行结果支持 json/csv/md/markdown/html/png/zip。",
        "json",
    ),
    "include_sandbox": ("是否执行额外的沙箱检查；默认 false。", False),
    "task_source": ("监控快照来源：legacy_evaluation 或 async_task。", "async_task"),
    "window_seconds": ("聚合最近多少秒的指标，范围 1–86400；LLM 查询省略时返回累计统计。", 60),
    "level": ("日志级别，不区分大小写：DEBUG/INFO/WARNING/ERROR/CRITICAL。", "INFO"),
    "start": ("日志起始时间，ISO 8601，必须带时区且不早于 Unix epoch。", "2026-10-01T00:00:00Z"),
    "end": ("日志结束时间，必须带时区且不早于 start。", "2026-10-19T00:00:00Z"),
    "search": ("在保留的日志中搜索文本，最多 200 个字符。", "evaluation"),
}

FIELD_DESCRIPTIONS = {
    "username": "用户名；登录接口也接受邮箱。长度及格式见 schema 约束。",
    "email": "电子邮箱地址；必须具有非空域名和后缀。",
    "password": "用户密码。注册至少 12 个字符；仅用于请求，不会出现在响应。",
    "refresh_token": "登录或上一次刷新取得的刷新令牌；轮换后旧令牌失效。",
    "current_password": "修改密码前校验的当前密码。",
    "new_password": "新密码，至少 12 个字符；修改后所有会话撤销。",
    "provider": "LLM 提供商：openai、anthropic 或 siliconflow。",
    "key_name": "用户自定义密钥名称，不是提供商密钥本身。",
    "api_key": "提供商明文密钥；仅本次请求提交，服务器加密存储。",
    "api_key_id": "自己已保存的提供商密钥 ID；不会接受其他用户密钥。",
    "model": "提供商支持的模型名称；实验中的对象可指定独立密钥。",
    "problem_ids": "待评估题目 ID 列表，不允许重复，题目需预先存在。",
    "strategy_names": "待运行策略名称列表，不允许重复。",
    "budget_cap_usd": "此运行的预算上限，单位 USD；为空时不指定上限。",
    "timeout_seconds": "每道题目的超时时间，单位秒。",
    "max_concurrency": "评估最大并发题目数。",
    "task_type": "异步任务类型，例如 evaluation、experiment、benchmark、import。",
    "entity_id": "该异步任务关联的业务实体 ID。",
    "celery_task_name": "服务器已注册且与任务类型匹配的 Celery 处理器全名。",
    "celery_task_args": "处理器位置参数数组，须与对应任务处理器签名一致。",
    "celery_task_kwargs": "处理器关键字参数；用户身份由服务器校验。",
    "file_id": "自己的已上传文件 ID。",
    "mode": "append 追加题目，overwrite 替换自己的题库。",
    "dataset_path": "服务器 DATA_ROOT 内的数据集相对路径；不是客户端文件路径。",
    "models": "实验模型列表，每个模型可覆盖 api_key_id、base_url 和 temperature。",
    "strategies": "策略配置列表，每项包含 name 和可选的 max_iterations、temperature、max_tokens、system_prompt、custom_params。",
    "strategy": "A/B 测试使用的单个策略配置。",
    "name": "资源或策略名称，具体长度限制见 schema。",
    "repeats": "每个模型/策略组合重复执行次数。",
    "budget": "实验预算配置或优化分析的 USD 上限，具体结构见 schema。",
    "execution": "实验执行模式：serial 或 parallel。",
    "max_workers": "并行工作线程上限，具体范围见 schema。",
    "problem_filters": "题目过滤配置，用于限制数据集中参与执行的题目。",
    "base_url": "可选提供商 API 基础 URL 覆盖。",
    "temperature": "可选采样温度，范围 0–2。",
    "problems": "基准套件包含的题目 ID 列表。",
    "version": "基准套件的版本标签。",
    "description": "用户填写的资源或提示变体说明。",
    "frozen": "是否冻结基准套件；冻结后不可修改。",
    "prompt_variants": "恰好两个具有唯一 id 的提示变体。",
    "baseline_id": "基线变体 ID，默认第一个变体。",
    "seed": "A/B 分层随机分组种子，便于复现。",
    "id": "资源或提示变体的唯一标识。",
    "system_prompt": "覆盖此变体的系统提示词；为空时使用默认值。",
    "prefix": "附加到题目提示之前的文本。",
    "suffix": "附加到题目提示之后的文本。",
    "comparisons": "已有实验比较报告列表，每项包括 experiment 和 combinations。",
    "comparison": "已有实验比较报告，包含 combinations 列表。",
    "budgets": "用于 Pareto 分析的预算阈值列表，单位 USD。",
    "accuracy_metric": "准确率口径：overall 或 formal。",
    "min_accuracy": "优化建议的最低准确率，范围 0–1。",
    "objective": "优化目标，例如 best_value；见优化算法支持的目标。",
    "global_cap_usd": "全局预算上限，单位 USD，必须为正。",
    "difficulty_caps": "easy/medium/hard 各难度的正数 USD 预算上限映射。",
    "action": "预算超限动作：pause 或 downgrade。",
    "threshold_pct": "预警阈值，预算百分比，范围 1–100。",
    "channel": "预警通道：slack、webhook、smtp 或 log。",
    "target": "通道目标地址；响应会遮罩敏感部分。",
    "enabled": "是否启用此策略或预警规则。",
    "config": "策略专用配置对象，内容依赖所选策略。",
    "prompt_per_1k": "每千个输入 token 的 USD 单价，必须为正。",
    "completion_per_1k": "每千个输出 token 的 USD 单价，必须为正。",
    "file": "恰好一个待上传的文件，multipart 文件字段。",
    "validate": "必须开启题目 schema 校验；仅接受 true 或 1。",
    "config_type": "配置类型：harness 或 experiment，默认 harness。",
}

ERROR_MESSAGES = {
    400: "Request validation failed",
    401: "Invalid or expired credentials",
    403: "Administrator permission required",
    404: "Resource not found",
    405: "Method Not Allowed",
    408: "Upload timed out",
    409: "Resource already exists",
    413: "Request body too large",
    415: "Multipart form data required",
    429: "Too many requests",
    500: "An unexpected error occurred",
    503: "Service is unavailable",
}

API_CONTRACT_VERSION = "1.1.0"

OVERVIEW = """LLM Algorithm Harness API，HTTP 契约版本 1.1.0（API v1）。

**版本策略**：URL 主版本 `/api/v1`；不使用 Header 版本协商。
兼容扩展沿用 v1；破坏性变更使用新的 URL 主版本，并提供迁移说明、并行支持与退役公告。
契约版本使用 MAJOR.MINOR.PATCH；健康检查的 `version` 是独立的应用发布版本。
完整策略与兼容性检查流程见仓库 `docs/api-versioning.md`。

自动生成的 OpenAPI 位于 `/openapi.json`，Swagger UI 位于 `/docs`，ReDoc 位于 `/redoc`。
每个操作均包含参数、请求/响应示例、认证、速率限制及 curl 命令。
JSON 成功响应使用 `{success, data, message}`；204 无响应体；下载返回附件而非 JSON 包装。
错误使用 `{success: false, error: {code, message, details, request_id}}`，并保留顶层兼容字段
`message/detail/details`。参数校验失败为 HTTP 400（不是 422）；错误头 `X-Request-ID`
与 `error.request_id` 相同。默认 HTTP 状态码映射与显式业务错误码有区别，业务码不会从文案推断。
401 使用 `WWW-Authenticate: Bearer`，429 使用 `Retry-After`（秒）。

**WebSocket**：`/api/v1/ws/progress?token=ACCESS_TOKEN`，使用访问令牌查询参数认证。
发送 `{"action":"subscribe","task_id":"eval-demo"}` 订阅自己的评估，
`{"action":"unsubscribe","task_id":"eval-demo"}` 取消订阅，`{"action":"ping"}` 心跳。
服务端发送 connected、task.snapshot、subscribed、unsubscribed、pong 和任务事件。
无效令牌关闭码 4401；任务不存在或不属于自己为 4403。此连接不经过 HTTP 请求限流，
不会列在 OpenAPI HTTP paths 中。完整示例见仓库 `API.md`。
"""


def _error_example(status: int, code: str) -> dict[str, Any]:
    message = ERROR_MESSAGES.get(status, "Request failed")
    return {
        "success": False,
        "error": {"code": code, "message": message, "details": {}, "request_id": "req_example"},
        "message": message,
        "detail": message,
        "details": {},
    }


def _describe_fields(node: Any) -> None:
    if isinstance(node, dict):
        for name, field in node.get("properties", {}).items():
            if name in FIELD_DESCRIPTIONS:
                field.setdefault("description", FIELD_DESCRIPTIONS[name])
        for value in node.values():
            _describe_fields(value)
    elif isinstance(node, list):
        for value in node:
            _describe_fields(value)


def _rate_limit(name: str, path: str) -> str:
    if name == "health_check":
        return "速率限制：此公开存活接口未配置应用级限流。"
    if name in AUTH_OPERATIONS:
        return "速率限制：同一客户端 IP 共享 AUTH_RATE_LIMIT（默认 10 次）/ AUTH_RATE_WINDOW_SECONDS（默认 60 秒）；429 后按 Retry-After 重试。"
    text = "速率限制：同一用户共享 AUTH_PROTECTED_RATE_LIMIT（默认 120 次）/ AUTH_RATE_WINDOW_SECONDS（默认 60 秒）；429 后按 Retry-After 重试。"
    if name in UPLOAD_OPERATIONS:
        text += " 上传额外按 IP 和用户分别限制 FILE_UPLOAD_RATE_LIMIT（默认 10 次/同一认证窗口）。"
    if (
        name in UPLOAD_OPERATIONS
        or path == "/api/v1/problems/export"
        or (path.startswith("/api/v1/files/") and path.endswith("/download"))
        or path.startswith("/api/v1/results/")
    ):
        text += " 此路径还受 FILE_MAX_CONCURRENT_TRANSFERS（每个 API 进程默认 2 个）并发容量限制。"
    if name == "models":
        text += " 模型查询还按用户使用独立限流桶：AUTH_RATE_LIMIT（默认 10 次）/ AUTH_RATE_WINDOW_SECONDS（默认 60 秒）。"
    if name == "alert_history":
        text += " limit 限制到 1–200，默认 50。"
    return text


def _curl(path: str, method: str, operation: dict[str, Any], name: str) -> str:
    url = "http://localhost:8000" + path
    for parameter in operation.get("parameters", []):
        if parameter["in"] == "path":
            url = url.replace("{" + parameter["name"] + "}", str(parameter["example"]))
    query = {
        p["name"]: str(p["example"]).lower() if isinstance(p["example"], bool) else p["example"]
        for p in operation.get("parameters", [])
        if p["in"] == "query"
    }
    if query:
        url += "?" + urlencode(query)
    args = ["curl", "-D -" if name in DOWNLOADS else "-i", "-X", method.upper(), shlex.quote(url)]
    if operation.get("security"):
        args.append('-H "Authorization: Bearer $ACCESS_TOKEN"')
    contents = operation.get("requestBody", {}).get("content", {})
    if "application/json" in contents:
        args += [
            "-H 'Content-Type: application/json'",
            "--data "
            + shlex.quote(json.dumps(contents["application/json"]["example"], ensure_ascii=False)),
        ]
    elif "multipart/form-data" in contents:
        filename = "config.yaml" if name == "upload_config" else "problems.json"
        args.append("-F " + shlex.quote("file=@" + filename))
        if name == "upload_problems":
            args += ["-F 'mode=append'", "-F 'validate=true'"]
        if name == "upload_config":
            args.append("-F 'config_type=harness'")
    if name in DOWNLOADS:
        args += ["--output", "download.bin"]
    return " \\\n  ".join(args)


def _document_operation(path: str, method: str, operation: dict[str, Any]) -> None:
    name = operation.get("operationId", "").partition("_api_v1_")[0]
    if name not in OPERATIONS:
        # Preserve FastAPI output for future routes; the coverage test flags them.
        return
    purpose, data = OPERATIONS[name]
    operation["summary"] = purpose.split("；")[0].split("。")[0]
    for parameter in operation.get("parameters", []):
        description, example = PARAMETERS[parameter["name"]]
        if name == "alert_history" and parameter["name"] == "limit":
            description, example = "最近预警条数；默认 50，服务端限制到 1–200。", 50
        if name in {"task_logs", "download_logs"} and parameter["name"] == "task_id":
            description, example = (
                "自己拥有的异步任务 ID 或有效关联评估 ID；兼容旧评估运行 ID。",
                "eval-demo",
            )
        parameter["description"] = description
        parameter["example"] = example
    for media_type, media in operation.get("requestBody", {}).get("content", {}).items():
        if media_type == "application/json":
            model_name = media["schema"]["$ref"].rsplit("/", 1)[-1]
            media["example"] = deepcopy(REQUEST_EXAMPLES[model_name])
        else:
            media["example"] = {
                "file": "(binary file)",
                **(
                    {"config_type": "harness"}
                    if name == "upload_config"
                    else {"mode": "append", "validate": True} if name == "upload_problems" else {}
                ),
            }
            properties = media["schema"]["properties"]
            allowed = (
                {"file", "config_type"}
                if name == "upload_config"
                else {"file", "mode", "validate"} if name == "upload_problems" else {"file"}
            )
            media["schema"]["properties"] = {k: v for k, v in properties.items() if k in allowed}
        operation["requestBody"][
            "description"
        ] = "请求体各字段的语义、必填项、类型及约束见 schema；示例中的 ID/令牌需要替换为自己的资源。"
    responses = operation["responses"]
    # The application's RequestValidationError handler returns 400, never 422.
    responses.pop("422", None)
    for status, response in responses.items():
        if status.startswith("2"):
            if status == "204":
                response["description"] = "操作成功；无响应体。"
                response.pop("content", None)
            elif name in DOWNLOADS:
                response["description"] = (
                    "文件附件；媒体类型取决于格式或文件后缀，Content-Disposition 提供文件名。"
                )
                response["content"] = {
                    mime: {
                        "schema": (
                            {"type": "string", "format": "binary"}
                            if mime in {"image/png", "application/zip", "application/octet-stream"}
                            else {}
                        ),
                        "example": example,
                    }
                    for mime, example in DOWNLOADS[name].items()
                }
                response["headers"] = {
                    "Content-Disposition": {
                        "description": "附件文件名（可能使用 filename*=UTF-8 编码）。",
                        "schema": {"type": "string"},
                    }
                }
                if name == "download_logs":
                    response["headers"].update(
                        {
                            header: {"description": description, "schema": {"type": kind}}
                            for header, description, kind in [
                                ("X-Retained-Log-Count", "匹配的保留日志总行数。", "integer"),
                                ("X-Exported-Log-Count", "实际导出的日志行数。", "integer"),
                                ("X-Log-Export-Truncated", "是否受导出上限截断。", "boolean"),
                            ]
                        }
                    )
            else:
                response["description"] = (
                    "异步任务已受理；轮询详情或进度获取最终结果。"
                    if status == "202"
                    else "操作成功。"
                ) + " JSON 的 success 表示成功，data 为下列业务数据，message 为提示信息。"
                response.setdefault("content", {}).setdefault("application/json", {})["example"] = {
                    "success": True,
                    "data": deepcopy(data),
                    "message": (
                        "Service is healthy" if name == "health_check" else "Operation successful"
                    ),
                }
        else:
            numeric_status = int(status) if status.isdecimal() else 500 if status == "5XX" else 400
            code = HTTP_CODES.get(numeric_status, ErrorCode.HTTP_ERROR).value
            response["description"] = (
                f"{code}：{ERROR_MESSAGES.get(numeric_status, 'Request failed')}。error.details 为结构化详情；request_id 可用于关联日志。通用错误契约，具体适用条件见本操作说明。"
            )
            examples = {code: {"value": _error_example(numeric_status, code)}}
            if status == "401":
                examples["INVALID_TOKEN"] = {"value": _error_example(401, "INVALID_TOKEN")}
            response["content"]["application/json"]["examples"] = examples
            response["headers"] = {
                "X-Request-ID": {
                    "description": "服务端生成，与 error.request_id 相同。",
                    "schema": {"type": "string"},
                },
                "Cache-Control": {"schema": {"type": "string"}, "example": "no-store"},
            }
            if status == "401":
                response["headers"]["WWW-Authenticate"] = {
                    "schema": {"type": "string"},
                    "example": "Bearer",
                }
            if status == "429":
                response["headers"]["Retry-After"] = {
                    "description": "重试前等待的秒数。",
                    "schema": {"type": "integer"},
                    "example": 60,
                }
    auth = (
        "认证：公开接口，无需 Bearer。"
        if not operation.get("security")
        else "认证：Authorization: Bearer <access_token>；仅可操作自己的资源。"
    )
    if name in ADMIN_OPERATIONS:
        auth += " 需要管理员权限，由 MONITOR_ADMIN_USER_IDS 配置；不足时 403。"
    errors = "错误：参数或业务状态无效 400；未认证/令牌无效 401；资源不可访问 404；限流 429；内部故障 500/503。下方保留全局 HTTP 错误模型，非每个状态都会由本处理器产生。"
    if name == "health_check":
        errors = "错误：此存活检查不执行认证、参数校验或依赖探测；下方错误模型为全局协议参考。"
    operation["description"] = (
        f"API v1（URL 主版本 `/api/v1`）。{purpose}\n\n{auth}\n\n{_rate_limit(name, path)}\n\n{errors}\n\n使用示例（先创建自己的资源，替换示例 ID、令牌和文件）：\n\n```bash\n{_curl(path, method, operation, name)}\n```"
    )
    operation["x-codeSamples"] = [
        {"lang": "Shell", "label": "curl", "source": _curl(path, method, operation, name)}
    ]


def install_documentation(app: FastAPI) -> None:
    """Decorate this app's default generator after its routes are registered."""
    app.description = OVERVIEW
    generate = app.openapi

    def documented_openapi() -> dict[str, Any]:
        if app.openapi_schema is not None:
            return app.openapi_schema
        schema = generate()
        schema["info"]["version"] = API_CONTRACT_VERSION
        _describe_fields(schema)
        for path, methods in schema["paths"].items():
            for method, operation in methods.items():
                if method in {"get", "post", "put", "patch", "delete", "options", "head", "trace"}:
                    _document_operation(path, method, operation)
        app.openapi_schema = schema
        return schema

    app.openapi = documented_openapi
