import { STATUS_LABELS, type TaskStatus } from '../types'
import styles from './StatusBadge.module.css'

const CLASS_BY_STATUS: Record<TaskStatus, string> = {
  pending: styles.pending,
  in_progress: styles.progress,
  completed: styles.completed,
}

export function StatusBadge({ status }: { status: TaskStatus }) {
  return (
    <span className={`${styles.badge} ${CLASS_BY_STATUS[status]}`}>
      <span className={styles.dot} aria-hidden="true" />
      {STATUS_LABELS[status]}
    </span>
  )
}
