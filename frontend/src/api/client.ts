import type { ApiErrorBody } from '../types'

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

function extractMessage(body: ApiErrorBody | undefined, fallback: string): string {
  if (!body?.detail) return fallback
  if (typeof body.detail === 'string') return body.detail
  const first = body.detail[0]
  return first?.msg ?? fallback
}

/** Thin fetch wrapper: JSON in/out, typed errors, single place that knows
 * about the API's base path. Every request is relative (`/api/...`) so the
 * same code works behind Vite's dev proxy and behind nginx in production. */
export async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        ...init?.headers,
      },
    })
  } catch {
    throw new ApiError('Could not reach the server. Check your connection and try again.', 0)
  }

  if (!response.ok) {
    let body: ApiErrorBody | undefined
    try {
      body = (await response.json()) as ApiErrorBody
    } catch {
      body = undefined
    }
    throw new ApiError(
      extractMessage(body, `Request failed (${response.status})`),
      response.status,
    )
  }

  if (response.status === 204) {
    return undefined as T
  }

  return (await response.json()) as T
}
