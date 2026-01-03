import { useEffect, useRef, useState, useCallback } from 'react'

// Exponential backoff constants
const INITIAL_RETRY_DELAY = 1000  // 1 second
const MAX_RETRY_DELAY = 30000     // 30 seconds
const BACKOFF_MULTIPLIER = 2

interface SSEOptions {
  onMessage?: (data: unknown) => void
  onError?: (error: Event) => void
  onOpen?: () => void
  onReconnect?: (attempt: number, delay: number) => void
  /** Automatically reconnect on connection loss (default: true) */
  autoReconnect?: boolean
  /** Custom event types to listen for (in addition to 'message') */
  eventTypes?: string[]
}

interface SSEState {
  isConnected: boolean
  lastMessage: unknown
  retryCount: number
  retryDelay: number | null
}

export function useSSE(url: string | null, options: SSEOptions = {}) {
  const {
    onMessage,
    onError,
    onOpen,
    onReconnect,
    autoReconnect = true,
    eventTypes = [],
  } = options

  const [state, setState] = useState<SSEState>({
    isConnected: false,
    lastMessage: null,
    retryCount: 0,
    retryDelay: null,
  })

  const eventSourceRef = useRef<EventSource | null>(null)
  const retryTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const retryDelayRef = useRef<number>(INITIAL_RETRY_DELAY)
  const countdownIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const urlRef = useRef<string | null>(null)

  // Store callbacks in refs to avoid reconnection on callback changes
  const callbacksRef = useRef({ onMessage, onError, onOpen, onReconnect })
  useEffect(() => {
    callbacksRef.current = { onMessage, onError, onOpen, onReconnect }
  }, [onMessage, onError, onOpen, onReconnect])

  const clearTimers = useCallback(() => {
    if (retryTimeoutRef.current) {
      clearTimeout(retryTimeoutRef.current)
      retryTimeoutRef.current = null
    }
    if (countdownIntervalRef.current) {
      clearInterval(countdownIntervalRef.current)
      countdownIntervalRef.current = null
    }
  }, [])

  const connect = useCallback(() => {
    const currentUrl = urlRef.current
    if (!currentUrl) return

    clearTimers()

    // Close existing connection
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
    }

    const eventSource = new EventSource(currentUrl)
    eventSourceRef.current = eventSource

    eventSource.onopen = () => {
      setState(prev => ({
        ...prev,
        isConnected: true,
        retryCount: 0,
        retryDelay: null,
      }))
      retryDelayRef.current = INITIAL_RETRY_DELAY // Reset on success
      callbacksRef.current.onOpen?.()
    }

    // Default message handler
    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        setState(prev => ({ ...prev, lastMessage: data }))
        callbacksRef.current.onMessage?.(data)
      } catch {
        console.error('[useSSE] Failed to parse SSE message:', event.data)
      }
    }

    // Register custom event type handlers
    eventTypes.forEach(eventType => {
      eventSource.addEventListener(eventType, (event) => {
        try {
          const data = JSON.parse((event as MessageEvent).data)
          setState(prev => ({ ...prev, lastMessage: data }))
          callbacksRef.current.onMessage?.(data)
        } catch {
          console.error(`[useSSE] Failed to parse SSE ${eventType} event:`, (event as MessageEvent).data)
        }
      })
    })

    eventSource.onerror = (error) => {
      eventSource.close()
      setState(prev => ({ ...prev, isConnected: false }))
      callbacksRef.current.onError?.(error)

      // Auto-reconnect with exponential backoff
      if (autoReconnect && urlRef.current) {
        const currentDelay = retryDelayRef.current
        const nextDelay = Math.min(currentDelay * BACKOFF_MULTIPLIER, MAX_RETRY_DELAY)

        setState(prev => ({
          ...prev,
          retryCount: prev.retryCount + 1,
          retryDelay: Math.ceil(currentDelay / 1000),
        }))

        callbacksRef.current.onReconnect?.(
          state.retryCount + 1,
          Math.ceil(currentDelay / 1000)
        )

        // Start countdown display
        let countdown = Math.ceil(currentDelay / 1000)
        countdownIntervalRef.current = setInterval(() => {
          countdown -= 1
          if (countdown > 0) {
            setState(prev => ({ ...prev, retryDelay: countdown }))
          }
        }, 1000)

        // Schedule reconnection
        retryTimeoutRef.current = setTimeout(() => {
          clearTimers()
          setState(prev => ({ ...prev, retryDelay: null }))
          connect()
        }, currentDelay)

        retryDelayRef.current = nextDelay
      }
    }
  }, [autoReconnect, clearTimers, eventTypes, state.retryCount])

  // Handle URL changes
  useEffect(() => {
    urlRef.current = url

    if (!url) {
      // Close connection when URL becomes null
      clearTimers()
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
        eventSourceRef.current = null
      }
      setState({
        isConnected: false,
        lastMessage: null,
        retryCount: 0,
        retryDelay: null,
      })
      return
    }

    // Connect to new URL
    connect()

    return () => {
      clearTimers()
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
        eventSourceRef.current = null
      }
      setState(prev => ({ ...prev, isConnected: false }))
    }
  }, [url, connect, clearTimers])

  const close = useCallback(() => {
    clearTimers()
    urlRef.current = null
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }
    setState({
      isConnected: false,
      lastMessage: null,
      retryCount: 0,
      retryDelay: null,
    })
  }, [clearTimers])

  const reconnect = useCallback(() => {
    if (urlRef.current) {
      retryDelayRef.current = INITIAL_RETRY_DELAY
      connect()
    }
  }, [connect])

  return {
    isConnected: state.isConnected,
    lastMessage: state.lastMessage,
    retryCount: state.retryCount,
    retryDelay: state.retryDelay,
    close,
    reconnect,
  }
}
