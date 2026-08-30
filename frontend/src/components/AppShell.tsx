import type { ReactNode } from 'react'
import type { Theme } from '../hooks/useTheme'
import type { ConnectionStatus, Me } from '../types'
import { Header } from './Header'
import { ToastContainer } from './ToastContainer'
import styles from './AppShell.module.css'

interface AppShellProps {
  taskCount: number
  connectionStatus: ConnectionStatus
  onRefresh: () => void
  isRefreshing: boolean
  theme: Theme
  onToggleTheme: () => void
  user: Me
  onSignOut: () => void
  children: ReactNode
}

export function AppShell({
  taskCount,
  connectionStatus,
  onRefresh,
  isRefreshing,
  theme,
  onToggleTheme,
  user,
  onSignOut,
  children,
}: AppShellProps) {
  return (
    <div className={styles.shell}>
      <Header
        taskCount={taskCount}
        connectionStatus={connectionStatus}
        onRefresh={onRefresh}
        isRefreshing={isRefreshing}
        theme={theme}
        onToggleTheme={onToggleTheme}
        user={user}
        onSignOut={onSignOut}
      />
      <main className={styles.main}>{children}</main>
      <ToastContainer />
    </div>
  )
}
