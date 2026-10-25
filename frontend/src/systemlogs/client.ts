import type { AxiosInstance } from 'axios'
import { ApiClientError } from '../auth/http.ts'
import type { LogEntry, LogQuery, SystemLogClient } from './types.ts'

function protocol(field: string): never {
  throw new ApiClientError('日志接口响应格式不兼容', undefined, { field })
}
function record(value: unknown, field: string): Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value))
    protocol(field)
  return value as Record<string, unknown>
}
function text(value: unknown, field: string, allowEmpty = false): string {
  if (typeof value !== 'string' || (!allowEmpty && !value.trim()))
    protocol(field)
  return value
}
function count(value: unknown, field: string): number {
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < 0)
    protocol(field)
  return value
}
function nullableText(value: unknown, field: string): string | null {
  return value === null || value === undefined ? null : text(value, field, true)
}
function float(value: unknown, field: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0)
    protocol(field)
  return value
}

function logEntry(value: unknown, field: string): LogEntry {
  const data = record(value, field)
  return {
    id: count(data.id, `${field}.id`),
    timestamp: float(data.timestamp, `${field}.timestamp`),
    level: text(data.level, `${field}.level`),
    message: text(data.message, `${field}.message`, true),
    user_id: nullableText(data.user_id, `${field}.user_id`),
    run_id: nullableText(data.run_id, `${field}.run_id`),
    // context 为服务端自由 JSON（已脱敏），前端不解析结构
    context: data.context,
  }
}

const LEVELS = new Set(['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'])

export function readLogQuery(input: {
  level: string
  search: string
  start: string
  end: string
}): { errors: Record<string, string>; query: LogQuery } {
  const errors: Record<string, string> = {}
  const level = input.level.trim().toUpperCase()
  if (level && !LEVELS.has(level)) errors.level = '未知日志级别'
  const startSeconds = input.start ? Date.parse(input.start) / 1000 : undefined
  const endSeconds = input.end ? Date.parse(input.end) / 1000 : undefined
  if (input.start && Number.isNaN(startSeconds)) errors.start = '时间格式无效'
  if (input.end && Number.isNaN(endSeconds)) errors.end = '时间格式无效'
  if (
    startSeconds !== undefined &&
    endSeconds !== undefined &&
    !Number.isNaN(startSeconds) &&
    !Number.isNaN(endSeconds) &&
    startSeconds > endSeconds
  )
    errors.end = '起始时间须早于结束时间'
  return {
    errors,
    query: {
      ...(level && LEVELS.has(level) ? { level } : {}),
      ...(input.search.trim() ? { search: input.search.trim() } : {}),
      ...(startSeconds !== undefined && !Number.isNaN(startSeconds)
        ? { start: startSeconds }
        : {}),
      ...(endSeconds !== undefined && !Number.isNaN(endSeconds)
        ? { end: endSeconds }
        : {}),
      limit: 50,
      offset: 0,
    },
  }
}

// 注入 useAuthStore 提供的同一已解包实例，沿用 Cookie、CSRF 和共享刷新。
export function createSystemLogClient(http: AxiosInstance): SystemLogClient {
  return {
    query: async (query, signal) => {
      const data = await http.get<unknown, unknown>('/logs', {
        params: {
          ...(query.level ? { level: query.level } : {}),
          ...(query.start !== undefined ? { start: query.start } : {}),
          ...(query.end !== undefined ? { end: query.end } : {}),
          ...(query.search ? { search: query.search } : {}),
          limit: query.limit,
          offset: query.offset,
        },
        signal,
        timeout: 15_000,
      })
      const page = record(data, 'logs')
      const items = page.items
      if (!Array.isArray(items)) protocol('logs.items')
      return {
        items: items.map((item, index) =>
          logEntry(item, `logs.items.${index}`),
        ),
        total: count(page.total, 'logs.total'),
        limit: count(page.limit, 'logs.limit'),
        offset: count(page.offset, 'logs.offset'),
      }
    },
  }
}
