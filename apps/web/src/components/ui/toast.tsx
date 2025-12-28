/**
 * Toast Notification System
 *
 * Provides toast notifications with UELR integration for error tracking.
 */

import { createContext, useContext, useState, useCallback, ReactNode } from 'react'
import { X, AlertCircle, CheckCircle, Info, ExternalLink } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useNavigate } from 'react-router-dom'

export type ToastType = 'success' | 'error' | 'info' | 'warning'

export interface Toast {
  id: string
  type: ToastType
  title: string
  message?: string
  correlationId?: string
  interactionId?: string
  duration?: number
}

interface ToastContextValue {
  toasts: Toast[]
  addToast: (toast: Omit<Toast, 'id'>) => string
  removeToast: (id: string) => void
  /** Show an error toast with UELR tracking link */
  showError: (title: string, message?: string, correlationId?: string, interactionId?: string) => void
  /** Show a success toast */
  showSuccess: (title: string, message?: string) => void
  /** Show an info toast */
  showInfo: (title: string, message?: string) => void
}

const ToastContext = createContext<ToastContextValue | null>(null)

export function useToast() {
  const context = useContext(ToastContext)
  if (!context) {
    throw new Error('useToast must be used within ToastProvider')
  }
  return context
}

const icons: Record<ToastType, typeof AlertCircle> = {
  success: CheckCircle,
  error: AlertCircle,
  info: Info,
  warning: AlertCircle,
}

const styles: Record<ToastType, string> = {
  success: 'border-green-500/30 bg-green-500/10',
  error: 'border-red-500/30 bg-red-500/10',
  info: 'border-blue-500/30 bg-blue-500/10',
  warning: 'border-yellow-500/30 bg-yellow-500/10',
}

const iconStyles: Record<ToastType, string> = {
  success: 'text-green-400',
  error: 'text-red-400',
  info: 'text-blue-400',
  warning: 'text-yellow-400',
}

function ToastItem({
  toast,
  onRemove,
}: {
  toast: Toast
  onRemove: () => void
}) {
  const navigate = useNavigate()
  const Icon = icons[toast.type]

  const handleOpenLogs = () => {
    // Navigate to logs page with correlation ID filter
    if (toast.interactionId) {
      navigate(`/logs?interaction=${toast.interactionId}`)
    } else if (toast.correlationId) {
      navigate(`/logs?correlation=${toast.correlationId}`)
    } else {
      navigate('/logs')
    }
    onRemove()
  }

  return (
    <div
      className={cn(
        'flex items-start gap-3 p-4 rounded-lg border shadow-lg backdrop-blur-sm',
        'animate-in slide-in-from-right duration-200',
        styles[toast.type]
      )}
    >
      <Icon className={cn('w-5 h-5 flex-shrink-0 mt-0.5', iconStyles[toast.type])} />
      <div className="flex-1 min-w-0">
        <p className="font-medium text-gray-200">{toast.title}</p>
        {toast.message && (
          <p className="text-sm text-gray-400 mt-1">{toast.message}</p>
        )}
        {(toast.correlationId || toast.interactionId) && (
          <div className="flex items-center gap-2 mt-2">
            <code className="text-[10px] px-1.5 py-0.5 bg-gray-800 rounded text-gray-500">
              {toast.correlationId?.slice(0, 16) || toast.interactionId?.slice(0, 16)}...
            </code>
            <button
              onClick={handleOpenLogs}
              className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1 transition-colors"
            >
              Open Logs
              <ExternalLink className="w-3 h-3" />
            </button>
          </div>
        )}
      </div>
      <button
        onClick={onRemove}
        className="text-gray-500 hover:text-gray-300 transition-colors"
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  )
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const addToast = useCallback((toast: Omit<Toast, 'id'>) => {
    const id = `toast-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`
    const newToast: Toast = { ...toast, id }

    setToasts((prev) => [...prev, newToast])

    // Auto-remove after duration
    const duration = toast.duration ?? (toast.type === 'error' ? 10000 : 5000)
    if (duration > 0) {
      setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== id))
      }, duration)
    }

    return id
  }, [])

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  const showError = useCallback(
    (title: string, message?: string, correlationId?: string, interactionId?: string) => {
      addToast({ type: 'error', title, message, correlationId, interactionId })
    },
    [addToast]
  )

  const showSuccess = useCallback(
    (title: string, message?: string) => {
      addToast({ type: 'success', title, message })
    },
    [addToast]
  )

  const showInfo = useCallback(
    (title: string, message?: string) => {
      addToast({ type: 'info', title, message })
    },
    [addToast]
  )

  return (
    <ToastContext.Provider value={{ toasts, addToast, removeToast, showError, showSuccess, showInfo }}>
      {children}
      {/* Toast container */}
      <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm">
        {toasts.map((toast) => (
          <ToastItem
            key={toast.id}
            toast={toast}
            onRemove={() => removeToast(toast.id)}
          />
        ))}
      </div>
    </ToastContext.Provider>
  )
}
