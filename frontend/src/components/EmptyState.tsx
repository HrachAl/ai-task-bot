import styles from './EmptyState.module.css'

interface EmptyStateProps {
  title: string
  description?: string
  compact?: boolean
}

export function EmptyState({ title, description, compact }: EmptyStateProps) {
  return (
    <div className={`${styles.wrapper} ${compact ? styles.compact : ''}`}>
      <div className={styles.icon} aria-hidden="true">
        <InboxIcon />
      </div>
      <p className={styles.title}>{title}</p>
      {description && <p className={styles.description}>{description}</p>}
    </div>
  )
}

function InboxIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M4 12h4l1.5 3h5L16 12h4M5 12l1.6-6.4A2 2 0 0 1 8.53 4h6.94a2 2 0 0 1 1.93 1.6L19 12v6a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2v-6Z"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
    </svg>
  )
}
