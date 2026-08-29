import { forwardRef, type HTMLAttributes, type KeyboardEvent } from 'react'
import { useDraggable } from '@dnd-kit/core'
import type { Task, TaskStatus } from '../types'
import { formatRelativeDate } from '../utils/date'
import { StatusBadge } from './StatusBadge'
import styles from './TaskCard.module.css'

const ACCENT_CLASS: Record<TaskStatus, string> = {
  pending: styles.pending,
  in_progress: styles.progress,
  completed: styles.completed,
}

interface TaskCardViewProps extends HTMLAttributes<HTMLDivElement> {
  task: Task
  dragging?: boolean
  elevated?: boolean
  entering?: boolean
}

/** Pure presentational card markup, with no drag behavior attached — reused
 * by both the draggable `TaskCard` and the floating `DragOverlay` copy. */
export const TaskCardView = forwardRef<HTMLDivElement, TaskCardViewProps>(function TaskCardView(
  { task, dragging, elevated, entering, className, ...rest },
  ref,
) {
  const classes = [
    styles.card,
    ACCENT_CLASS[task.status],
    dragging ? styles.dragging : '',
    elevated ? styles.elevated : '',
    entering ? styles.entering : '',
    className ?? '',
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <div ref={ref} className={classes} {...rest}>
      <div className={styles.headerRow}>
        <StatusBadge status={task.status} />
        <span className={styles.taskId}>#{task.id}</span>
      </div>
      <p className={styles.title}>{task.title}</p>
      {task.description && <p className={styles.description}>{task.description}</p>}
      <div className={styles.footerRow}>
        <span className={styles.author}>
          <AuthorIcon />
          User #{task.user_id}
        </span>
        <span className={styles.date}>{formatRelativeDate(task.created_at)}</span>
      </div>
    </div>
  )
})

interface TaskCardProps {
  task: Task
  onOpen: (task: Task) => void
  isNew?: boolean
  onEntered?: (id: number) => void
}

export function TaskCard({ task, onOpen, isNew, onEntered }: TaskCardProps) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: task.id,
    data: { task },
  })

  function openFromKeyboard(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === 'Enter') onOpen(task)
  }

  return (
    <TaskCardView
      ref={setNodeRef}
      task={task}
      dragging={isDragging}
      entering={isNew}
      onAnimationEnd={() => onEntered?.(task.id)}
      onClick={() => onOpen(task)}
      onKeyDown={openFromKeyboard}
      {...listeners}
      {...attributes}
    />
  )
}

function AuthorIcon() {
  return (
    <svg width="11" height="11" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <circle cx="8" cy="5.5" r="2.5" stroke="currentColor" strokeWidth="1.3" />
      <path
        d="M3 13c0-2.5 2.2-4 5-4s5 1.5 5 4"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinecap="round"
      />
    </svg>
  )
}
