/**
 * UELR Logs Page
 *
 * Displays user interaction history with timeline visualization
 * and bundle download capability for debugging.
 */

import { useState, useMemo } from 'react'
import {
  Activity,
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  Download,
  Globe,
  Layers,
  Loader2,
  RefreshCw,
  Search,
  Server,
  Smartphone,
  XCircle,
  Zap,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import {
  useInteractionHistory,
  useInteractionDetails,
  type UELRInteraction,
  type UELRStep,
  type StepStatus,
  type StepComponent,
} from '@/uelr'

// Status badge styling
const statusStyles: Record<StepStatus, { icon: typeof CheckCircle2; className: string }> = {
  success: { icon: CheckCircle2, className: 'bg-green-500/20 text-green-400 border-green-500/30' },
  error: { icon: XCircle, className: 'bg-red-500/20 text-red-400 border-red-500/30' },
  pending: { icon: Clock, className: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30' },
  cancelled: { icon: XCircle, className: 'bg-gray-500/20 text-gray-400 border-gray-500/30' },
}

// Component icon mapping
const componentIcons: Record<StepComponent, typeof Smartphone> = {
  frontend: Smartphone,
  backend: Server,
  worker: Zap,
  plugin: Layers,
  comfyui: Activity,
  redis: Globe,
}

// Format duration for display
function formatDuration(ms: number | undefined): string {
  if (ms === undefined) return '-'
  if (ms < 1000) return `${Math.round(ms)}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  return `${Math.floor(ms / 60000)}m ${Math.round((ms % 60000) / 1000)}s`
}

// Format timestamp for display
function formatTime(isoString: string): string {
  try {
    const date = new Date(isoString)
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch {
    return isoString
  }
}

// Format date for display
function formatDate(isoString: string): string {
  try {
    const date = new Date(isoString)
    const today = new Date()
    const isToday = date.toDateString() === today.toDateString()
    if (isToday) return 'Today'

    const yesterday = new Date(today)
    yesterday.setDate(yesterday.getDate() - 1)
    if (date.toDateString() === yesterday.toDateString()) return 'Yesterday'

    return date.toLocaleDateString([], { month: 'short', day: 'numeric' })
  } catch {
    return isoString
  }
}

// Status badge component
function StatusBadge({ status }: { status: StepStatus }) {
  const { icon: Icon, className } = statusStyles[status] || statusStyles.pending
  return (
    <Badge variant="outline" className={`${className} text-xs`}>
      <Icon className="w-3 h-3 mr-1" />
      {status}
    </Badge>
  )
}

// Interaction list item
function InteractionListItem({
  interaction,
  isSelected,
  onClick,
}: {
  interaction: UELRInteraction
  isSelected: boolean
  onClick: () => void
}) {
  const StatusIcon = statusStyles[interaction.status]?.icon || Clock

  return (
    <div
      className={`p-3 border-b border-gray-700 cursor-pointer hover:bg-gray-800/50 transition-colors ${
        isSelected ? 'bg-gray-800 border-l-2 border-l-blue-500' : ''
      }`}
      onClick={onClick}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <StatusIcon
              className={`w-4 h-4 flex-shrink-0 ${
                interaction.status === 'success'
                  ? 'text-green-400'
                  : interaction.status === 'error'
                    ? 'text-red-400'
                    : 'text-yellow-400'
              }`}
            />
            <span className="font-medium text-sm text-gray-200 truncate">
              {interaction.action_name}
            </span>
          </div>
          <div className="flex items-center gap-2 mt-1 text-xs text-gray-500">
            <span>{formatDate(interaction.started_at)}</span>
            <span>{formatTime(interaction.started_at)}</span>
            {interaction.duration_ms !== undefined && (
              <>
                <span>-</span>
                <span>{formatDuration(interaction.duration_ms)}</span>
              </>
            )}
          </div>
        </div>
        {interaction.error_count > 0 && (
          <Badge variant="outline" className="bg-red-500/20 text-red-400 border-red-500/30 text-xs">
            {interaction.error_count} error{interaction.error_count > 1 ? 's' : ''}
          </Badge>
        )}
      </div>
    </div>
  )
}

// Step timeline item
function StepTimelineItem({ step }: { step: UELRStep }) {
  const [isExpanded, setIsExpanded] = useState(false)
  const ComponentIcon = componentIcons[step.component] || Activity

  const hasDetails = step.details && Object.keys(step.details).length > 0

  return (
    <div className="relative pl-6 pb-4 border-l border-gray-700 last:border-l-transparent">
      {/* Timeline dot */}
      <div
        className={`absolute left-0 top-1 w-3 h-3 -translate-x-1/2 rounded-full border-2 ${
          step.status === 'success'
            ? 'bg-green-500 border-green-400'
            : step.status === 'error'
              ? 'bg-red-500 border-red-400'
              : step.status === 'pending'
                ? 'bg-yellow-500 border-yellow-400'
                : 'bg-gray-500 border-gray-400'
        }`}
      />

      <Collapsible open={isExpanded} onOpenChange={setIsExpanded}>
        <CollapsibleTrigger asChild>
          <div
            className={`cursor-pointer hover:bg-gray-800/50 rounded p-2 -ml-2 ${
              hasDetails ? '' : 'cursor-default'
            }`}
          >
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-center gap-2">
                <ComponentIcon className="w-4 h-4 text-gray-500 flex-shrink-0" />
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-gray-300">{step.message}</span>
                    {hasDetails && (
                      <span className="text-gray-600">
                        {isExpanded ? (
                          <ChevronDown className="w-3 h-3" />
                        ) : (
                          <ChevronRight className="w-3 h-3" />
                        )}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2 mt-0.5 text-xs text-gray-500">
                    <Badge variant="outline" className="text-[10px] px-1 py-0">
                      {step.component}
                    </Badge>
                    <span>{formatTime(step.timestamp)}</span>
                    {step.duration_ms !== undefined && (
                      <span className="text-gray-600">({formatDuration(step.duration_ms)})</span>
                    )}
                  </div>
                </div>
              </div>
              <StatusBadge status={step.status} />
            </div>
          </div>
        </CollapsibleTrigger>

        {hasDetails && (
          <CollapsibleContent>
            <div className="ml-6 mt-2 p-3 bg-gray-900 rounded border border-gray-700 text-xs">
              <pre className="text-gray-400 whitespace-pre-wrap overflow-x-auto">
                {JSON.stringify(step.details, null, 2)}
              </pre>
            </div>
          </CollapsibleContent>
        )}
      </Collapsible>
    </div>
  )
}

// Interaction detail panel
function InteractionDetailPanel({
  interactionId,
  onDownloadBundle,
  isDownloading,
}: {
  interactionId: string | null
  onDownloadBundle: () => void
  isDownloading: boolean
}) {
  const { interaction, loading, error, refetch } = useInteractionDetails(interactionId)

  if (!interactionId) {
    return (
      <div className="flex items-center justify-center h-full text-gray-500">
        <div className="text-center">
          <Activity className="w-12 h-12 mx-auto mb-3 opacity-50" />
          <p>Select an interaction to view details</p>
        </div>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
      </div>
    )
  }

  if (error || !interaction) {
    return (
      <div className="flex items-center justify-center h-full text-red-400">
        <div className="text-center">
          <AlertCircle className="w-12 h-12 mx-auto mb-3" />
          <p>Failed to load interaction details</p>
          <Button variant="outline" size="sm" className="mt-2" onClick={refetch}>
            Retry
          </Button>
        </div>
      </div>
    )
  }

  // Group steps by component for timeline
  const steps = interaction.steps || []

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="p-4 border-b border-gray-700">
        <div className="flex items-start justify-between">
          <div>
            <h3 className="text-lg font-semibold text-gray-200">{interaction.action_name}</h3>
            <div className="flex items-center gap-2 mt-1">
              <StatusBadge status={interaction.status} />
              {interaction.action_category && (
                <Badge variant="outline" className="text-xs">
                  {interaction.action_category}
                </Badge>
              )}
            </div>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={onDownloadBundle}
            disabled={isDownloading}
          >
            {isDownloading ? (
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            ) : (
              <Download className="w-4 h-4 mr-2" />
            )}
            Download Bundle
          </Button>
        </div>

        {/* Metadata */}
        <div className="grid grid-cols-2 gap-x-4 gap-y-1 mt-4 text-xs text-gray-500">
          <div>
            <span className="text-gray-600">Started:</span>{' '}
            {formatDate(interaction.started_at)} {formatTime(interaction.started_at)}
          </div>
          <div>
            <span className="text-gray-600">Duration:</span>{' '}
            {formatDuration(interaction.duration_ms)}
          </div>
          <div>
            <span className="text-gray-600">Steps:</span> {interaction.step_count}
          </div>
          <div>
            <span className="text-gray-600">Errors:</span> {interaction.error_count}
          </div>
          <div className="col-span-2">
            <span className="text-gray-600">Correlation ID:</span>{' '}
            <code className="text-gray-400 bg-gray-800 px-1 rounded text-[10px]">
              {interaction.correlation_id}
            </code>
          </div>
          {interaction.page && (
            <div className="col-span-2">
              <span className="text-gray-600">Page:</span> {interaction.page}
            </div>
          )}
        </div>

        {/* Error summary */}
        {interaction.error_summary && (
          <div className="mt-3 p-2 bg-red-500/10 border border-red-500/30 rounded text-sm text-red-400">
            <AlertCircle className="w-4 h-4 inline-block mr-2" />
            {interaction.error_summary}
          </div>
        )}
      </div>

      {/* Timeline */}
      <ScrollArea className="flex-1">
        <div className="p-4">
          <h4 className="text-sm font-medium text-gray-400 mb-4">
            Timeline ({steps.length} steps)
          </h4>
          {steps.length === 0 ? (
            <p className="text-gray-500 text-sm">No steps recorded</p>
          ) : (
            <div className="space-y-1">
              {steps.map((step) => (
                <StepTimelineItem key={step.step_id} step={step} />
              ))}
            </div>
          )}
        </div>
      </ScrollArea>
    </div>
  )
}

// Main Logs page
export default function LogsPage() {
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [selectedInteractionId, setSelectedInteractionId] = useState<string | null>(null)
  const [isDownloading, setIsDownloading] = useState(false)

  // Build filters
  const filters = useMemo(() => {
    const f: { action_name?: string; status?: StepStatus } = {}
    if (searchQuery) f.action_name = searchQuery
    if (statusFilter && statusFilter !== 'all') f.status = statusFilter as StepStatus
    return f
  }, [searchQuery, statusFilter])

  const {
    interactions,
    total,
    loading,
    error,
    refetch,
    loadMore,
    hasMore,
  } = useInteractionHistory({
    limit: 50,
    filters,
    autoRefresh: true,
    refreshInterval: 5000,
  })

  // Handle bundle download
  const handleDownloadBundle = async () => {
    if (!selectedInteractionId) return

    setIsDownloading(true)
    try {
      const response = await fetch(
        `/api/uelr/interactions/${selectedInteractionId}/bundle`
      )
      if (!response.ok) {
        throw new Error('Failed to download bundle')
      }

      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `uelr-bundle-${selectedInteractionId}.zip`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (error) {
      console.error('Failed to download bundle:', error)
    } finally {
      setIsDownloading(false)
    }
  }

  return (
    <div className="h-full flex flex-col">
      {/* Page header */}
      <div className="p-6 pb-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-100">Interaction Logs</h1>
            <p className="text-gray-500 text-sm mt-1">
              End-to-end trace of user actions across frontend, backend, and worker
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={() => refetch()} disabled={loading}>
            <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
        </div>

        {/* Filters */}
        <div className="flex items-center gap-4 mt-4">
          <div className="relative flex-1 max-w-xs">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
            <Input
              placeholder="Search actions..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9 bg-gray-900 border-gray-700"
            />
          </div>
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="w-32 bg-gray-900 border-gray-700">
              <SelectValue placeholder="Status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Status</SelectItem>
              <SelectItem value="success">Success</SelectItem>
              <SelectItem value="error">Error</SelectItem>
              <SelectItem value="pending">Pending</SelectItem>
              <SelectItem value="cancelled">Cancelled</SelectItem>
            </SelectContent>
          </Select>
          <div className="text-sm text-gray-500">
            {total} interaction{total !== 1 ? 's' : ''}
          </div>
        </div>
      </div>

      {/* Main content */}
      <div className="flex-1 flex min-h-0 px-6 pb-6 gap-4">
        {/* Interaction list */}
        <Card className="w-80 flex flex-col bg-gray-900/50 border-gray-700">
          <CardHeader className="py-3 px-4 border-b border-gray-700">
            <CardTitle className="text-sm font-medium text-gray-300">
              Recent Interactions
            </CardTitle>
          </CardHeader>
          <ScrollArea className="flex-1">
            {loading && interactions.length === 0 ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="w-6 h-6 animate-spin text-blue-500" />
              </div>
            ) : error ? (
              <div className="p-4 text-red-400 text-sm text-center">
                <AlertCircle className="w-6 h-6 mx-auto mb-2" />
                Failed to load interactions
              </div>
            ) : interactions.length === 0 ? (
              <div className="p-4 text-gray-500 text-sm text-center">
                <Activity className="w-6 h-6 mx-auto mb-2 opacity-50" />
                No interactions recorded yet
              </div>
            ) : (
              <>
                {interactions.map((interaction) => (
                  <InteractionListItem
                    key={interaction.interaction_id}
                    interaction={interaction}
                    isSelected={interaction.interaction_id === selectedInteractionId}
                    onClick={() => setSelectedInteractionId(interaction.interaction_id)}
                  />
                ))}
                {hasMore && (
                  <div className="p-4">
                    <Button
                      variant="outline"
                      size="sm"
                      className="w-full"
                      onClick={loadMore}
                      disabled={loading}
                    >
                      {loading ? (
                        <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      ) : null}
                      Load More
                    </Button>
                  </div>
                )}
              </>
            )}
          </ScrollArea>
        </Card>

        {/* Detail panel */}
        <Card className="flex-1 bg-gray-900/50 border-gray-700 overflow-hidden">
          <InteractionDetailPanel
            interactionId={selectedInteractionId}
            onDownloadBundle={handleDownloadBundle}
            isDownloading={isDownloading}
          />
        </Card>
      </div>
    </div>
  )
}
