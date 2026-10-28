import type { AxiosInstance } from 'axios'
import { ApiClientError } from '../auth/http.ts'
import type { UserRole } from '../auth/roles.ts'
import { createMonitoringClient } from '../monitoring/client.ts'
import { createEvaluationClient } from './client.ts'

/** Compose existing owner-scoped APIs; never derive totals from recent rows. */
export function createDashboardClient(http: AxiosInstance) {
  const evaluations = createEvaluationClient(http)
  const monitoring = createMonitoringClient(http)
  return {
    async recent(signal: AbortSignal) {
      const first = await evaluations.list({ limit: 5, offset: 0 }, signal)
      signal.throwIfAborted()
      const page =
        first.total > 5
          ? await evaluations.list(
              { limit: 5, offset: first.total - 5 },
              signal,
            )
          : first
      signal.throwIfAborted()
      return { total: page.total, items: [...page.items].reverse() }
    },
    async count(status: 'running' | 'completed', signal: AbortSignal) {
      return (await evaluations.list({ status, limit: 1, offset: 0 }, signal))
        .total
    },
    async cost(signal: AbortSignal): Promise<number> {
      const value: unknown = await http.get('/costs/summary', {
        signal,
        timeout: 15_000,
      })
      if (
        typeof value !== 'object' ||
        value === null ||
        !('total_cost_usd' in value) ||
        typeof value.total_cost_usd !== 'number' ||
        !Number.isFinite(value.total_cost_usd) ||
        value.total_cost_usd < 0
      )
        throw new ApiClientError('费用汇总响应格式不兼容')
      return value.total_cost_usd
    },
    system(role: UserRole | null, signal: AbortSignal) {
      return role === 'admin'
        ? monitoring.systemStatus(signal)
        : Promise.resolve(null)
    },
  }
}
