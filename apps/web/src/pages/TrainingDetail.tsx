/**
 * Training Detail Page
 *
 * Full page view for a specific training job with:
 * - Real-time progress via SSE with exponential backoff reconnection
 * - Live logs viewer with filtering and search
 * - Sample images gallery
 * - Checkpoints panel with download
 * - GPU stats panel
 * - Metrics display (loss, step, ETA, iteration speed)
 * - Log-derived progress with API fallback
 * - Debug bundle download
 *
 * Works for:
 * - Running jobs (live updates)
 * - Failed jobs (shows error state + error logs)
 * - Succeeded jobs (static final state + artifacts)
 */

import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
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
  Clock,
  Gauge,
  Bug,
  X,
  Cpu,
  Thermometer,
  Zap,
  CheckCircle2,
  XCircle,
  Loader2,
  Search,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { LossChart } from '@/components/training/LossChart'
import { CheckpointsPanel } from '@/components/training/CheckpointsPanel'
import { SampleImagesPanel } from '@/components/training/SampleImagesPanel'
import { api, Character, GPUMetrics } from '@/lib/api'

interface LogEntry {
  timestamp: string
  level: string
  message: string
  event?: string
  fields?: Record<string, unknown>
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

// SSE reconnection with exponential backoff
const SSE_INITIAL_RETRY_DELAY = 1000
const SSE_MAX_RETRY_DELAY = 30000
const SSE_BACKOFF_MULTIPLIER = 2

export default function TrainingDetailPage() {
  const { jobId } = useParams<{ jobId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [logs, setLogs] = useState<LogEntry[]>([])
  const [sseConnected, setSseConnected] = useState(false)
  const [sseError, setSseError] = useState<string | null>(null)
  const [sseRetryCountdown, setSseRetryCountdown] = useState<number | null>(null)
  const [logFilter, setLogFilter] = useState<'all' | 'info' | 'error'>('all')
  const [logSearch, setLogSearch] = useState('')
  const [copiedId, setCopiedId] = useState(false)
  const [gpuMetrics, setGpuMetrics] = useState<GPUMetrics | null>(null)
  const [showCancelConfirm, setShowCancelConfirm] = useState(false)
  const [lossHistory, setLossHistory] = useState<{ step: number; loss: number }[]>([])
  const [autoScroll, setAutoScroll] = useState(true)
  const [lastLogTime, setLastLogTime] = useState<Date | null>(null)

  // Log-derived progress state
  const [logDerivedStep, setLogDerivedStep] = useState<number>(0)
  const [logDerivedTotal, setLogDerivedTotal] = useState<number>(0)
  const [usingLogProgress, setUsingLogProgress] = useState(false)

  const logsEndRef = useRef<HTMLDivElement>(null)
  const eventSourceRef = useRef<EventSource | null>(null)
  const retryTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const retryDelayRef = useRef<number>(SSE_INITIAL_RETRY_DELAY)
  const countdownIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

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

  // Fetch character for name and trigger word
  const { data: characters = [] } = useQuery({
    queryKey: ['characters'],
    queryFn: api.listCharacters,
  })

  const character = job
    ? characters.find((c: Character) => c.id === job.character_id)
    : null
  const characterName = character?.name || 'Unknown'
  const triggerWord = character?.trigger_word || null

  const isActive = job && ['running', 'queued', 'pending'].includes(job.status)

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

  // Update logs from API response
  useEffect(() => {
    if (logsData?.entries) {
      setLogs(logsData.entries)
      if (logsData.entries.length > 0) {
        const lastEntry = logsData.entries[logsData.entries.length - 1]
        setLastLogTime(new Date(lastEntry.timestamp))
      }
    }
  }, [logsData])

  // Parse progress from log messages
  const parseProgressFromMessage = useCallback((message: string) => {
    // Pattern: "Step 123/500" or "step 123 / 500" etc.
    const stepMatch = message.match(/[Ss]tep\s*(\d+)\s*[/]\s*(\d+)/)
    if (stepMatch) {
      const current = parseInt(stepMatch[1], 10)
      const total = parseInt(stepMatch[2], 10)
      if (current > 0 && total > 0) {
        setLogDerivedStep(current)
        setLogDerivedTotal(total)
        setUsingLogProgress(true)
      }
    }
  }, [])

  // SSE Connection with exponential backoff reconnection
  const connectSSE = useCallback(() => {
    if (!isActive || !jobId) return

    // Clear any pending retry
    if (retryTimeoutRef.current) {
      clearTimeout(retryTimeoutRef.current)
      retryTimeoutRef.current = null
    }
    if (countdownIntervalRef.current) {
      clearInterval(countdownIntervalRef.current)
      countdownIntervalRef.current = null
    }
    setSseRetryCountdown(null)

    // Close existing connection
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
    }

    const eventSource = new EventSource(`/api/jobs/${jobId}/stream`)
    eventSourceRef.current = eventSource

    eventSource.onopen = () => {
      setSseConnected(true)
      setSseError(null)
      retryDelayRef.current = SSE_INITIAL_RETRY_DELAY // Reset on success

      // Fetch historical logs to catch up
      refetchLogs()
    }

    eventSource.addEventListener('progress', (e) => {
      try {
        const data = JSON.parse(e.data)

        // Update GPU metrics from flat fields or nested object
        const gpuData = data.gpu || (data.gpu_utilization !== undefined ? {
          utilization: parseFloat(data.gpu_utilization) || 0,
          memory_used: parseFloat(data.gpu_memory_used) || 0,
          memory_total: parseFloat(data.gpu_memory_total) || 0,
          temperature: parseFloat(data.gpu_temperature) || 0,
          power_watts: parseFloat(data.power_watts) || 0,
        } : null)

        if (gpuData) {
          setGpuMetrics(gpuData)
        }

        // Extract step info (handles both formats)
        const currentStep = data.step || data.current_step || 0
        const currentLoss = data.loss || data.current_loss

        // Update loss history for chart
        if (currentStep > 0 && currentLoss !== undefined && currentLoss !== null) {
          setLossHistory(prev => {
            // Only add if step is new (avoid duplicates)
            if (prev.length === 0 || prev[prev.length - 1].step < currentStep) {
              const newHistory = [...prev, { step: currentStep, loss: currentLoss }]
              // Keep last 500 points to avoid memory issues
              return newHistory.slice(-500)
            }
            return prev
          })
        }

        // Parse progress from message
        if (data.message) {
          parseProgressFromMessage(data.message)
        }

        // Add log entry for every step with progress info
        if (data.message && currentStep > 0) {
          setLogs(prev => {
            // Avoid duplicate entries for same step
            const lastLog = prev[prev.length - 1]
            if (lastLog?.fields?.step === currentStep) {
              return prev
            }
            const newLogs = [...prev.slice(-500), {
              timestamp: data.timestamp || new Date().toISOString(),
              level: 'INFO',
              message: data.message,
              event: 'training.progress',
              fields: {
                step: currentStep,
                loss: currentLoss,
                lr: data.lr,
                iteration_speed: data.iteration_speed,
                eta_seconds: data.eta_seconds,
              },
            }]
            setLastLogTime(new Date())
            return newLogs
          })
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
      refetchLogs()
      eventSource.close()
      setSseConnected(false)
    })

    eventSource.onerror = () => {
      eventSource.close()
      setSseConnected(false)

      // Calculate next retry delay with exponential backoff
      const nextDelay = Math.min(
        retryDelayRef.current * SSE_BACKOFF_MULTIPLIER,
        SSE_MAX_RETRY_DELAY
      )

      setSseError(`Connection lost. Reconnecting in ${Math.ceil(retryDelayRef.current / 1000)}s...`)
      setSseRetryCountdown(Math.ceil(retryDelayRef.current / 1000))

      // Start countdown
      let countdown = Math.ceil(retryDelayRef.current / 1000)
      countdownIntervalRef.current = setInterval(() => {
        countdown -= 1
        if (countdown > 0) {
          setSseRetryCountdown(countdown)
          setSseError(`Connection lost. Reconnecting in ${countdown}s...`)
        }
      }, 1000)

      // Schedule retry
      retryTimeoutRef.current = setTimeout(() => {
        if (countdownIntervalRef.current) {
          clearInterval(countdownIntervalRef.current)
        }
        setSseRetryCountdown(null)
        connectSSE()
      }, retryDelayRef.current)

      retryDelayRef.current = nextDelay
    }
  }, [jobId, isActive, queryClient, refetchLogs, parseProgressFromMessage])

  // Start SSE connection
  useEffect(() => {
    connectSSE()

    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
      }
      if (retryTimeoutRef.current) {
        clearTimeout(retryTimeoutRef.current)
      }
      if (countdownIntervalRef.current) {
        clearInterval(countdownIntervalRef.current)
      }
      setSseConnected(false)
    }
  }, [connectSSE])

  // Auto-scroll logs when enabled
  useEffect(() => {
    if (autoScroll) {
      logsEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [logs, autoScroll])

  // Copy job ID
  const copyJobId = useCallback(() => {
    if (jobId) {
      navigator.clipboard.writeText(jobId)
      setCopiedId(true)
      setTimeout(() => setCopiedId(false), 2000)
    }
  }, [jobId])

  // Filter and search logs
  const filteredLogs = useMemo(() => {
    return logs.filter(log => {
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

  // Calculate effective progress - prefer log-derived, fallback to API
  const effectiveProgress = useMemo(() => {
    if (usingLogProgress && logDerivedTotal > 0) {
      return {
        current: logDerivedStep,
        total: logDerivedTotal,
        percent: (logDerivedStep / logDerivedTotal) * 100,
        source: 'log' as const,
      }
    }
    return {
      current: job?.current_step || 0,
      total: job?.total_steps || 0,
      percent: job?.progress || 0,
      source: 'api' as const,
    }
  }, [usingLogProgress, logDerivedStep, logDerivedTotal, job])

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

  // Log level colors
  const getLogLevelClass = (level: string) => {
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
                {triggerWord && (
                  <span className="text-sm font-normal text-muted-foreground">
                    (trigger: {triggerWord})
                  </span>
                )}
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
              <CardTitle className="text-sm flex items-center gap-2">
                Progress
                {effectiveProgress.source === 'log' && (
                  <span className="text-xs font-normal text-green-500">(live)</span>
                )}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <Progress value={effectiveProgress.percent} className="h-3" />
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">
                  Step {effectiveProgress.current} / {effectiveProgress.total}
                </span>
                <span className="font-medium">{effectiveProgress.percent.toFixed(1)}%</span>
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

          {/* Config Summary - without base model per spec */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Configuration</CardTitle>
            </CardHeader>
            <CardContent className="space-y-1 text-sm">
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

          {/* Checkpoints Panel */}
          <CheckpointsPanel jobId={job.id} isActive={!!isActive} />

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
          {/* Sample Images Panel */}
          <SampleImagesPanel jobId={job.id} isActive={!!isActive} />

          {/* Loss Chart */}
          <LossChart
            data={lossHistory}
            currentStep={effectiveProgress.current}
            totalSteps={effectiveProgress.total}
          />

          {/* Logs */}
          <Card className="flex-1">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <CardTitle className="text-sm flex items-center gap-2">
                  <Terminal className="h-4 w-4" />
                  Logs ({filteredLogs.length})
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
                    <p className="text-muted-foreground">
                      {logs.length === 0 ? 'No logs yet...' : 'No logs match your filter.'}
                    </p>
                  ) : (
                    filteredLogs.map((log, i) => (
                      <div
                        key={i}
                        className={`py-0.5 px-1 rounded ${getLogLevelClass(log.level)}`}
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
            {sseConnected ? 'Live updates connected' : sseError || 'Reconnecting...'}
          </span>
          {sseRetryCountdown !== null && (
            <span className="text-yellow-400">({sseRetryCountdown}s)</span>
          )}
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
