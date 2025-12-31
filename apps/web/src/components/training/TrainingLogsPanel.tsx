/**
 * Training Logs Panel
 *
 * Displays training logs with support for:
 * - Regular log messages (INFO, WARNING, ERROR, DEBUG)
 * - Live progress bars that update in place
 * - Stage progress (initializing, loading model, etc.)
 * - Training progress with step/loss/speed/ETA
 */

import { useState, useEffect, useRef, useMemo } from 'react'
import { Terminal, RefreshCw, Search, ChevronDown, ChevronUp } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { cn } from '@/lib/utils'

// Types
export interface LogEntry {
  timestamp: string
  level: string
  message: string
  event?: string
  fields?: Record<string, unknown>
}

export interface ProgressBar {
  id: string
  type: string // 'stage' | 'training' | 'download' | 'upload' | 'sample' | 'checkpoint'
  label: string
  value: number // 0-100
  current?: number
  total?: number
  timestamp: string
  completed?: boolean
}

interface TrainingLogsPanelProps {
  logs: LogEntry[]
  progressBars: Map<string, ProgressBar>
  lastLogTime: Date | null
  isActive: boolean
  onRefresh: () => void
}

// Progress bar colors by type
const progressBarColors: Record<string, string> = {
  stage: 'bg-blue-500',
  training: 'bg-green-500',
  download: 'bg-purple-500',
  upload: 'bg-orange-500',
  sample: 'bg-pink-500',
  checkpoint: 'bg-yellow-500',
}

// Log level colors
function getLogLevelClass(level: string): string {
  switch (level) {
    case 'ERROR':
      return 'text-red-400 bg-red-500/10'
    case 'WARNING':
      return 'text-yellow-400 bg-yellow-500/10'
    case 'DEBUG':
      return 'text-gray-500'
    default:
      return 'text-muted-foreground'
  }
}

function getLogLevelBadgeClass(level: string): string {
  switch (level) {
    case 'ERROR':
      return 'text-red-400'
    case 'WARNING':
      return 'text-yellow-400'
    case 'DEBUG':
      return 'text-gray-500'
    default:
      return 'text-blue-400'
  }
}

