import type { Task } from './task'

export type TaskEventType = 'task_created' | 'task_updated' | 'task_deleted'

/** Every event carries the full task, deletions included. */
export interface TaskEvent {
  type: TaskEventType
  task: Task
}

export type ConnectionStatus = 'connecting' | 'open' | 'closed'
