/** The signed-in user, as returned by GET /api/me. Identity comes from
 * Telegram — there is no separate account to create. */
export interface Me {
  id: number
  telegram_id: number
  username: string | null
  created_at: string
  updated_at: string
  access_token: string
  dashboard_url: string
}
