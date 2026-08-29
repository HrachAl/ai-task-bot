import { useState, type FormEvent } from 'react'
import { ApiError } from '../api/client'
import { useToasts } from '../hooks/useToasts'
import type { Task, TaskCreateInput } from '../types'
import buttons from '../styles/buttons.module.css'
import form from '../styles/form.module.css'
import { Modal } from './Modal'
import styles from './TaskModal.module.css'

interface TaskModalProps {
  onClose: () => void
  onCreate: (input: TaskCreateInput) => Promise<Task>
}

const TITLE_MAX = 500
const DESCRIPTION_MAX = 5000

export function TaskModal({ onClose, onCreate }: TaskModalProps) {
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [fieldError, setFieldError] = useState<string | null>(null)
  const { showToast } = useToasts()

  const trimmedTitle = title.trim()
  const isValid = trimmedTitle.length > 0 && trimmedTitle.length <= TITLE_MAX

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (!isValid || isSubmitting) return

    setIsSubmitting(true)
    setFieldError(null)
    try {
      await onCreate({
        title: trimmedTitle,
        description: description.trim() || undefined,
      })
      showToast('Task created', 'success')
      onClose()
    } catch (err) {
      setFieldError(err instanceof ApiError ? err.message : 'Failed to create task.')
      setIsSubmitting(false)
    }
  }

  return (
    <Modal titleId="new-task-title" title="New Task" onClose={onClose}>
      <form className={styles.form} onSubmit={handleSubmit}>
        <div className={form.field}>
          <label htmlFor="task-title" className={form.label}>
            Title
          </label>
          <input
            id="task-title"
            className={form.input}
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="e.g. Write the quarterly report"
            maxLength={TITLE_MAX}
            autoFocus
            required
          />
        </div>

        <div className={form.field}>
          <label htmlFor="task-description" className={form.label}>
            Description <span className={form.optional}>(optional)</span>
          </label>
          <textarea
            id="task-description"
            className={form.textarea}
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder="Add more detail..."
            maxLength={DESCRIPTION_MAX}
            rows={4}
          />
        </div>

        {fieldError && (
          <p role="alert" className={form.error}>
            {fieldError}
          </p>
        )}

        <div className={styles.actions}>
          <button
            type="button"
            className={buttons.secondary}
            onClick={onClose}
            disabled={isSubmitting}
          >
            Cancel
          </button>
          <button type="submit" className={buttons.primary} disabled={!isValid || isSubmitting}>
            {isSubmitting ? 'Creating…' : 'Create Task'}
          </button>
        </div>
      </form>
    </Modal>
  )
}
