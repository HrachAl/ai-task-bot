/** Dashboard access, without a registration form.
 *
 * There is no sign-up and no password anywhere in this project: the bot
 * hands each Telegram user a link containing their personal token
 * (`/dashboard`), the token is exchanged for that user's board, and it is
 * kept in localStorage so the link only has to be followed once per device.
 */

const STORAGE_KEY = 'ai-task-bot-token'
const TOKEN_PARAM = 'token'

function readStored(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY)
  } catch {
    // Private-mode browsers can throw on storage access — the session still
    // works for as long as the tab lives, it just won't be remembered.
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

/** Pull `?token=...` out of the URL on first load, remember it, and scrub it
 * from the address bar so the secret isn't left sitting in browser history
 * or copied along when the user shares the page URL. */
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
