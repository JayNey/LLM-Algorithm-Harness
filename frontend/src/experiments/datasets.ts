import { ApiClientError } from '../auth/http.ts'

export interface DatasetSource {
  dataset_id?: string
  dataset_path?: string | null
}

export interface DatasetReference {
  id: string
  name: string
  problem_count: number
  updated_at: number
}

export function datasetConflict(source: DatasetSource): boolean {
  return Boolean(source.dataset_id?.trim() && source.dataset_path?.trim())
}

export function datasetPayload(source: DatasetSource): DatasetSource {
  return source.dataset_id?.trim()
    ? { dataset_id: source.dataset_id.trim() }
    : { dataset_path: source.dataset_path?.trim() }
}

export function readDatasetSource(
  value: Record<string, unknown>,
): DatasetSource {
  const id = value.dataset_id
  const path = value.dataset_path
  const hasId = typeof id === 'string' && Boolean(id.trim())
  const hasPath = typeof path === 'string' && Boolean(path.trim())
  if (hasId === hasPath || (id != null && !hasId) || (path != null && !hasPath))
    throw new ApiClientError('数据集引用格式不兼容')
  return hasId ? { dataset_id: id } : { dataset_path: path as string }
}

export function readDatasets(value: unknown): DatasetReference[] {
  if (!Array.isArray(value)) throw new ApiClientError('数据集列表格式不兼容')
  return value.map((item: unknown) => {
    if (typeof item !== 'object' || item === null)
      throw new ApiClientError('数据集列表格式不兼容')
    const row = item as Record<string, unknown>
    if (
      typeof row.id !== 'string' ||
      !row.id.trim() ||
      typeof row.name !== 'string' ||
      !row.name.trim() ||
      typeof row.problem_count !== 'number' ||
      !Number.isSafeInteger(row.problem_count) ||
      row.problem_count < 0 ||
      typeof row.updated_at !== 'number' ||
      !Number.isSafeInteger(row.updated_at) ||
      row.updated_at < 0
    )
      throw new ApiClientError('数据集列表格式不兼容')
    return {
      id: row.id,
      name: row.name,
      problem_count: row.problem_count,
      updated_at: row.updated_at,
    }
  })
}
