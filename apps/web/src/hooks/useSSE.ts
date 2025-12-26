import { useEffect, useRef, useState } from 'react'

interface SSEOptions {
  onMessage?: (data: any) => void
  onError?: (error: Event) => void
  onOpen?: () => void
}

export function useSSE(url: string | null, options: SSEOptions = {}) {
  const [isConnected, setIsConnected] = useState(false)
  const [lastMessage, setLastMessage] = useState<any>(null)
  const eventSourceRef = useRef<EventSource | null>(null)

  useEffect(() => {
    if (!url) {
      return
    }

    const eventSource = new EventSource(url)
    eventSourceRef.current = eventSource

    eventSource.onopen = () => {
      setIsConnected(true)
      options.onOpen?.()
    }

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        setLastMessage(data)
        options.onMessage?.(data)
      } catch {
        console.error('Failed to parse SSE message:', event.data)
      }
    }

    eventSource.onerror = (error) => {
      setIsConnected(false)
      options.onError?.(error)
    }

    return () => {
      eventSource.close()
      eventSourceRef.current = null
      setIsConnected(false)
    }
  }, [url])

  const close = () => {
    eventSourceRef.current?.close()
    setIsConnected(false)
  }

  return { isConnected, lastMessage, close }
}
