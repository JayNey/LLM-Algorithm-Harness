import type { AxiosInstance } from 'axios'
import { ApiClientError } from '../auth/http.ts'
import type {
  ApiPage,
  DirectImportResult,
  EvaluationOptionsMeta,
  ImportJobProgress,
  ImportJobStarted,
  ImportValidation,
  ProblemClient,
  ProblemHistoryItem,
  ProblemOption,
  UploadedFile,
} from './types.ts'

function protocol(field: string): never {
  throw new ApiClientError('题目接口响应格式不兼容', undefined, { field })
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
function boolean(value: unknown, field: string): boolean {
  if (typeof value !== 'boolean') protocol(field)
  return value
}
function count(value: unknown, field: string): number {
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < 0)
    protocol(field)
  return value
}
function nullableNumber(value: unknown, field: string): number | null {
  return value === null ? null : count(value, field)
}
function nullableFloat(value: unknown, field: string): number | null {
  if (value === null) return null
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0)
    protocol(field)
  return value
}
function array<T>(
  value: unknown,
  read: (value: unknown, field: string) => T,
  field: string,
): T[] {
  if (!Array.isArray(value)) protocol(field)
  return value.map((item, index) => read(item, `${field}.${index}`))
}
function page<T>(
  value: unknown,
  read: (value: unknown, field: string) => T,
  field: string,
): ApiPage<T> {
  const data = record(value, field)
  const limit = count(data.limit, `${field}.limit`)
  if (limit < 1 || limit > 100) protocol(`${field}.limit`)
  return {
    items: array(data.items, read, `${field}.items`),
    total: count(data.total, `${field}.total`),
    limit,
    offset: count(data.offset, `${field}.offset`),
    has_more: boolean(data.has_more, `${field}.has_more`),
  }
}
function problemSource(value: unknown, field: string) {
  if (value !== 'shared' && value !== 'personal') protocol(field)
  return value
}

function problemOption(value: unknown, field: string): ProblemOption {
  const data = record(value, field)
  return {
    problem_id: text(data.problem_id, `${field}.problem_id`),
    title: text(data.title, `${field}.title`, true),
    difficulty:
      data.difficulty === null || data.difficulty === undefined
        ? null
        : text(data.difficulty, `${field}.difficulty`),
    source: problemSource(data.source, `${field}.source`),
  }
}

function optionsMeta(value: unknown): EvaluationOptionsMeta {
  const data = record(value, 'options')
  return {
    sources: array(
      data.sources,
      (item, field) => {
        const row = record(item, field)
        return {
          id: problemSource(row.id, `${field}.id`),
          label: text(row.label, `${field}.label`),
          problem_count: count(row.problem_count, `${field}.problem_count`),
        }
      },
      'options.sources',
    ),
  }
}

function validation(value: unknown): ImportValidation {
  const data = record(value, 'validation')
  return {
    total: count(data.total, 'validation.total'),
    valid: count(data.valid, 'validation.valid'),
    invalid: count(data.invalid, 'validation.invalid'),
    errors: array(
      data.errors,
      (item, field) => {
        // api/files/parsing.py problem_error：{index, errors:[{field,type}]}
        const row = record(item, field)
        return {
          index: count(row.index, `${field}.index`),
          errors: array(
            row.errors,
            (detail, detailField) => {
              const cell = record(detail, detailField)
              return {
                field: text(cell.field, `${detailField}.field`, true),
                type: text(cell.type, `${detailField}.type`, true),
              }
            },
            `${field}.errors`,
          ),
        }
      },
      'validation.errors',
    ),
    errors_truncated: boolean(
      data.errors_truncated,
      'validation.errors_truncated',
    ),
    file_id:
      data.file_id === null || data.file_id === undefined
        ? null
        : text(data.file_id, 'validation.file_id'),
    duplicates: count(data.duplicates, 'validation.duplicates'),
    imported: count(data.imported, 'validation.imported'),
    dataset_total: count(data.dataset_total, 'validation.dataset_total'),
  }
}

function directImportResult(value: unknown): DirectImportResult {
  const data = record(value, 'import')
  return {
    file_id: text(data.file_id, 'import.file_id'),
    job_id: text(data.job_id, 'import.job_id'),
    validation: validation(data.validation),
  }
}

function uploadedFile(value: unknown): UploadedFile {
  // /files/upload 的 data 形状：{file: {id, filename, size, ...}, parsed}
  const data = record(value, 'upload')
  const file = record(data.file, 'upload.file')
  return {
    file_id: text(file.id, 'upload.file.id'),
    filename:
      file.filename === null || file.filename === undefined
        ? null
        : text(file.filename, 'upload.file.filename'),
    size_bytes: nullableNumber(file.size, 'upload.file.size'),
  }
}

