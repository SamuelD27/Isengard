/**
 * Ongoing Training Page
 *
 * Lists all training jobs that are currently in process (running/queued).
 * Each job shows:
 * - Character name
 * - Base model
 * - Current step / total steps
 * - Progress percentage
 * - Elapsed time
 * - ETA
 * - Progress bar
 *
 * Clicking a job opens its detail page.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  Play,
  ArrowLeft,
  RefreshCw,
  Clock,
  Loader2,
  Square,
  ChevronRight,
  Zap,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { api, TrainingJob, Character } from '@/lib/api'

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

function formatETA(seconds: number | null): string {
  if (seconds === null || seconds <= 0) return '--'
  return formatDuration(seconds)
}

export default function OngoingTrainingPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  // Fetch ongoing training jobs
  const { data: jobs = [], isLoading: jobsLoading } = useQuery({
    queryKey: ['training-jobs-ongoing'],
    queryFn: () => api.listOngoingTrainingJobs(),
    refetchInterval: 2000, // Refresh every 2 seconds for real-time updates
  })

  // Fetch characters for name lookup
  const { data: characters = [] } = useQuery({
    queryKey: ['characters'],
    queryFn: api.listCharacters,
  })

  const cancelMutation = useMutation({
    mutationFn: api.cancelTraining,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['training-jobs-ongoing'] })
      queryClient.invalidateQueries({ queryKey: ['training-jobs'] })
    },
  })

  const getCharacterName = (characterId: string): string => {
    const char = characters.find((c: Character) => c.id === characterId)
    return char?.name || 'Unknown'
  }

  const getStatusBadge = (status: string) => {
    const statusStyles: Record<string, string> = {
      pending: 'bg-yellow-500/20 text-yellow-400',
      queued: 'bg-blue-500/20 text-blue-400',
      running: 'bg-green-500/20 text-green-400',
    }
    return statusStyles[status] || 'bg-gray-500/20 text-gray-400'
  }

  return (
    <div className="space-y-6 fade-in">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate('/training')}
          >
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div>
            <h1 className="text-xl font-semibold text-foreground">Ongoing Training</h1>
            <p className="text-sm text-muted-foreground">
              {jobs.length} job{jobs.length !== 1 ? 's' : ''} in progress
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => queryClient.invalidateQueries({ queryKey: ['training-jobs-ongoing'] })}
          >
            <RefreshCw className="h-4 w-4" />
          </Button>
          <Button onClick={() => navigate('/training/start')}>
            <Play className="mr-2 h-4 w-4" />
            Start Training
          </Button>
        </div>
      </div>

      {/* Ongoing Jobs List */}
      {jobsLoading ? (
        <div className="flex items-center justify-center h-48">
          <div className="animate-spin rounded-full h-6 w-6 border-2 border-accent border-t-transparent" />
        </div>
      ) : jobs.length === 0 ? (
        <Card className="border-dashed">
          <CardContent className="py-16 text-center">
            <Zap className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
            <h3 className="text-lg font-medium text-foreground mb-2">
              No ongoing training jobs
            </h3>
            <p className="text-sm text-muted-foreground mb-6">
              Start a new training job to see it here
            </p>
            <Button onClick={() => navigate('/training/start')}>
              <Play className="mr-2 h-4 w-4" />
              Start Training
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {jobs.map((job: TrainingJob) => (
            <Card
              key={job.id}
              className="cursor-pointer hover:border-accent/50 transition-colors"
              onClick={() => navigate(`/training/${job.id}`)}
            >
              <CardContent className="py-4">
                <div className="flex items-start justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <div className="h-10 w-10 rounded-full bg-accent/20 flex items-center justify-center">
                      <Loader2 className="h-5 w-5 text-accent animate-spin" />
                    </div>
                    <div>
                      <h3 className="font-medium text-foreground flex items-center gap-2">
                        {getCharacterName(job.character_id)}
                        <Badge className={getStatusBadge(job.status)}>
                          {job.status}
                        </Badge>
                      </h3>
                      <div className="flex items-center gap-3 text-xs text-muted-foreground mt-1">
                        <span>{job.base_model || 'flux-dev'}</span>
                        <span>•</span>
                        <span>
                          {job.preset_name
                            ? job.preset_name.charAt(0).toUpperCase() + job.preset_name.slice(1)
                            : 'Custom'}
                        </span>
                        <span>•</span>
                        <span className="font-mono">{job.id}</span>
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => cancelMutation.mutate(job.id)}
                      disabled={cancelMutation.isPending}
                    >
                      <Square className="mr-2 h-3.5 w-3.5" />
                      Cancel
                    </Button>
                    <ChevronRight className="h-5 w-5 text-muted-foreground" />
                  </div>
                </div>

                {/* Progress Bar */}
                <div className="space-y-2">
                  <Progress value={job.progress} className="h-2" />
                  <div className="flex items-center justify-between text-sm">
                    <div className="flex items-center gap-4 text-muted-foreground">
                      <span>
                        Step <span className="text-foreground font-medium">{job.current_step}</span> / {job.total_steps}
                      </span>
                      {job.iteration_speed !== null && (
                        <>
                          <span>•</span>
                          <span>
                            <span className="text-foreground font-medium">{job.iteration_speed.toFixed(2)}</span> it/s
                          </span>
                        </>
                      )}
                      {job.current_loss !== null && (
                        <>
                          <span>•</span>
                          <span>
                            Loss: <span className="text-foreground font-medium">{job.current_loss.toFixed(4)}</span>
                          </span>
                        </>
                      )}
                    </div>
                    <span className="font-medium text-foreground">{job.progress.toFixed(1)}%</span>
                  </div>
                </div>

                {/* Time Info */}
                <div className="flex items-center gap-6 mt-3 text-xs text-muted-foreground">
                  <div className="flex items-center gap-1">
                    <Clock className="h-3 w-3" />
                    <span>Elapsed:</span>
                    <span className="text-foreground">
                      {job.elapsed_seconds ? formatDuration(job.elapsed_seconds) : '--'}
                    </span>
                  </div>
                  <div className="flex items-center gap-1">
                    <span>ETA:</span>
                    <span className="text-foreground">
                      {formatETA(job.eta_seconds)}
                    </span>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
