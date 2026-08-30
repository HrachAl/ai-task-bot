import { useCallback, useEffect, useState } from 'react'
import { ApiError } from '../api/client'
import { fetchMe } from '../api/me'
import { captureTokenFromUrl, clearToken } from '../auth'
import type { Me } from '../types'

export type SessionState =
  | { status: 'loading' }
  /** No token yet (or it was rejected) — the user needs a fresh link from the bot. */
  | { status: 'anonymous'; reason: 'missing' | 'invalid' }
  | { status: 'authenticated'; user: Me }
  /** The token may be fine; we just couldn't reach the API. */
  | { status: 'error'; message: string }

/** Resolves who is looking at the dashboard.
 *
 * The token arrives once, as `?token=` in the link the bot sends, and is
 * then remembered per browser. It is verified against GET /api/me on every
 * load so a revoked or mistyped token shows the "connect" screen instead of
 * an empty board that looks like data loss.
 */
export function useSession() {
  const [state, setState] = useState<SessionState>({ status: 'loading' })

  const resolve = useCallback(async () => {
    const token = captureTokenFromUrl()
    if (!token) {
      setState({ status: 'anonymous', reason: 'missing' })
      return
    }

    setState({ status: 'loading' })
    try {
      const user = await fetchMe()
      setState({ status: 'authenticated', user })
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        clearToken()
        setState({ status: 'anonymous', reason: 'invalid' })
        return
      }
      setState({
        status: 'error',
        message:
          err instanceof ApiError ? err.message : 'Could not reach the server.',
      })
    }
  }, [])

  useEffect(() => {
    void resolve()
  }, [resolve])

  const signOut = useCallback(() => {
    clearToken()
    setState({ status: 'anonymous', reason: 'missing' })
  }, [])

  return { state, retry: resolve, signOut }
}
