import axios, {
  type AxiosAdapter,
  type AxiosInstance,
  type AxiosResponse,
} from 'axios'
import type { StoredSession } from './tokenStore.ts'

const refreshWindowMs = 30_000

const authSuffixes = [
  '/auth/login',
  '/auth/register',
  '/auth/refresh',
  '/auth/logout',
] as const

export function isAuthEndpoint(url: string): boolean {
  const path = url.split('?')[0] ?? ''
  return authSuffixes.some((suffix) => path.endsWith(suffix))
}

export function shouldRefreshBeforeRequest(
  expiresAt: number,
  now: number,
): boolean {
  return expiresAt - now < refreshWindowMs
}

export class ApiClientError extends Error {
  readonly status: number | undefined

  constructor(message: string, status?: number) {
    super(message)
    this.name = 'ApiClientError'
    this.status = status
  }
}

export interface HttpClientOptions {
  baseURL: string
  now: () => number
  read: () => StoredSession | null
  write: (session: StoredSession) => void
  clear: () => void
  refresh: () => Promise<StoredSession>
  adapter?: AxiosAdapter
}

function messageFrom(data: unknown, fallback: string): string {
  if (typeof data === 'object' && data !== null) {
    const body = data as { detail?: unknown; message?: unknown }
    if (typeof body.detail === 'string' && body.detail.length > 0) {
      return body.detail
    }
    if (typeof body.message === 'string' && body.message.length > 0) {
      return body.message
    }
  }
  return fallback
}

function unwrapData(data: unknown): unknown {
  if (typeof data === 'object' && data !== null && 'data' in data) {
    return data.data
  }
  return data
}

function transformResponse(
  data: unknown,
  headers: unknown,
  status?: number,
): unknown {
  void headers
  if (status === 204) return undefined
  if (typeof data !== 'string' || data.length === 0) return data
  try {
    return JSON.parse(data) as unknown
  } catch {
    return data
  }
}

function failure(error: unknown): ApiClientError {
  const response =
    typeof error === 'object' && error !== null && 'response' in error
      ? error.response
      : undefined
  const body =
    typeof response === 'object' && response !== null && 'data' in response
      ? response.data
      : undefined
  const status =
    typeof response === 'object' &&
    response !== null &&
    'status' in response &&
    typeof response.status === 'number'
      ? response.status
      : undefined
  const fallback = error instanceof Error ? error.message : '请求失败'
  return new ApiClientError(messageFrom(body, fallback), status)
}

export function createHttpClient(options: HttpClientOptions): AxiosInstance {
  const client = axios.create({
    baseURL: options.baseURL,
    adapter: options.adapter,
    transformResponse: [transformResponse],
  })

  client.interceptors.request.use(async (config) => {
    if (isAuthEndpoint(config.url ?? '')) {
      config.headers.delete('Authorization')
      return config
    }

    let current = options.read()
    if (
      current &&
      shouldRefreshBeforeRequest(current.expiresAt, options.now())
    ) {
      current = await options.refresh()
      options.write(current)
    }
    if (current?.accessToken) {
      config.headers.set('Authorization', `Bearer ${current.accessToken}`)
    }
    return config
  })

  client.interceptors.response.use(
    (response) => {
      if (response.status === 204) {
        return undefined as unknown as AxiosResponse
      }
      if (response.status < 200 || response.status >= 300) {
        throw new ApiClientError(
          messageFrom(response.data, response.statusText || '请求失败'),
          response.status,
        )
      }
      return unwrapData(response.data) as AxiosResponse
    },
    (error: unknown) => {
      throw failure(error)
    },
  )

  return client
}
