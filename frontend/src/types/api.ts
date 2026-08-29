/** Shape of FastAPI's error responses (both our custom handlers and the
 * default 422 validation errors use this `{ detail }` envelope). */
export interface ApiErrorBody {
  detail?: string | { msg: string; loc?: (string | number)[] }[]
}
