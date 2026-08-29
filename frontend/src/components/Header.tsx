import type { Theme } from '../hooks/useTheme'
import type { ConnectionStatus } from '../types'
import styles from './Header.module.css'

interface HeaderProps {
  taskCount: number
  connectionStatus: ConnectionStatus
  onRefresh: () => void
  isRefreshing: boolean
  theme: Theme
  onToggleTheme: () => void
}

export function Header({
  taskCount,
  connectionStatus,
  onRefresh,
  isRefreshing,
  theme,
  onToggleTheme,
}: HeaderProps) {
  return (
    <header className={styles.header}>
      <div className={styles.left}>
        <div className={styles.logo}>
          <span className={styles.logoMark} aria-hidden="true">
            <BotIcon />
          </span>
          <span className={styles.logoText}>AI Task Bot</span>
        </div>
        <nav className={styles.nav} aria-label="Primary">
          <span className={styles.navItem} aria-current="page">
            Tasks
          </span>
        </nav>
      </div>

      <div className={styles.right}>
        <span className={styles.taskCount}>
          {taskCount} {taskCount === 1 ? 'task' : 'tasks'}
        </span>

        <ConnectionIndicator status={connectionStatus} />

        <button
          type="button"
          className={styles.iconButton}
          onClick={onToggleTheme}
          aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
          title={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
        >
          {theme === 'dark' ? <SunIcon /> : <MoonIcon />}
        </button>

        <button
          type="button"
          className={styles.iconButton}
          onClick={onRefresh}
          disabled={isRefreshing}
          aria-label="Refresh tasks"
          title="Refresh"
        >
          <RefreshIcon spinning={isRefreshing} />
        </button>

        <div className={styles.userArea} aria-hidden="true">
          <span className={styles.avatar}>U</span>
        </div>
      </div>
    </header>
  )
}

const STATUS_TEXT: Record<ConnectionStatus, string> = {
  open: 'Live',
  connecting: 'Connecting…',
  closed: 'Reconnecting…',
}

function ConnectionIndicator({ status }: { status: ConnectionStatus }) {
  return (
    <span className={`${styles.connection} ${styles[status]}`} role="status">
      <span className={styles.connectionDot} aria-hidden="true" />
      {STATUS_TEXT[status]}
    </span>
  )
}

function BotIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <rect x="3" y="6" width="10" height="7" rx="2.5" stroke="white" strokeWidth="1.4" />
      <path d="M8 6V3.5" stroke="white" strokeWidth="1.4" strokeLinecap="round" />
      <circle cx="8" cy="2.5" r="1" fill="white" />
      <circle cx="6" cy="9.5" r="1" fill="white" />
      <circle cx="10" cy="9.5" r="1" fill="white" />
    </svg>
  )
}

function SunIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <circle cx="8" cy="8" r="3.2" stroke="currentColor" strokeWidth="1.4" />
      <path
        d="M8 1.5v1.6M8 12.9v1.6M14.5 8h-1.6M3.1 8H1.5M12.5 3.5l-1.1 1.1M4.6 11.4l-1.1 1.1M12.5 12.5l-1.1-1.1M4.6 4.6L3.5 3.5"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
      />
    </svg>
  )
}

function MoonIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path
        d="M13.5 9.8A5.7 5.7 0 0 1 6.2 2.5a5.7 5.7 0 1 0 7.3 7.3Z"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function RefreshIcon({ spinning }: { spinning: boolean }) {
  return (
    <svg
      width="15"
      height="15"
      viewBox="0 0 16 16"
      fill="none"
      aria-hidden="true"
      className={spinning ? styles.spin : ''}
    >
      <path
        d="M13.5 8a5.5 5.5 0 1 1-1.7-3.98M13.5 2.5v3.5H10"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}
