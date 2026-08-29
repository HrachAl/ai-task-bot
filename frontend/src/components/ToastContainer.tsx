import { useToasts } from '../hooks/useToasts'
import { Toast } from './Toast'
import styles from './ToastContainer.module.css'

export function ToastContainer() {
  const { toasts, dismissToast } = useToasts()

  if (toasts.length === 0) return null

  return (
    <div className={styles.container} aria-live="polite">
      {toasts.map((toast) => (
        <Toast key={toast.id} toast={toast} onDismiss={dismissToast} />
      ))}
    </div>
  )
}