function importStarted(value: unknown): ImportJobStarted {
  const data = record(value, 'import-start')
  return {
    job_id: text(data.job_id, 'import-start.job_id'),
    task_id: text(data.task_id, 'import-start.task_id'),
    status: text(data.status, 'import-start.status'),
  }
}

function importProgress(value: unknown): ImportJobProgress {
  const data = record(value, 'import-job')
  const status = text(data.status, 'import-job.status')
  // percentage 是浮点（processed/total*100 真除法），不能走整数校验
  const percentage = data.percentage
  if (
    typeof percentage !== 'number' ||
    !Number.isFinite(percentage) ||
    percentage < 0 ||
    percentage > 100
  )
    protocol('import-job.percentage')
  let result: ImportValidation | null = null
  let failureDetail: string | null = null
  if (data.result !== null && data.result !== undefined) {
    if (status === 'completed') {
      result = validation(data.result)
    } else {
      // 失败终态的 result 是 {status_code, detail}，不是导入报告
      const failure = record(data.result, 'import-job.result')
      failureDetail =
        failure.detail === null || failure.detail === undefined
          ? null
          : text(String(failure.detail), 'import-job.result.detail', true)
    }
  }
  return {
    job_id: text(data.job_id, 'import-job.job_id'),
    status,
    processed: count(data.processed, 'import-job.processed'),
    total: count(data.total, 'import-job.total'),
    percentage,
    result,
    failureDetail,
  }
}

function historyItem(value: unknown, field: string): ProblemHistoryItem {
  const data = record(value, field)
  return {
    problem_id: text(data.problem_id, `${field}.problem_id`),
    strategy: text(data.strategy, `${field}.strategy`),
    status: text(data.status, `${field}.status`),
    iterations: nullableNumber(data.iterations, `${field}.iterations`),
    tokens: nullableNumber(data.tokens, `${field}.tokens`),
    execution_time: nullableFloat(
      data.execution_time,
      `${field}.execution_time`,
    ),
    run_id:
      data.run_id === null || data.run_id === undefined
        ? null
        : text(data.run_id, `${field}.run_id`),
  }
}

// 导入管道（create_job）只接受 .json/.csv；YAML 仅存在于解析层，不走导入
const ALLOWED_SUFFIXES = ['.json', '.csv']
export const DIRECT_IMPORT_MAX_BYTES = 5 * 1024 * 1024

// 注入 useAuthStore 提供的同一已解包实例，沿用 Cookie、CSRF 和共享刷新。
export function createProblemClient(http: AxiosInstance): ProblemClient {
  async function get<T>(
    url: string,
    read: (value: unknown) => T,
    params?: unknown,
    signal?: AbortSignal,
    timeout = 10_000,
  ): Promise<T> {
    return read(
      await http.get<unknown, unknown>(url, { params, signal, timeout }),
    )
  }
  return {
    options: async (signal) =>
      get('/evaluation-options', optionsMeta, undefined, signal),
    problems: (query, signal) =>
      get(
        '/evaluation-options/problems',
        (value) => page(value, problemOption, 'problems'),
        { source: query.source, limit: query.limit, offset: query.offset },
        signal,
      ),
    uploadFile: async (file) => {
      const form = new FormData()
      form.append('file', file)
      const data = await http.post<unknown, unknown>('/files/upload', form, {
        timeout: 120_000,
      })
      return uploadedFile(data)
    },
    directImport: async (file, mode) => {
      const form = new FormData()
      form.append('file', file)
      form.append('mode', mode)
      form.append('validate', 'true')
      const data = await http.post<unknown, unknown>('/problems/upload', form, {
        timeout: 120_000,
      })
      return directImportResult(data)
    },
    startImport: async (fileId, mode) => {
      const data = await http.post<unknown, unknown>(
        '/problems/import',
        { file_id: fileId, mode },
        { timeout: 20_000 },
      )
      return importStarted(data)
    },
    importJob: async (jobId, signal) =>
      get(
        `/imports/${encodeURIComponent(jobId)}`,
        importProgress,
        undefined,
        signal,
      ),
    problemHistory: async (problemId, query, signal) =>
      get(
        `/results/problems/${encodeURIComponent(problemId)}`,
        (value) => page(value, historyItem, 'history'),
        { limit: query.limit, offset: query.offset },
        signal,
      ),
    exportUrl: (format) =>
      `/api/v1/problems/export?format=${format === 'csv' ? 'csv' : 'json'}`,
  }
}

export function validateImportFile(file: {
  name: string
  size: number
}): string | null {
  const lower = file.name.toLowerCase()
  if (!ALLOWED_SUFFIXES.some((suffix) => lower.endsWith(suffix)))
    return `仅支持 ${ALLOWED_SUFFIXES.join(' / ')} 格式`
  if (file.size <= 0) return '文件不能为空'
  return null
}
