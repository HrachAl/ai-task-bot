import { useState } from 'react'
import {
  DndContext,
  DragOverlay,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from '@dnd-kit/core'
import { TASK_STATUSES, type Task, type TaskStatus } from '../types'
import { KanbanColumn } from './KanbanColumn'
import { TaskCardView } from './TaskCard'
import styles from './KanbanBoard.module.css'

interface KanbanBoardProps {
  tasks: Task[]
  onOpenTask: (task: Task) => void
  onStatusChange: (id: number, status: TaskStatus) => void
  newTaskIds: Set<number>
  onTaskEntered: (id: number) => void
}

function groupByStatus(tasks: Task[]): Record<TaskStatus, Task[]> {
  const grouped: Record<TaskStatus, Task[]> = { pending: [], in_progress: [], completed: [] }
  for (const task of tasks) grouped[task.status].push(task)
  return grouped
}

export function KanbanBoard({
  tasks,
  onOpenTask,
  onStatusChange,
  newTaskIds,
  onTaskEntered,
}: KanbanBoardProps) {
  const [activeTask, setActiveTask] = useState<Task | null>(null)

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
    useSensor(KeyboardSensor),
  )

  const grouped = groupByStatus(tasks)

  function handleDragStart(event: DragStartEvent) {
    const task = event.active.data.current?.task as Task | undefined
    setActiveTask(task ?? null)
  }

  function handleDragEnd(event: DragEndEvent) {
    setActiveTask(null)
    const { active, over } = event
    if (!over) return

    const task = active.data.current?.task as Task | undefined
    const newStatus = over.id as TaskStatus
    if (!task || task.status === newStatus) return

    onStatusChange(task.id, newStatus)
  }

  return (
    <DndContext
      sensors={sensors}
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
      onDragCancel={() => setActiveTask(null)}
    >
      <div className={styles.board}>
        {TASK_STATUSES.map((status) => (
          <KanbanColumn
            key={status}
            status={status}
            tasks={grouped[status]}
            onOpenTask={onOpenTask}
            newTaskIds={newTaskIds}
            onTaskEntered={onTaskEntered}
          />
        ))}
      </div>

      <DragOverlay dropAnimation={{ duration: 180, easing: 'cubic-bezier(0.2, 0.8, 0.2, 1)' }}>
        {activeTask ? (
          <div className={styles.overlayWrapper}>
            <TaskCardView task={activeTask} elevated />
          </div>
        ) : null}
      </DragOverlay>
    </DndContext>
  )
}
