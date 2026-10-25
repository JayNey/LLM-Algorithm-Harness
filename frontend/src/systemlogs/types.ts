/** 系统日志查询前端类型（issue #167 簇 D）。
 * 字段与 api/monitoring/store.py 的 query_logs 行（api_monitor_logs 表）
 * 及 api/routes/monitoring.py 的 /logs 响应形状对齐（admin 端点）。
 */

export interface LogEntry {
  id: number
  timestamp: number
  level: string
  message: string
  user_id: string | null
  run_id: string | null
  context: unknown
}

export interface LogQuery {
  level?: string
  start?: number
  end?: number
  search?: string
  limit: number
  offset: number
}

export interface LogPage {
  items: LogEntry[]
  total: number
  limit: number
  offset: number
}

export interface SystemLogClient {
  query(query: LogQuery, signal?: AbortSignal): Promise<LogPage>
}
