/**
 * Checkpoints Panel Component
 *
 * Displays training checkpoints with download functionality.
 * Polls for new checkpoints during active training.
 */

import { useQuery } from '@tanstack/react-query'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Download, RefreshCw, HardDrive, Loader2, AlertCircle } from 'lucide-react'

interface Checkpoint {
  name: string
  path: string
  size_bytes: number
  created_at: string
  step: number | null
  url: string
}

interface CheckpointsPanelProps {
  jobId: string
  isActive: boolean
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}

function formatTimestamp(timestamp: string): string {
  return new Date(timestamp).toLocaleTimeString()
}

export function CheckpointsPanel({ jobId, isActive }: CheckpointsPanelProps) {
  const {
    data,
    isLoading,
    error,
    refetch,
    isFetching,
  } = useQuery({
    queryKey: ['job-checkpoints', jobId],
    queryFn: async () => {
      const response = await fetch(`/api/jobs/${jobId}/checkpoints`)
      if (!response.ok) {
        throw new Error(`Failed to fetch checkpoints: ${response.statusText}`)
      }
      return response.json() as Promise<{ job_id: string; checkpoints: Checkpoint[]; total_count: number }>
    },
    enabled: !!jobId,
    refetchInterval: isActive ? 30000 : false, // Poll every 30s during training
    staleTime: 10000,
  })

  const checkpoints = data?.checkpoints || []

  const handleDownload = (checkpoint: Checkpoint) => {
    window.open(checkpoint.url, '_blank')
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm flex items-center gap-2">
            <HardDrive className="h-4 w-4" />
            Checkpoints ({checkpoints.length})
          </CardTitle>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => refetch()}
            disabled={isFetching}
            title="Refresh checkpoints"
          >
            <RefreshCw className={`h-3 w-3 ${isFetching ? 'animate-spin' : ''}`} />
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : error ? (
          <div className="flex items-center gap-2 text-sm text-destructive py-4">
            <AlertCircle className="h-4 w-4" />
            <span>Failed to load checkpoints</span>
          </div>
        ) : checkpoints.length === 0 ? (
          <p className="text-sm text-muted-foreground py-4">
            {isActive
              ? 'No checkpoints yet. Checkpoints are saved at configured intervals during training.'
              : 'No checkpoints were saved for this training job.'}
          </p>
        ) : (
          <div className="space-y-2">
            {checkpoints.map((checkpoint) => (
              <div
                key={checkpoint.name}
                className="flex items-center justify-between p-2 rounded bg-muted/30 hover:bg-muted/50 transition-colors"
              >
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">{checkpoint.name}</p>
                  <div className="flex gap-3 text-xs text-muted-foreground">
                    {checkpoint.step !== null && (
                      <span>Step {checkpoint.step}</span>
                    )}
                    <span>{formatBytes(checkpoint.size_bytes)}</span>
                    <span>{formatTimestamp(checkpoint.created_at)}</span>
                  </div>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleDownload(checkpoint)}
                  title={`Download ${checkpoint.name}`}
                >
                  <Download className="h-3 w-3" />
                </Button>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
