import { apiRequest } from './client'
import type { Task, TaskCreateInput, TaskUpdateInput } from '../types'

export function fetchTasks(): Promise<Task[]> {
  return apiRequest<Task[]>('/api/tasks')
}

export function createTask(input: TaskCreateInput): Promise<Task> {
  return apiRequest<Task>('/api/tasks', {
    method: 'POST',
    body: JSON.stringify(input),
  })
}

export function updateTask(id: number, input: TaskUpdateInput): Promise<Task> {
  return apiRequest<Task>(`/api/tasks/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(input),
  })
}

export function deleteTask(id: number): Promise<void> {
  return apiRequest<void>(`/api/tasks/${id}`, { method: 'DELETE' })
}
