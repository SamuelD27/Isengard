/**
 * Training Detail Page
 *
 * Full page view for a specific training job with:
 * - Real-time progress via SSE
 * - Live logs viewer with filtering
 * - Sample images gallery
 * - GPU stats panel
 * - Metrics display (loss, step, ETA, iteration speed)
 * - Debug bundle download
 *
 * Works for:
 * - Running jobs (live updates)
 * - Failed jobs (shows error state + error logs)
 * - Succeeded jobs (static final state + artifacts)
 */

import { useState, useEffect, useRef, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft,
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
  X,
  Cpu,
  Thermometer,
  Zap,
  CheckCircle2,
  XCircle,
  Loader2,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { api, Character, GPUMetrics } from '@/lib/api'

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
  gpu?: GPUMetrics
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`
  if (seconds < 3600) {
    const mins = Math.floor(seconds / 60)
    const secs = seconds % 60
    return `${mins}m ${secs}s`
  }
  const hours = Math.floor(seconds / 3600)
  const mins = Math.floor((seconds % 3600) / 60)
  return `${hours}h ${mins}m`
}

export default function TrainingDetailPage() {
  const { jobId } = useParams<{ jobId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [logs, setLogs] = useState<LogEntry[]>([])
  const [samples, setSamples] = useState<SampleImage[]>([])
  const [sseConnected, setSseConnected] = useState(false)
  const [sseError, setSseError] = useState<string | null>(null)
  const [logFilter, setLogFilter] = useState<'all' | 'info' | 'error'>('all')
  const [copiedId, setCopiedId] = useState(false)
  const [selectedSample, setSelectedSample] = useState<SampleImage | null>(null)
  const [gpuMetrics, setGpuMetrics] = useState<GPUMetrics | null>(null)
  const [showCancelConfirm, setShowCancelConfirm] = useState(false)

  const logsEndRef = useRef<HTMLDivElement>(null)
  const eventSourceRef = useRef<EventSource | null>(null)

  // Fetch job data
  const { data: job, isLoading: jobLoading, error: jobError } = useQuery({
    queryKey: ['training-job', jobId],
    queryFn: () => api.getTrainingJob(jobId!),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const data = query.state.data
      if (!data) return 5000
      // Stop polling for completed jobs
      if (['completed', 'failed', 'cancelled'].includes(data.status)) return false
      return 2000
    },
  })

  // Fetch character for name
  const { data: characters = [] } = useQuery({
    queryKey: ['characters'],
    queryFn: api.listCharacters,
  })

  const characterName = job
    ? characters.find((c: Character) => c.id === job.character_id)?.name || 'Unknown'
    : 'Loading...'

  const isActive = job && ['running', 'queued', 'pending'].includes(job.status)

  // Fetch artifacts (samples)
  const { data: artifacts, refetch: refetchArtifacts } = useQuery({
    queryKey: ['job-artifacts', jobId],
    queryFn: async () => {
      const response = await fetch(`/api/jobs/${jobId}/artifacts`)
      if (!response.ok) return { artifacts: [] }
      return response.json()
    },
    enabled: !!jobId,
    refetchInterval: isActive ? 5000 : false,
  })

  // Fetch logs
  const { data: logsData, refetch: refetchLogs } = useQuery({
    queryKey: ['job-logs', jobId],
    queryFn: async () => {
      const response = await fetch(`/api/jobs/${jobId}/logs/view?limit=500`)
      if (!response.ok) return { entries: [] }
      return response.json()
    },
    enabled: !!jobId,
    refetchInterval: isActive ? 3000 : false,
  })

  // Cancel mutation
  const cancelMutation = useMutation({
    mutationFn: api.cancelTraining,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['training-job', jobId] })
      queryClient.invalidateQueries({ queryKey: ['training-jobs-ongoing'] })
    },
  })

  // Update samples from artifacts
  useEffect(() => {
    if (artifacts?.artifacts) {
      const sampleArtifacts = artifacts.artifacts
        .filter((a: { type: string }) => a.type === 'sample')
        .map((a: { name: string; url: string; step: number; created_at: string }) => ({
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
    if (!isActive || !jobId) return

    const eventSource = new EventSource(`/api/jobs/${jobId}/stream`)
    eventSourceRef.current = eventSource

    eventSource.onopen = () => {
      setSseConnected(true)
      setSseError(null)
    }

    eventSource.addEventListener('progress', (e) => {
      try {
        const data: ProgressEvent = JSON.parse(e.data)

        // Update GPU metrics
        if (data.gpu) {
          setGpuMetrics(data.gpu)
        }

        // Update iteration speed from step timing
        // Note: The job model tracks this now

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

        // Invalidate job query to get latest data
        queryClient.invalidateQueries({ queryKey: ['training-job', jobId] })
      } catch (err) {
        console.error('SSE parse error:', err)
      }
    })

    eventSource.addEventListener('complete', () => {
      queryClient.invalidateQueries({ queryKey: ['training-job', jobId] })
      queryClient.invalidateQueries({ queryKey: ['training-jobs-ongoing'] })
      queryClient.invalidateQueries({ queryKey: ['training-jobs-successful'] })
      refetchArtifacts()
      refetchLogs()
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
  }, [jobId, isActive, queryClient, refetchArtifacts, refetchLogs])

  // Auto-scroll logs
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  // Copy job ID
  const copyJobId = useCallback(() => {
    if (jobId) {
      navigator.clipboard.writeText(jobId)
      setCopiedId(true)
      setTimeout(() => setCopiedId(false), 2000)
    }
  }, [jobId])

  // Filter logs
  const filteredLogs = logs.filter(log => {
    if (logFilter === 'all') return true
    if (logFilter === 'error') return log.level === 'ERROR' || log.level === 'WARNING'
    return log.level === 'INFO'
  })

  // Status colors
  const statusColors: Record<string, string> = {
    pending: 'bg-yellow-500/20 text-yellow-400',
    queued: 'bg-blue-500/20 text-blue-400',
    running: 'bg-green-500/20 text-green-400',
    completed: 'bg-green-500/20 text-green-400',
    failed: 'bg-red-500/20 text-red-400',
    cancelled: 'bg-gray-500/20 text-gray-400',
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return <CheckCircle2 className="h-5 w-5 text-success" />
      case 'failed':
        return <XCircle className="h-5 w-5 text-destructive" />
      case 'cancelled':
        return <X className="h-5 w-5 text-muted-foreground" />
      default:
        return <Loader2 className="h-5 w-5 text-accent animate-spin" />
    }
  }

  if (jobLoading) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="animate-spin rounded-full h-8 w-8 border-2 border-accent border-t-transparent" />
      </div>
    )
  }

  if (jobError || !job) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" size="sm" onClick={() => navigate('/training')}>
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back to Training
        </Button>
        <Card className="border-destructive/50">
          <CardContent className="py-8 text-center">
            <AlertTriangle className="h-12 w-12 mx-auto text-destructive mb-4" />
            <h3 className="text-lg font-medium text-foreground mb-2">Job Not Found</h3>
            <p className="text-sm text-muted-foreground">
              The training job "{jobId}" could not be found.
            </p>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="space-y-6 fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="sm" onClick={() => navigate('/training')}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div className="flex items-center gap-3">
            {getStatusIcon(job.status)}
            <div>
              <h1 className="text-xl font-semibold text-foreground flex items-center gap-2">
                {characterName}
                <Badge className={statusColors[job.status]}>{job.status}</Badge>
                {sseConnected && (
                  <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" title="Live" />
                )}
              </h1>
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <code className="font-mono text-xs bg-muted px-1 rounded">{job.id}</code>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-5 w-5 p-0"
                  onClick={copyJobId}
                  title="Copy job ID"
                >
                  {copiedId ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
                </Button>
              </div>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {isActive && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowCancelConfirm(true)}
              disabled={cancelMutation.isPending}
            >
              {cancelMutation.isPending ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <Square className="h-4 w-4 mr-2" />
              )}
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
        </div>
      </div>

      {/* Main Content Grid */}
      <div className="grid gap-6 lg:grid-cols-3">
        {/* Left Column - Progress & Metrics */}
        <div className="space-y-4">
          {/* Progress Card */}
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

          {/* Metrics Card */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Metrics</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground flex items-center gap-1">
                  <Clock className="h-3 w-3" /> Elapsed
                </span>
                <span>{job.elapsed_seconds ? formatDuration(job.elapsed_seconds) : '--'}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground flex items-center gap-1">
                  <Clock className="h-3 w-3" /> ETA
                </span>
                <span>{job.eta_seconds ? formatDuration(job.eta_seconds) : '--'}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground flex items-center gap-1">
                  <Zap className="h-3 w-3" /> Speed
                </span>
                <span>{job.iteration_speed ? `${job.iteration_speed.toFixed(2)} it/s` : '--'}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground flex items-center gap-1">
                  <Gauge className="h-3 w-3" /> Loss
                </span>
                <span>{job.current_loss ? job.current_loss.toFixed(4) : '--'}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">LR</span>
                <span>{job.config.learning_rate.toExponential(2)}</span>
              </div>
            </CardContent>
          </Card>

          {/* GPU Stats Card */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center gap-2">
                <Cpu className="h-4 w-4" />
                GPU Stats
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {gpuMetrics ? (
                <>
                  <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">Utilization</span>
                    <span>{gpuMetrics.utilization.toFixed(0)}%</span>
                  </div>
                  <Progress value={gpuMetrics.utilization} className="h-2" />
                  <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">Memory</span>
                    <span>{gpuMetrics.memory_used.toFixed(1)} / {gpuMetrics.memory_total.toFixed(1)} GB</span>
                  </div>
                  <Progress value={(gpuMetrics.memory_used / gpuMetrics.memory_total) * 100} className="h-2" />
                  <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground flex items-center gap-1">
                      <Thermometer className="h-3 w-3" /> Temperature
                    </span>
                    <span>{gpuMetrics.temperature.toFixed(0)}°C</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground flex items-center gap-1">
                      <Zap className="h-3 w-3" /> Power
                    </span>
                    <span>{gpuMetrics.power_watts.toFixed(0)}W</span>
                  </div>
                </>
              ) : (
                <p className="text-sm text-muted-foreground">
                  {isActive ? 'Waiting for GPU data...' : 'GPU stats not available'}
                </p>
              )}
            </CardContent>
          </Card>

          {/* Config Summary */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Configuration</CardTitle>
            </CardHeader>
            <CardContent className="space-y-1 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Base Model</span>
                <span>{job.base_model || 'flux-dev'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Preset</span>
                <span>{job.preset_name ? job.preset_name.charAt(0).toUpperCase() + job.preset_name.slice(1) : 'Custom'}</span>
              </div>
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

        {/* Right Column - Logs & Samples (spans 2 cols) */}
        <div className="lg:col-span-2 space-y-4">
          {/* Samples Gallery */}
          {samples.length > 0 && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2">
                  <ImageIcon className="h-4 w-4" />
                  Sample Images ({samples.length})
                </CardTitle>
              </CardHeader>
              <CardContent>
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
              </CardContent>
            </Card>
          )}

          {/* Logs */}
          <Card className="flex-1">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm flex items-center gap-2">
                  <Terminal className="h-4 w-4" />
                  Logs
                </CardTitle>
                <div className="flex items-center gap-2">
                  <select
                    className="text-xs bg-input border border-border rounded px-2 py-1"
                    value={logFilter}
                    onChange={(e) => setLogFilter(e.target.value as 'all' | 'info' | 'error')}
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
            </CardHeader>
            <CardContent>
              <ScrollArea className="h-96 rounded border border-border bg-background p-3">
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
            </CardContent>
          </Card>
        </div>
      </div>

      {/* SSE Status Bar */}
      {isActive && (
        <div className="fixed bottom-4 left-1/2 -translate-x-1/2 px-4 py-2 bg-muted rounded-full border border-border shadow-lg flex items-center gap-2 text-xs">
          <span className={`w-2 h-2 rounded-full ${sseConnected ? 'bg-green-500' : 'bg-yellow-500'}`} />
          <span className="text-muted-foreground">
            {sseConnected ? 'Live updates connected' : 'Reconnecting...'}
          </span>
          {sseError && (
            <span className="text-yellow-400">{sseError}</span>
          )}
        </div>
      )}

      {/* Sample Image Modal */}
      {selectedSample && (
        <div
          className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center p-8"
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

      {/* Cancel Training Confirmation Dialog */}
      <ConfirmDialog
        open={showCancelConfirm}
        onOpenChange={setShowCancelConfirm}
        title="Cancel Training"
        description="Are you sure you want to cancel this training job? This action cannot be undone and any progress will be lost."
        confirmLabel="Cancel Training"
        variant="destructive"
        onConfirm={() => {
          cancelMutation.mutate(job.id)
          setShowCancelConfirm(false)
        }}
        isLoading={cancelMutation.isPending}
      />
    </div>
  )
}
