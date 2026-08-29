import { useState } from 'react'
import { ApiError } from '../api/client'
import { useToasts } from '../hooks/useToasts'
import { STATUS_LABELS, TASK_STATUSES, type Task, type TaskStatus } from '../types'
import { formatFullDate } from '../utils/date'
import buttons from '../styles/buttons.module.css'
import { Modal } from './Modal'
import { StatusBadge } from './StatusBadge'
import styles from './TaskDetails.module.css'

interface TaskDetailsProps {
  task: Task
  onClose: () => void
  onStatusChange: (id: number, status: TaskStatus) => Promise<void>
  onDelete: (id: number) => Promise<void>
}

export function TaskDetails({ task, onClose, onStatusChange, onDelete }: TaskDetailsProps) {
  const [pendingStatus, setPendingStatus] = useState<TaskStatus | null>(null)
  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const { showToast } = useToasts()

  async function handleStatusClick(status: TaskStatus) {
    if (status === task.status || pendingStatus) return
    setPendingStatus(status)
    try {
      await onStatusChange(task.id, status)
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : 'Failed to update status.', 'error')
    } finally {
      setPendingStatus(null)
    }
  }

  async function handleDelete() {
    setIsDeleting(true)
    try {
      await onDelete(task.id)
      showToast('Task deleted', 'success')
      onClose()
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : 'Failed to delete task.', 'error')
      setIsDeleting(false)
      setConfirmingDelete(false)
    }
  }

  return (
    <Modal titleId="task-details-title" title={`Task #${task.id}`} onClose={onClose} width={520}>
      <div className={styles.body}>
        <div className={styles.titleRow}>
          <h3 className={styles.title}>{task.title}</h3>
          <StatusBadge status={task.status} />
        </div>

        {task.description ? (
          <p className={styles.description}>{task.description}</p>
        ) : (
          <p className={styles.noDescription}>No description provided.</p>
        )}

        <dl className={styles.meta}>
          <div className={styles.metaItem}>
            <dt className={styles.metaLabel}>Task ID</dt>
            <dd className={styles.metaValue}>#{task.id}</dd>
          </div>
          <div className={styles.metaItem}>
            <dt className={styles.metaLabel}>Created</dt>
            <dd className={styles.metaValue}>{formatFullDate(task.created_at)}</dd>
          </div>
          <div className={styles.metaItem}>
            <dt className={styles.metaLabel}>Created by</dt>
            <dd className={styles.metaValue}>User #{task.user_id}</dd>
          </div>
        </dl>

        <div className={styles.section}>
          <span className={styles.sectionLabel}>Change status</span>
          <div className={styles.statusGroup} role="group" aria-label="Change task status">
            {TASK_STATUSES.map((status) => (
              <button
                key={status}
                type="button"
                className={`${styles.statusOption} ${status === task.status ? styles.active : ''}`}
                onClick={() => handleStatusClick(status)}
                disabled={pendingStatus !== null}
                aria-pressed={status === task.status}
              >
                {pendingStatus === status ? 'Updating…' : STATUS_LABELS[status]}
              </button>
            ))}
          </div>
        </div>

        <div className={styles.footer}>
          {confirmingDelete ? (
            <div className={styles.confirmRow}>
              <span className={styles.confirmText}>Delete this task permanently?</span>
              <div className={styles.confirmActions}>
                <button
                  type="button"
                  className={buttons.secondary}
                  onClick={() => setConfirmingDelete(false)}
                  disabled={isDeleting}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className={buttons.dangerSolid}
                  onClick={handleDelete}
                  disabled={isDeleting}
                >
                  {isDeleting ? 'Deleting…' : 'Confirm Delete'}
                </button>
              </div>
            </div>
          ) : (
            <button
              type="button"
              className={buttons.danger}
              onClick={() => setConfirmingDelete(true)}
            >
              Delete Task
            </button>
          )}
        </div>
      </div>
    </Modal>
  )
}
