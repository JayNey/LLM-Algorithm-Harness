import type { AxiosInstance } from 'axios'
import { ApiClientError } from '../auth/http.ts'

export type ReportFormat = 'markdown' | 'html' | 'csv'
export interface ReportDownload {
  blob: Blob
  filename: string
}
const extensions: Record<ReportFormat, string> = {
  markdown: 'md',
  html: 'html',
  csv: 'csv',
}
function unsafeFilenameCharacter(char: string): boolean {
  return (
    char.charCodeAt(0) < 32 ||
    char.charCodeAt(0) === 127 ||
    '/\\:<>|?*'.includes(char)
  )
}

export function reportFilename(header: unknown, fallback: string): string {
  if (typeof header !== 'string') return fallback
  const encoded = /filename\*=UTF-8''([^;]+)/i.exec(header)
  const plain = /filename=(?:"([^"]*)"|([^;]*))/i.exec(header)
  try {
    const name = (
      encoded
        ? decodeURIComponent(encoded[1])
        : (plain?.[1] ?? plain?.[2] ?? '')
    ).trim()
    return name &&
      !Array.from(name).some(unsafeFilenameCharacter) &&
      name !== '.' &&
      name !== '..'
      ? name
      : fallback
  } catch {
    return fallback
  }
}

export function createReportClient(http: AxiosInstance) {
  return {
    async download(
      runId: string,
      format: ReportFormat,
      signal?: AbortSignal,
    ): Promise<ReportDownload> {
      if (!runId.trim()) throw new ApiClientError('报告运行标识不可用')
      if (!(format in extensions)) throw new ApiClientError('报告格式不可用')
      const fallback =
        Array.from(runId, (char) =>
          unsafeFilenameCharacter(char) ? '_' : char,
        ).join('') +
        '.' +
        extensions[format]
      return http.get<unknown, ReportDownload>(
        '/reports/' + format + '/' + encodeURIComponent(runId),
        {
          signal,
          timeout: 60_000,
          responseType: 'blob',
          // The shared HTTP interceptor unwraps JSON data; package file bytes and
          // headers together here so it can retain its existing session handling.
          transformResponse: (body: Blob, headers) => ({
            blob: body,
            filename: reportFilename(headers['content-disposition'], fallback),
          }),
        },
      )
    },
  }
}
