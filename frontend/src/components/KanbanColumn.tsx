import { useDroppable } from '@dnd-kit/core'
import { STATUS_LABELS, type Task, type TaskStatus } from '../types'
import { EmptyState } from './EmptyState'
import { TaskCard } from './TaskCard'
import styles from './KanbanColumn.module.css'

interface KanbanColumnProps {
  status: TaskStatus
  tasks: Task[]
  onOpenTask: (task: Task) => void
  newTaskIds: Set<number>
  onTaskEntered: (id: number) => void
}

const ACCENT_CLASS: Record<TaskStatus, string> = {
  pending: styles.pending,
  in_progress: styles.progress,
  completed: styles.completed,
}

export function KanbanColumn({
  status,
  tasks,
  onOpenTask,
  newTaskIds,
  onTaskEntered,
}: KanbanColumnProps) {
  const { setNodeRef, isOver } = useDroppable({ id: status })

  return (
    <section
      className={`${styles.column} ${ACCENT_CLASS[status]}`}
      aria-label={`${STATUS_LABELS[status]} column`}
    >
      <header className={styles.header}>
        <div className={styles.headerLeft}>
          <span className={styles.accentDot} aria-hidden="true" />
          <h2 className={styles.title}>{STATUS_LABELS[status]}</h2>
        </div>
        <span className={styles.count}>{tasks.length}</span>
      </header>

      <div ref={setNodeRef} className={`${styles.dropZone} ${isOver ? styles.over : ''}`}>
        {tasks.length === 0 ? (
          <div className={styles.emptyDropZone}>
            <EmptyState compact title="No tasks" description="Drag a task here, or create one" />
          </div>
        ) : (
          <div className={styles.list}>
            {tasks.map((task) => (
              <TaskCard
                key={task.id}
                task={task}
                onOpen={onOpenTask}
                isNew={newTaskIds.has(task.id)}
                onEntered={onTaskEntered}
              />
            ))}
          </div>
        )}
      </div>
    </section>
  )
}
