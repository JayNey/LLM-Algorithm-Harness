## 实现方案
SQLAlchemy 按实际 engine 对象去重，每个来源复用原有有界采集器；应用启动将所有服务 engine 显式传给监控。认证与文件共用 AuthStore，按 store 绑定一个 SQLite 采集器，以 Connection/Cursor 子类覆盖 execute/executemany/executescript；脚本作为单次执行调用，不保存语句。采集只记录完成时间、耗时和成功标志，失败不能改变原查询异常。

## 响应与生命周期
保留 database_queries 原评估顶层统计，新增 sources 和 coverage。每个来源具有固定 source_id、roles、backend、process_id、scope；共享 SQLite 标记 auth/file/monitoring 用途。无连接串或文件路径。所有统计仅覆盖当前进程绑定连接，不覆盖 Celery、其他 API 实例或重启历史；不提供跨源聚合 p95。关闭监控逐个关闭并解除引用。SQLite 延迟排除连接获取和结果抓取，executescript 为整体执行延迟。

## 验证
真实独立引擎执行、共享对象去重；SQLite 成功/失败、cursor 路径、批量/脚本、事务回滚、采集失败隔离、关闭重开；HTTP 响应来源及隐私；现有监控/认证/文件回归。