// Format bytes to human readable
function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`
}

export function TrainingLogsPanel({
  logs,
  progressBars,
  lastLogTime,
  isActive: _isActive, // Used for future styling
  onRefresh,
}: TrainingLogsPanelProps) {
  const [logFilter, setLogFilter] = useState<'all' | 'info' | 'error'>('all')
  const [logSearch, setLogSearch] = useState('')
  const [autoScroll, setAutoScroll] = useState(true)
  const [showProgressBars, setShowProgressBars] = useState(true)
  const logsEndRef = useRef<HTMLDivElement>(null)

  // Auto-scroll when new logs arrive
  useEffect(() => {
    if (autoScroll) {
      logsEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [logs, autoScroll])

  // Filter and search logs
  const filteredLogs = useMemo(() => {
    return logs.filter((log) => {
      // Level filter
      if (logFilter === 'error' && log.level !== 'ERROR' && log.level !== 'WARNING') {
        return false
      }
      if (logFilter === 'info' && log.level !== 'INFO') {
        return false
      }
      // Text search
      if (logSearch && !log.message.toLowerCase().includes(logSearch.toLowerCase())) {
        return false
      }
      return true
    })
  }, [logs, logFilter, logSearch])

  // Get active progress bars (sorted by creation time)
  const activeProgressBars = useMemo(() => {
    return Array.from(progressBars.values())
      .filter((pb) => !pb.completed || pb.value < 100)
      .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())
  }, [progressBars])

  // Get completed progress bars (for display at bottom)
  const completedProgressBars = useMemo(() => {
    return Array.from(progressBars.values())
      .filter((pb) => pb.completed || pb.value >= 100)
      .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())
      .slice(0, 3) // Show last 3 completed
  }, [progressBars])

  return (
    <Card className="flex-1">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <CardTitle className="text-sm flex items-center gap-2">
            <Terminal className="h-4 w-4" />
            Training Logs ({filteredLogs.length})
            {lastLogTime && (
              <span className="text-xs font-normal text-muted-foreground">
                (last: {lastLogTime.toLocaleTimeString()})
              </span>
            )}
          </CardTitle>
          <div className="flex items-center gap-3">
            {/* Search input */}
            <div className="relative">
              <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3 w-3 text-muted-foreground" />
              <input
                type="text"
                placeholder="Search logs..."
                value={logSearch}
                onChange={(e) => setLogSearch(e.target.value)}
                className="text-xs bg-input border border-border rounded pl-7 pr-2 py-1 w-32 focus:w-48 transition-all focus:outline-none focus:ring-1 focus:ring-accent"
              />
            </div>
            <label className="flex items-center gap-1 text-xs text-muted-foreground cursor-pointer">
              <input
                type="checkbox"
                checked={autoScroll}
                onChange={(e) => setAutoScroll(e.target.checked)}
                className="w-3 h-3 rounded"
              />
              Auto-scroll
            </label>
            <select
              className="text-xs bg-input border border-border rounded px-2 py-1"
              value={logFilter}
              onChange={(e) => setLogFilter(e.target.value as 'all' | 'info' | 'error')}
            >
              <option value="all">All</option>
              <option value="info">Info</option>
              <option value="error">Errors</option>
            </select>
            <Button variant="ghost" size="sm" onClick={onRefresh} title="Refresh logs">
              <RefreshCw className="h-3 w-3" />
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Progress Bars Section */}
        {(activeProgressBars.length > 0 || completedProgressBars.length > 0) && (
          <div className="space-y-2">
            <button
              onClick={() => setShowProgressBars(!showProgressBars)}
              className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
            >
              {showProgressBars ? (
                <ChevronUp className="h-3 w-3" />
              ) : (
                <ChevronDown className="h-3 w-3" />
              )}
              Progress ({activeProgressBars.length} active)
            </button>

            {showProgressBars && (
              <div className="space-y-2 p-2 rounded border border-border bg-muted/30">
                {/* Active progress bars */}
                {activeProgressBars.map((pb) => (
                  <ProgressBarDisplay key={pb.id} progressBar={pb} isActive={true} />
                ))}

                {/* Show separator if both active and completed */}
                {activeProgressBars.length > 0 && completedProgressBars.length > 0 && (
                  <div className="border-t border-border/50 my-2" />
                )}

                {/* Completed progress bars (faded) */}
                {completedProgressBars.map((pb) => (
                  <ProgressBarDisplay key={pb.id} progressBar={pb} isActive={false} />
                ))}
              </div>
            )}
          </div>
        )}

        {/* Logs Section */}
        <ScrollArea className="h-80 rounded border border-border bg-background p-3">
          <div className="font-mono text-xs space-y-1">
            {filteredLogs.length === 0 ? (
              <p className="text-muted-foreground">
                {logs.length === 0 ? 'No logs yet...' : 'No logs match your filter.'}
              </p>
            ) : (
              filteredLogs.map((log, i) => (
                <div key={i} className={cn('py-0.5 px-1 rounded', getLogLevelClass(log.level))}>
                  <span className="text-muted-foreground/50">
                    {new Date(log.timestamp).toLocaleTimeString()}
                  </span>{' '}
                  <span className={cn('font-semibold', getLogLevelBadgeClass(log.level))}>
                    [{log.level}]
                  </span>{' '}
                  {log.message}
                </div>
              ))
            )}
            <div ref={logsEndRef} />
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  )
}

// Progress bar display component
function ProgressBarDisplay({
  progressBar,
  isActive,
}: {
  progressBar: ProgressBar
  isActive: boolean
}) {
  const colorClass = progressBarColors[progressBar.type] || 'bg-accent'
  const value = Math.min(100, Math.max(0, progressBar.value))

  // Format the detail text
  let detailText = ''
  if (progressBar.current !== undefined && progressBar.total !== undefined) {
    if (progressBar.type === 'download' || progressBar.type === 'upload') {
      detailText = `${formatBytes(progressBar.current)} / ${formatBytes(progressBar.total)}`
    } else {
      detailText = `${progressBar.current.toLocaleString()} / ${progressBar.total.toLocaleString()}`
    }
  }

  return (
    <div className={cn('space-y-1', !isActive && 'opacity-50')}>
      <div className="flex items-center justify-between text-xs">
        <span className="text-foreground font-medium truncate">{progressBar.label}</span>
        <span className="text-muted-foreground ml-2 whitespace-nowrap">
          {detailText && `${detailText} • `}
          {value.toFixed(1)}%
        </span>
      </div>
      <div className="relative h-2 w-full overflow-hidden rounded-full bg-muted">
        <div
          className={cn(
            'h-full transition-all duration-300 ease-out rounded-full',
            colorClass,
            isActive && value < 100 && 'animate-pulse'
          )}
          style={{ width: `${value}%` }}
        />
      </div>
    </div>
  )
}

export default TrainingLogsPanel
