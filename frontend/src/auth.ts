/** Dashboard access.
 *
 * There is no sign-up form: the bot hands each user a link carrying their
 * personal token, which is kept in localStorage so the link only has to be
 * followed once per browser.
 */

const STORAGE_KEY = 'ai-task-bot-token'
const TOKEN_PARAM = 'token'

function readStored(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY)
  } catch {
    // Private-mode browsers can throw on storage access. The session still
    // works for the life of the tab, it just isn't remembered.
    return null
  }
}

function write(token: string): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, token)
  } catch {
    /* not fatal — see readStored */
  }
}

/** Pull `?token=...` out of the URL, remember it, and scrub it from the
 * address bar so the secret isn't left in history or copied when the page
 * URL is shared. */
export function captureTokenFromUrl(): string | null {
  const params = new URLSearchParams(window.location.search)
  const token = params.get(TOKEN_PARAM)
  if (!token) return readStored()

  write(token)
  params.delete(TOKEN_PARAM)
  const query = params.toString()
  window.history.replaceState(
    null,
    '',
    window.location.pathname + (query ? `?${query}` : '') + window.location.hash,
  )
  return token
}

export function getToken(): string | null {
  return readStored()
}

export function clearToken(): void {
  try {
    window.localStorage.removeItem(STORAGE_KEY)
  } catch {
    /* not fatal — see readStored */
  }
}
