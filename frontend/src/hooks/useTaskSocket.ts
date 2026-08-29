import { useEffect, useRef, useState } from 'react'
import type { ConnectionStatus, Task, TaskEvent } from '../types'

const INITIAL_RECONNECT_DELAY_MS = 1000
const MAX_RECONNECT_DELAY_MS = 15000

function wsUrl(): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/ws/tasks`
}

/** Keeps a WebSocket connection to /ws/tasks alive, reconnecting with
 * exponential backoff on drop. Every task_created/task_updated event is
 * handed to `onTask`, which is expected to upsert-by-id so events can never
 * produce a duplicate card. */
export function useTaskSocket(onTask: (task: Task) => void): ConnectionStatus {
  const [status, setStatus] = useState<ConnectionStatus>('connecting')
  const onTaskRef = useRef(onTask)
  onTaskRef.current = onTask

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
