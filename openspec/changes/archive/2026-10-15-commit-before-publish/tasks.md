## 1. 先落库再发布

- [x] 1.1 让实验启动、题目导入、基准运行和 `POST /api/v1/tasks` 调用 `enqueue_task()`。发布前任务记录已提交，发布携带预生成的 `celery_task_id`；发布失败时任务为 `failed` 且错误信息为 `failed to publish task to broker`。不改 `create_task()` 和 `EvaluationService.resume_evaluation`。验证：`python3 -m pytest tests/test_async_task_submission.py tests/test_tasks_api.py tests/test_api_monitoring_queue_compatibility.py tests/test_api_experiment_benchmark.py tests/test_api_files.py -q --no-cov` 通过，且这四个入口的用例能看到发布时记录已落库。
