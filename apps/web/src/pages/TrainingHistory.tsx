/**
 * Training History Page
 *
 * Main training page showing ONLY successful (completed) training jobs.
 * Each job is clickable to view details.
 * Includes navigation to Start Training and Ongoing Training pages.
 */

import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  Play,
  RefreshCw,
  Clock,
  CheckCircle2,
  Loader2,
  Sparkles,
  ChevronRight,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
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

function formatDate(dateString: string): string {
  return new Date(dateString).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export default function TrainingHistoryPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  // Fetch only successful training jobs
  const { data: jobs = [], isLoading: jobsLoading } = useQuery({
    queryKey: ['training-jobs-successful'],
    queryFn: () => api.listSuccessfulTrainingJobs(),
    refetchInterval: 30000, // Refresh every 30s
  })

  // Fetch ongoing jobs count for the badge
  const { data: ongoingJobs = [] } = useQuery({
    queryKey: ['training-jobs-ongoing'],
    queryFn: () => api.listOngoingTrainingJobs(),
    refetchInterval: 5000,
  })

  // Fetch characters for name lookup
  const { data: characters = [] } = useQuery({
    queryKey: ['characters'],
    queryFn: api.listCharacters,
  })

  const getCharacterName = (characterId: string): string => {
    const char = characters.find((c: Character) => c.id === characterId)
    return char?.name || 'Unknown'
  }

  const calculateDuration = (job: TrainingJob): number | null => {
    if (!job.started_at || !job.completed_at) return null
    const start = new Date(job.started_at).getTime()
    const end = new Date(job.completed_at).getTime()
    return Math.floor((end - start) / 1000)
  }

  return (
    <div className="space-y-6 fade-in">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-foreground">Training History</h1>
          <p className="text-sm text-muted-foreground">
            View your completed LoRA training runs
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Button
            variant="outline"
            onClick={() => navigate('/training/ongoing')}
            className="relative"
          >
            <Loader2 className="mr-2 h-4 w-4" />
            Ongoing Training
            {ongoingJobs.length > 0 && (
              <Badge
                variant="secondary"
                className="ml-2 bg-accent text-accent-foreground"
              >
                {ongoingJobs.length}
              </Badge>
            )}
          </Button>
          <Button onClick={() => navigate('/training/start')}>
            <Play className="mr-2 h-4 w-4" />
            Start Training
          </Button>
        </div>
      </div>

      {/* Training History List */}
      {jobsLoading ? (
        <div className="flex items-center justify-center h-48">
          <div className="animate-spin rounded-full h-6 w-6 border-2 border-accent border-t-transparent" />
        </div>
      ) : jobs.length === 0 ? (
        <Card className="border-dashed">
          <CardContent className="py-16 text-center">
            <Sparkles className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
            <h3 className="text-lg font-medium text-foreground mb-2">
              No completed trainings yet
            </h3>
            <p className="text-sm text-muted-foreground mb-6">
              Start your first training to create a custom LoRA model
            </p>
            <Button onClick={() => navigate('/training/start')}>
              <Play className="mr-2 h-4 w-4" />
              Start Training
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          <div className="flex items-center justify-between px-1">
            <span className="text-sm text-muted-foreground">
              {jobs.length} successful training{jobs.length !== 1 ? 's' : ''}
            </span>
            <Button
              variant="ghost"
              size="sm"
              onClick={() =>
                queryClient.invalidateQueries({ queryKey: ['training-jobs-successful'] })
              }
            >
              <RefreshCw className="h-4 w-4" />
            </Button>
          </div>

          {jobs.map((job: TrainingJob) => {
            const duration = calculateDuration(job)
            return (
              <Card
                key={job.id}
                className="cursor-pointer hover:border-accent/50 transition-colors"
                onClick={() => navigate(`/training/${job.id}`)}
              >
                <CardContent className="py-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                      <div className="h-10 w-10 rounded-full bg-success/20 flex items-center justify-center">
                        <CheckCircle2 className="h-5 w-5 text-success" />
                      </div>
                      <div>
                        <h3 className="font-medium text-foreground">
                          {getCharacterName(job.character_id)}
                        </h3>
                        <div className="flex items-center gap-3 text-xs text-muted-foreground mt-1">
                          <span>{job.base_model || 'flux-dev'}</span>
                          <span>•</span>
                          <span>
                            {job.preset_name
                              ? job.preset_name.charAt(0).toUpperCase() +
                                job.preset_name.slice(1)
                              : 'Custom'}
                          </span>
                          <span>•</span>
                          <span>{job.total_steps} steps</span>
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-6">
                      <div className="text-right">
                        <p className="text-sm text-foreground">
                          {job.completed_at && formatDate(job.completed_at)}
                        </p>
                        <p className="text-xs text-muted-foreground flex items-center justify-end gap-1 mt-1">
                          <Clock className="h-3 w-3" />
                          {duration ? formatDuration(duration) : '--'}
                        </p>
                      </div>
                      <ChevronRight className="h-5 w-5 text-muted-foreground" />
                    </div>
                  </div>
                </CardContent>
              </Card>
            )
          })}
        </div>
      )}
    </div>
  )
}
