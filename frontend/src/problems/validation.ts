import type { ProblemListQuery, SourceFilter } from './types.ts'

const sourceFilters = new Set(['all', 'shared', 'personal'])

function integer(
  value: string | null,
  fallback: number,
  min: number,
  max: number,
): number {
  if (!value || !/^\d+$/.test(value)) return fallback
  const number = Number(value)
  return Number.isSafeInteger(number) && number >= min && number <= max
    ? number
    : fallback
}

export function readListQuery(search: URLSearchParams): ProblemListQuery {
  const raw = search.get('source')
  const source: SourceFilter =
    raw && sourceFilters.has(raw) ? (raw as SourceFilter) : 'all'
  return {
    source,
    limit: integer(search.get('limit'), 20, 1, 100),
    offset: integer(search.get('offset'), 0, 0, Number.MAX_SAFE_INTEGER),
  }
}

export function writeListQuery(query: ProblemListQuery): URLSearchParams {
  const normalized = readListQuery(
    new URLSearchParams({
      source: query.source,
      limit: String(query.limit),
      offset: String(query.offset),
    }),
  )
  const search = new URLSearchParams()
  if (normalized.source !== 'all') search.set('source', normalized.source)
  search.set('limit', String(normalized.limit))
  search.set('offset', String(normalized.offset))
  return search
}
