import axios, {
  type AxiosAdapter,
  type AxiosInstance,
  type AxiosResponse,
  type InternalAxiosRequestConfig,
} from 'axios'
import { createRefreshCoordinator } from './refreshCoordinator.ts'
import type { StoredSession } from './tokenStore.ts'

const refreshWindowMs = 30_000
const unavailable = '服务暂时不可用'

const tokenlessAuthSuffixes = [
  '/auth/login',
  '/auth/register',
  '/auth/refresh',
] as const

function requestPath(url: string): string {
  return url.split('?')[0] ?? ''
}

function endsWithAny(path: string, suffixes: readonly string[]): boolean {
  return suffixes.some((suffix) => path.endsWith(suffix))
}

export function isAuthEndpoint(url: string): boolean {
  const path = requestPath(url)
  return (
    endsWithAny(path, tokenlessAuthSuffixes) || path.endsWith('/auth/logout')
  )
}

function skipsAccessToken(url: string): boolean {
  return endsWithAny(requestPath(url), tokenlessAuthSuffixes)
}

export function shouldRefreshBeforeRequest(
  expiresAt: number,
  now: number,
): boolean {
  return expiresAt - now < refreshWindowMs
}

export class ApiClientError extends Error {
  readonly status: number | undefined
  readonly details: unknown

  constructor(message: string, status?: number, details?: unknown) {
    super(message)
    this.name = 'ApiClientError'
    this.status = status
    this.details = details
  }
}

export interface HttpClientOptions {
  baseURL: string
  now: () => number
  read: () => StoredSession | null
  write: (session: StoredSession) => void
  clear: () => void
  refresh?: () => Promise<StoredSession>
  adapter?: AxiosAdapter
}

function bodyRecord(
  data: unknown,
): { detail?: unknown; message?: unknown; details?: unknown } | null {
  if (typeof data === 'object' && data !== null) {
    return data as { detail?: unknown; message?: unknown; details?: unknown }
  }
  return null
}

function messageFrom(data: unknown, fallback: string): string {
  const body = bodyRecord(data)
  if (!body) return fallback
  if (typeof body.detail === 'string' && body.detail.length > 0) {
    return body.detail
  }
  if (typeof body.message === 'string' && body.message.length > 0) {
    return body.message
  }
  return fallback
}

function errorMessage(data: unknown, status: number | undefined): string {
  if (status !== undefined && status >= 500) return unavailable
  return messageFrom(data, unavailable)
}

function detailsFrom(data: unknown): unknown {
  const body = bodyRecord(data)
  if (!body || !('details' in body)) return undefined
  return body.details
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

interface RefreshPayload {
  access_token: string
  refresh_token: string
  expires_in: number
}

type RetryConfig = InternalAxiosRequestConfig & { __retried?: boolean }

function isRefreshPayload(value: unknown): value is RefreshPayload {
  if (typeof value !== 'object' || value === null) return false
  const payload = value as Record<string, unknown>
  return (
    typeof payload.access_token === 'string' &&
    typeof payload.refresh_token === 'string' &&
    typeof payload.expires_in === 'number'
  )
}

function errorResponse(error: unknown): {
  status: number | undefined
  data: unknown
  config: InternalAxiosRequestConfig | undefined
} {
  if (typeof error !== 'object' || error === null) {
    return { status: undefined, data: undefined, config: undefined }
  }
  const response =
    'response' in error &&
    typeof error.response === 'object' &&
    error.response !== null
      ? error.response
      : undefined
  const status =
    response && 'status' in response && typeof response.status === 'number'
      ? response.status
      : undefined
  const data = response && 'data' in response ? response.data : undefined
  const config =
    'config' in error &&
    typeof error.config === 'object' &&
    error.config !== null
      ? (error.config as InternalAxiosRequestConfig)
      : undefined
  return { status, data, config }
}

function failure(error: unknown): ApiClientError {
  if (error instanceof ApiClientError) throw error
  const { status, data } = errorResponse(error)
  return new ApiClientError(
    errorMessage(data, status),
    status,
    detailsFrom(data),
  )
}

function httpError(data: unknown, status: number | undefined): ApiClientError {
  return new ApiClientError(
    errorMessage(data, status),
    status,
    detailsFrom(data),
  )
}

export function createHttpClient(options: HttpClientOptions): AxiosInstance {
  const client = axios.create({
    baseURL: options.baseURL,
    adapter: options.adapter,
    transformResponse: [transformResponse],
  })

  async function refreshSession(): Promise<StoredSession> {
    const current = options.read()
    if (!current?.refreshToken) {
      throw new ApiClientError(unavailable)
    }
    const payload: unknown = await client.post(
      '/api/v1/auth/refresh',
      { refresh_token: current.refreshToken },
      { headers: { 'Content-Type': 'application/json' } },
    )
    if (!isRefreshPayload(payload)) {
      throw new ApiClientError(unavailable)
    }
    return {
      accessToken: payload.access_token,
      refreshToken: payload.refresh_token,
      expiresAt: options.now() + payload.expires_in * 1000,
      username: current.username,
    }
  }

  const coordinator = createRefreshCoordinator(async () => {
    try {
      const next = options.refresh
        ? await options.refresh()
        : await refreshSession()
      options.write(next)
      return next
    } catch (error) {
      options.clear()
      if (error instanceof ApiClientError) throw error
      throw new ApiClientError(unavailable)
    }
  })

  async function recover(
    config: InternalAxiosRequestConfig | undefined,
    createError: () => ApiClientError,
  ): Promise<AxiosResponse> {
    const retryConfig = config as RetryConfig | undefined
    if (
      !retryConfig ||
      retryConfig.__retried ||
      skipsAccessToken(retryConfig.url ?? '')
    ) {
      throw createError()
    }
    const next = await coordinator.refresh()
    retryConfig.__retried = true
    if (next.accessToken) {
      retryConfig.headers.set('Authorization', `Bearer ${next.accessToken}`)
    }
    return client.request(retryConfig)
  }

  client.interceptors.request.use(async (config) => {
    if (skipsAccessToken(config.url ?? '')) {
      config.headers.delete('Authorization')
      return config
    }

    let current = options.read()
    if (
      current &&
      shouldRefreshBeforeRequest(current.expiresAt, options.now())
    ) {
      current = await coordinator.refresh()
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
      if (response.status === 401) {
        return recover(response.config, () =>
          httpError(response.data, response.status),
        )
      }
      if (response.status < 200 || response.status >= 300) {
        throw httpError(response.data, response.status)
      }
      return unwrapData(response.data) as AxiosResponse
    },
    (error: unknown) => {
      const { status, config } = errorResponse(error)
      if (status === 401) {
        return recover(config, () => failure(error))
      }
      throw failure(error)
    },
  )

  return client
}
