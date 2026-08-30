import { useCallback, useEffect, useState } from 'react'
import { ApiError } from '../api/client'
import { createTask, deleteTask, fetchTasks, updateTask } from '../api/tasks'
import type { Task, TaskCreateInput, TaskStatus } from '../types'

function toMessage(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.message : fallback
}

export function useTasks() {
  const [tasks, setTasks] = useState<Task[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  // Ids inserted after the initial load (via the dashboard form or a
  // WebSocket task_created event) — lets the board play a one-time entrance
  // animation for genuinely new cards without replaying it on every render
  // or on the initial page-load batch.
  const [newTaskIds, setNewTaskIds] = useState<Set<number>>(new Set())

  const refresh = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const data = await fetchTasks()
      setTasks(data)
    } catch (err) {
      setError(toMessage(err, 'Failed to load tasks.'))
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  /** Insert-or-replace by id: the single merge point for API responses and
   * WebSocket events, so a task can never appear twice. */
  const upsertTask = useCallback((task: Task) => {
    setTasks((current) => {
      const index = current.findIndex((item) => item.id === task.id)
      if (index === -1) {
        setNewTaskIds((ids) => new Set(ids).add(task.id))
        return [task, ...current]
      }
      const next = [...current]
      next[index] = task
      return next
    })
  }, [])

  /** Called once a card's entrance animation has played, so it doesn't
   * replay on later re-renders of the same task. */
  const clearNewTask = useCallback((id: number) => {
    setNewTaskIds((ids) => {
      if (!ids.has(id)) return ids
      const next = new Set(ids)
      next.delete(id)
      return next
    })
  }, [])

  /** Drop a card that no longer exists. Removing an id that is already gone
   * is a no-op, so a task_deleted echo of our own delete changes nothing. */
  const dropTask = useCallback((id: number) => {
    setTasks((current) => current.filter((task) => task.id !== id))
  }, [])

  const addTask = useCallback(
    async (input: TaskCreateInput): Promise<Task> => {
      const task = await createTask(input)
      upsertTask(task)
      return task
    },
    [upsertTask],
  )

  const changeStatus = useCallback(
    async (id: number, status: TaskStatus): Promise<void> => {
      let previous: Task[] = []
      setTasks((current) => {
        previous = current
        return current.map((task) => (task.id === id ? { ...task, status } : task))
      })
      try {
        const updated = await updateTask(id, { status })
        upsertTask(updated)
      } catch (err) {
        setTasks(previous)
        throw err
      }
    },
    [upsertTask],
  )

  const removeTask = useCallback(async (id: number): Promise<void> => {
    let previous: Task[] = []
    setTasks((current) => {
      previous = current
      return current.filter((task) => task.id !== id)
    })
    try {
      await deleteTask(id)
    } catch (err) {
      setTasks(previous)
      throw err
    }
  }, [])

  return {
    tasks,
    isLoading,
    error,
    refresh,
    addTask,
    changeStatus,
    removeTask,
    upsertTask,
    dropTask,
    newTaskIds,
    clearNewTask,
  }
}

export type UseTasksResult = ReturnType<typeof useTasks>
