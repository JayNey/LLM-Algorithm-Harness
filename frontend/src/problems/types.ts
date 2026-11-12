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
  /** api/files/parsing.py problem_error：{index, errors:[{field,type}]} */
  errors: {
    index: number
    errors: { field: string; type: string }[]
  }[]
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

export interface LeetCodeImportResult {
  problem_id: string
  imported: boolean
}

export type LeetCodeDifficulty = 'easy' | 'medium' | 'hard'

export interface LeetCodeFilters {
  tags: string[]
  difficulty: LeetCodeDifficulty | null
  limit: number
}

export interface LeetCodeCandidate {
  slug: string
  number: string
  title: string
  difficulty: LeetCodeDifficulty
  tags: string[]
  source_url: string
}

export interface LeetCodeBatchItem {
  slug: string
  status: 'pending' | 'imported' | 'duplicate' | 'failed'
  error?: string
  retryable?: boolean
}

export interface LeetCodeBatchResult {
  items: LeetCodeBatchItem[]
  imported: number
  duplicates: number
  failed: number
}

export interface PersonalProblemDetail {
  description: string
  source_url: string | null
  needs_manual_completion: boolean
}

/** 异步导入：POST /files/upload 的 data.file（api/files/service.py _persist 形状）。 */
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

/** GET /imports/{job_id} 进度；失败终态的 result 是 {status_code,detail} 而非报告。 */
export interface ImportJobProgress {
  job_id: string
  status: string
  processed: number
  total: number
  percentage: number
  result: ImportValidation | null
  batch?: LeetCodeBatchResult
  /** 失败终态时从 result.detail 提取的错误说明 */
  failureDetail: string | null
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

export interface GovernanceRequest {
  problem_ids: string[]
  run_ids: string[]
  easy_threshold: number
  hard_threshold: number
}

export interface GovernanceChange {
  problem_id: string
  title: string
  original_tags: string[]
  standard_tags: string[]
  suggestions: { tag: string; confidence: number; matched_keywords: string[] }[]
  original_difficulty: string
  suggested_difficulty: string
  sample_count: number
  pass_rate: number | null
}

export interface GovernancePreview {
  preview_token: string
  problems: GovernanceChange[]
}

export interface ApprovedChange {
  problem_id: string
  normalize_tags: boolean
  suggested_tags: string[]
  apply_difficulty: boolean
}

export interface GovernanceSaveRequest {
  preview: GovernanceRequest
  preview_token: string
  name: string
  changes: ApprovedChange[]
}

export interface DatasetVersion {
  id: string
  name: string
  problem_count: number
}

export interface DatasetVersionDetail extends DatasetVersion {
  problems: (Omit<ProblemOption, 'source'> & { tags: string[] })[]
}

export interface ProblemClient {
  previewGovernance(
    request: GovernanceRequest,
    signal?: AbortSignal,
  ): Promise<GovernancePreview>
  saveDatasetVersion(request: GovernanceSaveRequest): Promise<DatasetVersion>
  datasetVersions(signal?: AbortSignal): Promise<DatasetVersion[]>
  datasetVersion(
    id: string,
    signal?: AbortSignal,
  ): Promise<DatasetVersionDetail>
  options(signal?: AbortSignal): Promise<EvaluationOptionsMeta>
  problems(
    query: ProblemListQuery,
    signal?: AbortSignal,
  ): Promise<ApiPage<ProblemOption>>
  uploadFile(file: File): Promise<UploadedFile>
  directImport(file: File, mode: ImportMode): Promise<DirectImportResult>
  importLeetCode(url: string): Promise<LeetCodeImportResult>
  previewLeetCode(filters: LeetCodeFilters): Promise<LeetCodeCandidate[]>
  startLeetCodeBatch(slugs: string[]): Promise<ImportJobStarted>
  retryLeetCodeBatch(jobId: string, slugs: string[]): Promise<ImportJobStarted>
  personalProblem(
    problemId: string,
    signal?: AbortSignal,
  ): Promise<PersonalProblemDetail>
  startImport(fileId: string, mode: ImportMode): Promise<ImportJobStarted>
  importJob(jobId: string, signal?: AbortSignal): Promise<ImportJobProgress>
  problemHistory(
    problemId: string,
    query: HistoryQuery,
    signal?: AbortSignal,
  ): Promise<ApiPage<ProblemHistoryItem>>
  exportLibrary(format: 'json' | 'csv'): Promise<Blob>
}
