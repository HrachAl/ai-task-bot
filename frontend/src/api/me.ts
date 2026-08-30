import { apiRequest } from './client'
import type { Me } from '../types'

export function fetchMe(): Promise<Me> {
  return apiRequest<Me>('/api/me')
}
