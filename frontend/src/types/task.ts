export type TaskStatus = 'pending' | 'in_progress' | 'completed'

export interface Task {
  id: number
  user_id: number
  title: string
  description: string | null
  status: TaskStatus
  created_at: string
  updated_at: string
}

export interface TaskCreateInput {
  title: string
  description?: string
}

export interface TaskUpdateInput {
  title?: string
  description?: string
  status?: TaskStatus
}

export const TASK_STATUSES: TaskStatus[] = ['pending', 'in_progress', 'completed']

export const STATUS_LABELS: Record<TaskStatus, string> = {
  pending: 'Pending',
  in_progress: 'In Progress',
  completed: 'Completed',
}
