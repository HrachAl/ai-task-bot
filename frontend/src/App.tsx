import { useCallback, useState } from 'react'
import { ApiError } from './api/client'
import { AppShell } from './components/AppShell'
import { ConnectScreen } from './components/ConnectScreen'
import { EmptyState } from './components/EmptyState'
import { KanbanBoard } from './components/KanbanBoard'
import { LoadingState } from './components/LoadingState'
import { TaskDetails } from './components/TaskDetails'
import { TaskModal } from './components/TaskModal'
import { useSession } from './hooks/useSession'
import { useTasks } from './hooks/useTasks'
import { useTaskSocket } from './hooks/useTaskSocket'
import { useTheme, type Theme } from './hooks/useTheme'
import { useToasts } from './hooks/useToasts'
import type { Me, TaskStatus } from './types'
import buttons from './styles/buttons.module.css'
import styles from './App.module.css'

/** Session gate.
 *
 * The board is per-user, so nothing is fetched until we know *which* user is
 * looking. Identity comes from the personal link the Telegram bot hands out
 * — there is no login form to fall back to, which is why an unresolved
 * session renders the connect instructions rather than an empty board.
 */
export function App() {
  const [theme, toggleTheme] = useTheme()
  const { state, retry, signOut } = useSession()

  if (state.status === 'loading') {
    return (
      <div className={styles.bootScreen}>
        <span className={styles.bootSpinner} aria-hidden="true" />
        <p className={styles.bootText}>Loading your board…</p>
      </div>
    )
  }

  if (state.status === 'anonymous') {
    return <ConnectScreen reason={state.reason} onRetry={retry} />
  }

  if (state.status === 'error') {
    return (
      <div className={styles.bootScreen}>
        <p className={styles.bootText}>{state.message}</p>
        <button type="button" className={buttons.secondary} onClick={retry}>
          Try again
        </button>
      </div>
    )
  }

  return (
    <Dashboard
      user={state.user}
      theme={theme}
      onToggleTheme={toggleTheme}
      onSignOut={signOut}
    />
  )
}

interface DashboardProps {
  user: Me
  theme: Theme
  onToggleTheme: () => void
  onSignOut: () => void
}

function Dashboard({ user, theme, onToggleTheme, onSignOut }: DashboardProps) {
  const {
    tasks,
    isLoading,
    error,
    refresh,
    addTask,
    changeStatus,
    removeTask,
    upsertTask,
    newTaskIds,
    clearNewTask,
  } = useTasks()
  const { showToast } = useToasts()
  const connectionStatus = useTaskSocket(upsertTask)

  const [isCreateOpen, setIsCreateOpen] = useState(false)
  const [selectedTaskId, setSelectedTaskId] = useState<number | null>(null)
  const [isRefreshing, setIsRefreshing] = useState(false)

  const selectedTask =
    selectedTaskId !== null ? (tasks.find((task) => task.id === selectedTaskId) ?? null) : null

  const handleRefresh = useCallback(async () => {
    setIsRefreshing(true)
    await refresh()
    setIsRefreshing(false)
  }, [refresh])

  // Drag-and-drop is fire-and-forget from the board's perspective — the
  // page owns turning a failed PATCH into a visible rollback notice.
  function handleBoardStatusChange(id: number, status: TaskStatus) {
    void changeStatus(id, status).catch((err) => {
      showToast(
        err instanceof ApiError ? err.message : "Couldn't update task — reverted.",
        'error',
      )
    })
  }

  return (
    <AppShell
      taskCount={tasks.length}
      connectionStatus={connectionStatus}
      onRefresh={handleRefresh}
      isRefreshing={isRefreshing}
      theme={theme}
      onToggleTheme={onToggleTheme}
      user={user}
      onSignOut={onSignOut}
    >
      <div className={styles.page}>
        <div className={styles.pageHeader}>
          <div>
            <h1 className={styles.title}>My Tasks</h1>
            <p className={styles.subtitle}>
              Everything you captured from Telegram and the dashboard, in one private board.
            </p>
          </div>
          <button
            type="button"
            className={buttons.primary}
            onClick={() => setIsCreateOpen(true)}
          >
            <PlusIcon />
            New Task
          </button>
        </div>

        {isLoading ? (
          <LoadingState />
        ) : error ? (
          <div className={styles.errorState}>
            <EmptyState title="Couldn't load tasks" description={error} />
            <button type="button" className={buttons.secondary} onClick={handleRefresh}>
              Try again
            </button>
          </div>
        ) : tasks.length === 0 ? (
          <EmptyState
            title="No tasks yet"
            description="Send a message to your Telegram bot, or create one here to get started."
          />
        ) : (
          <KanbanBoard
            tasks={tasks}
            onOpenTask={(task) => setSelectedTaskId(task.id)}
            onStatusChange={handleBoardStatusChange}
            newTaskIds={newTaskIds}
            onTaskEntered={clearNewTask}
          />
        )}
      </div>

      {isCreateOpen && <TaskModal onClose={() => setIsCreateOpen(false)} onCreate={addTask} />}

      {selectedTask && (
        <TaskDetails
          task={selectedTask}
          onClose={() => setSelectedTaskId(null)}
          onStatusChange={changeStatus}
          onDelete={removeTask}
        />
      )}
    </AppShell>
  )
}

function PlusIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path d="M8 3v10M3 8h10" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  )
}
