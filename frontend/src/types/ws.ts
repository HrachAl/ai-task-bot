import type { Task } from './task'

export type TaskEventType = 'task_created' | 'task_updated'

export interface TaskEvent {
  type: TaskEventType
  task: Task
}

export type ConnectionStatus = 'connecting' | 'open' | 'closed'
