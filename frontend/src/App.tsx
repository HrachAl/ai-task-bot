import { useCallback, useState } from 'react'
import { ApiError } from './api/client'
import { AppShell } from './components/AppShell'
import { EmptyState } from './components/EmptyState'
import { KanbanBoard } from './components/KanbanBoard'
import { LoadingState } from './components/LoadingState'
import { TaskDetails } from './components/TaskDetails'
import { TaskModal } from './components/TaskModal'
import { useTasks } from './hooks/useTasks'
import { useTaskSocket } from './hooks/useTaskSocket'
import { useTheme } from './hooks/useTheme'
import { useToasts } from './hooks/useToasts'
import type { TaskStatus } from './types'
import buttons from './styles/buttons.module.css'
import styles from './App.module.css'

export function App() {
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
  const [theme, toggleTheme] = useTheme()

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
      onToggleTheme={toggleTheme}
    >
      <div className={styles.page}>
        <div className={styles.pageHeader}>
          <div>
            <h1 className={styles.title}>My Tasks</h1>
            <p className={styles.subtitle}>
              Everything captured from Telegram and the dashboard, in one board.
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
