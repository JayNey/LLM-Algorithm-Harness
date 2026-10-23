## 实现
复用 AsyncTask.started_at/completed_at。状态与进度更新共用时间记录逻辑：首次 running 写开始时间，首次终态写结束时间；重复通知保留时间。完成/失败后重新 running 清空旧结束时间，保留首次开始时间。
性能接口 tasks 聚合 evaluation/experiment/benchmark/import，evaluations 只聚合 evaluation。只读 SQL 聚合，不轮询 Celery，不加载结果或凭据，兼容 SQLite/PostgreSQL。
平均耗时使用 completed/failed 且开始结束齐全、结束不早于开始的样本，单位秒。成功率为已实际开始的 completed/(completed+failed)，缺少结束或时间逆序的行不进入耗时；取消不纳入成功率。空分母返回 null。累计口径覆盖当前数据库保留记录，耗时为首次开始至最终结束的墙钟时间（包含暂停、重试间隔，排除首次排队）。数据库失败返回 unavailable 和 null，不泄露异常。
