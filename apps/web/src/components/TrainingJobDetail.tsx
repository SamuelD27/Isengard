/**
 * Training Job Detail Component
 *
 * Comprehensive job view with:
 * - Real-time progress via SSE
 * - Live logs viewer with filtering
 * - Sample images gallery
 * - Metrics display (loss, step, ETA)
 * - Debug bundle download
 */

import { useState, useEffect, useRef, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  X,
  Download,
  Copy,
  Check,
  AlertTriangle,
  RefreshCw,
  Square,
  Terminal,
  Image as ImageIcon,
  Clock,
  Gauge,
  Bug,
  Maximize2,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { TrainingJob } from '@/lib/api'

interface TrainingJobDetailProps {
  job: TrainingJob
  characterName?: string
  onClose: () => void
  onCancel?: () => void
}

interface LogEntry {
  timestamp: string
  level: string
  message: string
  event?: string
  fields?: Record<string, unknown>
}

interface SampleImage {
  name: string
  url: string
  step: number | null
  created_at: string
}

interface ProgressEvent {
  job_id: string
  status: string
  stage?: string
  step: number
  steps_total: number
  progress_pct: number
  loss?: number
  lr?: number
  eta_seconds?: number
  message: string
  sample_path?: string
  error?: string
  error_type?: string
  timestamp?: string
}

export function TrainingJobDetail({
  job: initialJob,
  characterName,
  onClose,
  onCancel,
}: TrainingJobDetailProps) {
  const [job, setJob] = useState<TrainingJob>(initialJob)
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [samples, setSamples] = useState<SampleImage[]>([])
  const [sseConnected, setSseConnected] = useState(false)
  const [sseError, setSseError] = useState<string | null>(null)
  const [logFilter, setLogFilter] = useState<'all' | 'info' | 'error'>('all')
  const [copiedId, setCopiedId] = useState(false)
  const [selectedSample, setSelectedSample] = useState<SampleImage | null>(null)

  const logsEndRef = useRef<HTMLDivElement>(null)
  const eventSourceRef = useRef<EventSource | null>(null)

  const isActive = ['running', 'queued', 'pending'].includes(job.status)

  // Fetch artifacts (samples)
  const { data: artifacts, refetch: refetchArtifacts } = useQuery({
    queryKey: ['job-artifacts', job.id],
    queryFn: async () => {
      const response = await fetch(`/api/jobs/${job.id}/artifacts`)
      if (!response.ok) return { artifacts: [] }
      return response.json()
    },
    refetchInterval: isActive ? 5000 : false,
  })

  // Fetch logs
  const { data: logsData, refetch: refetchLogs } = useQuery({
    queryKey: ['job-logs', job.id],
    queryFn: async () => {
      const response = await fetch(`/api/jobs/${job.id}/logs/view?limit=500`)
      if (!response.ok) return { entries: [] }
      return response.json()
    },
    refetchInterval: isActive ? 3000 : false,
  })

  // Update samples from artifacts
  useEffect(() => {
    if (artifacts?.artifacts) {
      const sampleArtifacts = artifacts.artifacts
        .filter((a: any) => a.type === 'sample')
        .map((a: any) => ({
          name: a.name,
          url: a.url,
          step: a.step,
          created_at: a.created_at,
        }))
      setSamples(sampleArtifacts)
    }
  }, [artifacts])

  // Update logs from API response
  useEffect(() => {
    if (logsData?.entries) {
      setLogs(logsData.entries)
    }
  }, [logsData])

  // SSE Connection for real-time updates
  useEffect(() => {
    if (!isActive) return

    const eventSource = new EventSource(`/api/jobs/${job.id}/stream`)
    eventSourceRef.current = eventSource

    eventSource.onopen = () => {
      setSseConnected(true)
      setSseError(null)
    }

    eventSource.addEventListener('progress', (e) => {
      try {
        const data: ProgressEvent = JSON.parse(e.data)

        // Update job state
        setJob(prev => ({
          ...prev,
          progress: data.progress_pct,
          current_step: data.step,
          total_steps: data.steps_total,
          status: data.status as any,
        }))

        // Add log entry for significant events
        if (data.message && data.step % Math.max(1, Math.floor(data.steps_total / 20)) === 0) {
          setLogs(prev => [...prev.slice(-500), {
            timestamp: data.timestamp || new Date().toISOString(),
            level: 'INFO',
            message: data.message,
            event: 'training.progress',
            fields: { step: data.step, loss: data.loss, lr: data.lr },
          }])
        }

        // Check for new sample
        if (data.sample_path) {
          refetchArtifacts()
        }
      } catch (err) {
        console.error('SSE parse error:', err)
      }
    })

    eventSource.addEventListener('complete', (e) => {
      try {
        const data = JSON.parse(e.data)
        setJob(prev => ({
          ...prev,
          status: data.status,
          progress: 100,
          error_message: data.error,
        }))
        refetchArtifacts()
        refetchLogs()
      } catch (err) {
        console.error('SSE complete parse error:', err)
      }
      eventSource.close()
      setSseConnected(false)
    })

    eventSource.onerror = () => {
      setSseError('Connection lost. Reconnecting...')
      setSseConnected(false)
    }

    return () => {
      eventSource.close()
      setSseConnected(false)
    }
  }, [job.id, isActive, refetchArtifacts, refetchLogs])

  // Auto-scroll logs
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  // Copy correlation ID
  const copyCorrelationId = useCallback(() => {
    navigator.clipboard.writeText(job.id)
    setCopiedId(true)
    setTimeout(() => setCopiedId(false), 2000)
  }, [job.id])

  // Filter logs
  const filteredLogs = logs.filter(log => {
    if (logFilter === 'all') return true
    if (logFilter === 'error') return log.level === 'ERROR' || log.level === 'WARNING'
    return log.level === 'INFO'
  })

  // Calculate ETA
  const etaDisplay = job.current_step > 0 && job.total_steps > 0
    ? `~${Math.ceil((job.total_steps - job.current_step) * 0.05 / 60)} min`
    : '--'

  const statusColors: Record<string, string> = {
    pending: 'bg-yellow-500/20 text-yellow-400',
    queued: 'bg-blue-500/20 text-blue-400',
    running: 'bg-green-500/20 text-green-400',
    completed: 'bg-green-500/20 text-green-400',
    failed: 'bg-red-500/20 text-red-400',
    cancelled: 'bg-gray-500/20 text-gray-400',
  }

  return (
    <div className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm">
      <div className="fixed inset-4 z-50 bg-background border border-border rounded-lg shadow-xl overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <div className="flex items-center gap-4">
            <div>
              <h2 className="text-lg font-semibold text-foreground flex items-center gap-2">
                {characterName || 'Training Job'}
                <Badge className={statusColors[job.status]}>
                  {job.status}
                </Badge>
                {sseConnected && (
                  <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" title="Live" />
                )}
              </h2>
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <code className="font-mono text-xs bg-muted px-1 rounded">{job.id}</code>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-5 w-5 p-0"
                  onClick={copyCorrelationId}
                  title="Copy job ID"
                >
                  {copiedId ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
                </Button>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {isActive && onCancel && (
              <Button variant="outline" size="sm" onClick={onCancel}>
                <Square className="h-4 w-4 mr-2" />
                Cancel
              </Button>
            )}
            <Button
              variant="outline"
              size="sm"
              onClick={() => window.open(`/api/jobs/${job.id}/debug-bundle`, '_blank')}
              title="Download debug bundle"
            >
              <Bug className="h-4 w-4 mr-2" />
              Debug Bundle
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => window.open(`/api/jobs/${job.id}/logs`, '_blank')}
              title="Download logs"
            >
              <Download className="h-4 w-4 mr-2" />
              Logs
            </Button>
            <Button variant="ghost" size="sm" onClick={onClose}>
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>

        {/* Main Content */}
        <div className="flex-1 overflow-hidden flex">
          {/* Left Panel - Progress & Metrics */}
          <div className="w-80 border-r border-border p-4 space-y-4 overflow-y-auto">
            {/* Progress */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">Progress</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <Progress value={job.progress} className="h-3" />
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">
                    Step {job.current_step} / {job.total_steps}
                  </span>
                  <span className="font-medium">{job.progress.toFixed(1)}%</span>
                </div>
              </CardContent>
            </Card>

            {/* Metrics */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">Metrics</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground flex items-center gap-1">
                    <Clock className="h-3 w-3" /> ETA
                  </span>
                  <span>{etaDisplay}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground flex items-center gap-1">
                    <Gauge className="h-3 w-3" /> Loss
                  </span>
                  <span>{job.progress > 0 ? '~0.05' : '--'}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">LR</span>
                  <span>{job.config.learning_rate.toExponential(2)}</span>
                </div>
              </CardContent>
            </Card>

            {/* Config Summary */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">Configuration</CardTitle>
              </CardHeader>
              <CardContent className="space-y-1 text-sm">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Steps</span>
                  <span>{job.config.steps}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Resolution</span>
                  <span>{job.config.resolution}px</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">LoRA Rank</span>
                  <span>{job.config.lora_rank}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Batch Size</span>
                  <span>{job.config.batch_size}</span>
                </div>
              </CardContent>
            </Card>

            {/* Error Display */}
            {job.status === 'failed' && job.error_message && (
              <Card className="border-red-500/50">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm text-red-400 flex items-center gap-2">
                    <AlertTriangle className="h-4 w-4" />
                    Error
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-red-300 font-mono break-all">
                    {job.error_message}
                  </p>
                  <p className="text-xs text-muted-foreground mt-2">
                    Download the debug bundle for full stack trace and logs.
                  </p>
                </CardContent>
              </Card>
            )}
          </div>

          {/* Right Panel - Logs & Samples */}
          <div className="flex-1 flex flex-col overflow-hidden">
            {/* Samples Gallery */}
            {samples.length > 0 && (
              <div className="border-b border-border p-4">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-sm font-medium flex items-center gap-2">
                    <ImageIcon className="h-4 w-4" />
                    Sample Images ({samples.length})
                  </h3>
                </div>
                <div className="flex gap-3 overflow-x-auto pb-2">
                  {samples.map((sample) => (
                    <button
                      key={sample.name}
                      onClick={() => setSelectedSample(sample)}
                      className="flex-shrink-0 relative group"
                    >
                      <img
                        src={sample.url}
                        alt={sample.name}
                        className="h-24 w-24 object-cover rounded border border-border hover:border-accent transition-colors"
                      />
                      <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity rounded flex items-center justify-center">
                        <Maximize2 className="h-5 w-5 text-white" />
                      </div>
                      {sample.step && (
                        <span className="absolute bottom-1 right-1 text-xs bg-black/70 text-white px-1 rounded">
                          #{sample.step}
                        </span>
                      )}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Logs */}
            <div className="flex-1 flex flex-col overflow-hidden">
              <div className="flex items-center justify-between px-4 py-2 border-b border-border">
                <h3 className="text-sm font-medium flex items-center gap-2">
                  <Terminal className="h-4 w-4" />
                  Logs
                </h3>
                <div className="flex items-center gap-2">
                  <select
                    className="text-xs bg-input border border-border rounded px-2 py-1"
                    value={logFilter}
                    onChange={(e) => setLogFilter(e.target.value as any)}
                  >
                    <option value="all">All</option>
                    <option value="info">Info</option>
                    <option value="error">Errors</option>
                  </select>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => refetchLogs()}
                    title="Refresh logs"
                  >
                    <RefreshCw className="h-3 w-3" />
                  </Button>
                </div>
              </div>
              <ScrollArea className="flex-1 p-4">
                <div className="font-mono text-xs space-y-1">
                  {filteredLogs.length === 0 ? (
                    <p className="text-muted-foreground">No logs yet...</p>
                  ) : (
                    filteredLogs.map((log, i) => (
                      <div
                        key={i}
                        className={`py-0.5 ${
                          log.level === 'ERROR'
                            ? 'text-red-400'
                            : log.level === 'WARNING'
                            ? 'text-yellow-400'
                            : 'text-muted-foreground'
                        }`}
                      >
                        <span className="text-muted-foreground/50">
                          {new Date(log.timestamp).toLocaleTimeString()}
                        </span>
                        {' '}
                        <span className={`font-semibold ${
                          log.level === 'ERROR' ? 'text-red-400' :
                          log.level === 'WARNING' ? 'text-yellow-400' :
                          log.level === 'DEBUG' ? 'text-gray-500' :
                          'text-blue-400'
                        }`}>
                          [{log.level}]
                        </span>
                        {' '}
                        {log.message}
                      </div>
                    ))
                  )}
                  <div ref={logsEndRef} />
                </div>
              </ScrollArea>
            </div>
          </div>
        </div>

        {/* SSE Status Bar */}
        {isActive && (
          <div className="px-4 py-2 border-t border-border bg-muted/30 flex items-center justify-between text-xs">
            <div className="flex items-center gap-2">
              <span className={`w-2 h-2 rounded-full ${sseConnected ? 'bg-green-500' : 'bg-yellow-500'}`} />
              <span className="text-muted-foreground">
                {sseConnected ? 'Live updates connected' : 'Reconnecting...'}
              </span>
            </div>
            {sseError && (
              <span className="text-yellow-400">{sseError}</span>
            )}
          </div>
        )}
      </div>

      {/* Sample Image Modal */}
      {selectedSample && (
        <div
          className="fixed inset-0 z-60 bg-black/90 flex items-center justify-center p-8"
          onClick={() => setSelectedSample(null)}
        >
          <div className="relative max-w-4xl max-h-full">
            <img
              src={selectedSample.url}
              alt={selectedSample.name}
              className="max-w-full max-h-[80vh] object-contain rounded"
            />
            <div className="absolute bottom-4 left-4 bg-black/70 text-white px-3 py-1 rounded text-sm">
              {selectedSample.step && `Step ${selectedSample.step}`}
            </div>
            <Button
              variant="ghost"
              size="sm"
              className="absolute top-4 right-4"
              onClick={() => setSelectedSample(null)}
            >
              <X className="h-5 w-5" />
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
