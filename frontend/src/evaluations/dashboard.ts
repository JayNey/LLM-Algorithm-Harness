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
    async cost(signal: AbortSignal) {
      const value: unknown = await http.get('/costs/summary', {
        signal,
        timeout: 15_000,
      })
      if (
        typeof value !== 'object' ||
        value === null ||
        !('by_source' in value) ||
        typeof value.by_source !== 'object' ||
        value.by_source === null ||
        Array.isArray(value.by_source)
      )
        throw new ApiClientError('费用汇总响应格式不兼容')

      const sources = value.by_source as Record<string, unknown>
      let knownCostUsd = 0
      let unknownCostCount = 0
      for (const source of ['evaluations', 'benchmarks']) {
        if (!Object.hasOwn(sources, source)) continue
        const entry = sources[source]
        if (
          typeof entry !== 'object' ||
          entry === null ||
          !('known_cost_usd' in entry) ||
          typeof entry.known_cost_usd !== 'number' ||
          !Number.isFinite(entry.known_cost_usd) ||
          entry.known_cost_usd < 0 ||
          !('unknown_cost_count' in entry) ||
          typeof entry.unknown_cost_count !== 'number' ||
          !Number.isSafeInteger(entry.unknown_cost_count) ||
          entry.unknown_cost_count < 0
        )
          throw new ApiClientError('费用汇总响应格式不兼容')
        knownCostUsd += entry.known_cost_usd
        unknownCostCount += entry.unknown_cost_count
      }
      return { knownCostUsd, unknownCostCount }
    },
    system(role: UserRole | null, signal: AbortSignal) {
      return role === 'admin'
        ? monitoring.systemStatus(signal)
        : Promise.resolve(null)
    },
  }
}
