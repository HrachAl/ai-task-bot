import { useEffect, useRef, useState } from 'react'
import { getToken } from '../auth'
import type { ConnectionStatus, Task, TaskEvent } from '../types'

const INITIAL_RECONNECT_DELAY_MS = 1000
const MAX_RECONNECT_DELAY_MS = 15000

function wsUrl(): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  // A browser can't set headers on a WebSocket handshake, so the token goes
  // in the query string — the server only ever streams this user's events.
  const token = getToken()
  const query = token ? `?token=${encodeURIComponent(token)}` : ''
  return `${protocol}//${window.location.host}/ws/tasks${query}`
}

/** Keeps a WebSocket connection to /ws/tasks alive, reconnecting with
 * exponential backoff on drop. task_created/task_updated events go to
 * `onTask`, which is expected to upsert-by-id so events can never produce a
 * duplicate card; task_deleted events go to `onTaskDeleted`. Both are
 * idempotent, so an echo of a change this client made itself is harmless. */
export function useTaskSocket(
  onTask: (task: Task) => void,
  onTaskDeleted: (id: number) => void,
): ConnectionStatus {
  const [status, setStatus] = useState<ConnectionStatus>('connecting')
  const onTaskRef = useRef(onTask)
  onTaskRef.current = onTask
  const onTaskDeletedRef = useRef(onTaskDeleted)
  onTaskDeletedRef.current = onTaskDeleted

  useEffect(() => {
    let socket: WebSocket | null = null
    let reconnectTimer: number | undefined
    let reconnectDelay = INITIAL_RECONNECT_DELAY_MS
    let cleanedUp = false

    function connect() {
      setStatus('connecting')
      socket = new WebSocket(wsUrl())

      socket.onopen = () => {
        reconnectDelay = INITIAL_RECONNECT_DELAY_MS
        setStatus('open')
      }

      socket.onmessage = (event) => {
        try {
          const parsed = JSON.parse(event.data as string) as TaskEvent
          if (parsed.type === 'task_created' || parsed.type === 'task_updated') {
            onTaskRef.current(parsed.task)
          } else if (parsed.type === 'task_deleted') {
            onTaskDeletedRef.current(parsed.task.id)
          }
        } catch {
          // Malformed frame — ignore rather than crash the UI.
        }
      }

      socket.onclose = () => {
        setStatus('closed')
        if (cleanedUp) return
        reconnectTimer = window.setTimeout(connect, reconnectDelay)
        reconnectDelay = Math.min(reconnectDelay * 2, MAX_RECONNECT_DELAY_MS)
      }

      socket.onerror = () => {
        socket?.close()
      }
    }

    connect()

    return () => {
      cleanedUp = true
      if (reconnectTimer !== undefined) window.clearTimeout(reconnectTimer)
      socket?.close()
    }
  }, [])

  return status
}
