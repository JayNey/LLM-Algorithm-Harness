/** 题目管理前端类型（issue #163，真实契约范围）。
 * 列表复用 #216 的 evaluation-options 契约（只下发元数据 4 字段）；
 * 导入/导出走 #153 的个人题库管道。字段契约见
 * api/evaluation_options.py、api/routes/files.py、api/files/store.py。
 */

export type ProblemSource = 'shared' | 'personal'
export type SourceFilter = 'all' | 'shared' | 'personal'

export interface ProblemOption {
  problem_id: string
  title: string
  difficulty: string | null
  source: ProblemSource
}

export interface SourceOption {
  id: ProblemSource
  label: string
  problem_count: number
}

export interface EvaluationOptionsMeta {
  sources: SourceOption[]
}

export interface ApiPage<T> {
  items: T[]
  total: number
  limit: number
  offset: number
  has_more: boolean
}

export interface ProblemListQuery {
  source: SourceFilter
  limit: number
  offset: number
}

/** 同步直导的 validation 报告（api/files/store.py merge_dataset 形状）。 */
export interface ImportValidation {
  total: number
  valid: number
  invalid: number
  errors: { index: number; error: string }[]
  errors_truncated: boolean
  file_id: string | null
  duplicates: number
  imported: number
  dataset_total: number
}

export interface DirectImportResult {
  file_id: string
  job_id: string
  validation: ImportValidation
}

/** 异步导入：上传文件元数据（POST /files/upload 的 data.file）。 */
export interface UploadedFile {
  file_id: string
  filename: string | null
  size_bytes: number | null
}

export interface ImportJobStarted {
  job_id: string
  task_id: string
  status: string
}

/** GET /imports/{job_id} 进度。 */
export interface ImportJobProgress {
  job_id: string
  status: string
  processed: number
  total: number
  percentage: number
  result: ImportValidation | null
}

/** 单题评估历史条目（/results/problems/{id}）。 */
export interface ProblemHistoryItem {
  problem_id: string
  strategy: string
  status: string
  iterations: number | null
  tokens: number | null
  execution_time: number | null
  run_id: string | null
}

export interface HistoryQuery {
  limit: number
  offset: number
}

export type ImportMode = 'append' | 'overwrite'

export interface ProblemClient {
  options(signal?: AbortSignal): Promise<EvaluationOptionsMeta>
  problems(
    query: ProblemListQuery,
    signal?: AbortSignal,
  ): Promise<ApiPage<ProblemOption>>
  uploadFile(file: File): Promise<UploadedFile>
  directImport(file: File, mode: ImportMode): Promise<DirectImportResult>
  startImport(fileId: string, mode: ImportMode): Promise<ImportJobStarted>
  importJob(jobId: string, signal?: AbortSignal): Promise<ImportJobProgress>
  problemHistory(
    problemId: string,
    query: HistoryQuery,
    signal?: AbortSignal,
  ): Promise<ApiPage<ProblemHistoryItem>>
  exportUrl(format: 'json' | 'csv'): string
}
