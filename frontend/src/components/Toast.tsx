import type { ToastItem } from '../hooks/useToasts'
import styles from './Toast.module.css'

interface ToastProps {
  toast: ToastItem
  onDismiss: (id: number) => void
}

const ICONS: Record<ToastItem['kind'], string> = {
  success: '✓',
  error: '!',
  info: 'i',
}

export function Toast({ toast, onDismiss }: ToastProps) {
  return (
    <div className={`${styles.toast} ${styles[toast.kind]}`} role="status">
      <span className={styles.icon} aria-hidden="true">
        {ICONS[toast.kind]}
      </span>
      <p className={styles.message}>{toast.message}</p>
      <button
        type="button"
        className={styles.dismiss}
        onClick={() => onDismiss(toast.id)}
        aria-label="Dismiss notification"
      >
        ×
      </button>
    </div>
  )
}
