import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Play, Square, RefreshCw, ChevronDown, ChevronUp, Info } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Progress } from '@/components/ui/progress'
import { api, Character, TrainingJob, TrainingConfig } from '@/lib/api'

const defaultConfig: TrainingConfig = {
  method: 'lora',
  steps: 1000,
  learning_rate: 0.0001,
  batch_size: 1,
  resolution: 1024,
  lora_rank: 16,
}

export default function TrainingPage() {
  const queryClient = useQueryClient()
  const [selectedCharacter, setSelectedCharacter] = useState<string>('')
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [config, setConfig] = useState<TrainingConfig>(defaultConfig)

  const { data: characters = [] } = useQuery({
    queryKey: ['characters'],
    queryFn: api.listCharacters,
  })

  const { data: jobs = [], isLoading: jobsLoading } = useQuery({
    queryKey: ['training-jobs'],
    queryFn: () => api.listTrainingJobs(),
    refetchInterval: 5000,
  })

  const startMutation = useMutation({
    mutationFn: ({ characterId, config }: { characterId: string; config: TrainingConfig }) =>
      api.startTraining(characterId, config),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['training-jobs'] })
    },
  })

  const cancelMutation = useMutation({
    mutationFn: api.cancelTraining,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['training-jobs'] })
    },
  })

  const handleStartTraining = () => {
    if (selectedCharacter) {
      startMutation.mutate({ characterId: selectedCharacter, config })
    }
  }

  const eligibleCharacters = characters.filter(c => c.image_count > 0)
  const selectedChar = characters.find(c => c.id === selectedCharacter)

  return (
    <div className="space-y-6 fade-in">
      {/* Page Header */}
      <div>
        <p className="text-sm text-muted-foreground">
          Train LoRA models for your characters
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-5">
        {/* Training Configuration - 3 cols */}
        <Card className="lg:col-span-3">
          <CardHeader>
            <CardTitle>New Training Job</CardTitle>
            <CardDescription>Configure LoRA training parameters</CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            {/* Character Selection */}
            <div className="space-y-2">
              <Label>Character</Label>
              {eligibleCharacters.length === 0 ? (
                <p className="text-sm text-muted-foreground py-2">
                  No characters with training images available
                </p>
              ) : (
                <select
                  className="flex h-9 w-full rounded-md border border-border bg-input px-3 py-2 text-sm text-foreground focus:outline-none focus:border-accent"
                  value={selectedCharacter}
                  onChange={(e) => setSelectedCharacter(e.target.value)}
                >
                  <option value="">Select character...</option>
                  {eligibleCharacters.map((char) => (
                    <option key={char.id} value={char.id}>
                      {char.name} ({char.image_count} images)
                    </option>
                  ))}
                </select>
              )}
            </div>

            {selectedChar && (
              <div className="rounded-md bg-muted p-3 text-sm space-y-1">
                <p className="text-foreground">
                  <span className="text-muted-foreground">Trigger:</span>{' '}
                  <code className="text-accent">{selectedChar.trigger_word}</code>
                </p>
                <p className="text-foreground">
                  <span className="text-muted-foreground">Images:</span> {selectedChar.image_count}
                </p>
              </div>
            )}

            {/* Basic Settings */}
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="steps">Training Steps</Label>
                <Input
                  id="steps"
                  type="number"
                  min={100}
                  max={10000}
                  value={config.steps}
                  onChange={(e) => setConfig({ ...config, steps: parseInt(e.target.value) || 1000 })}
                />
                <p className="text-xs text-muted-foreground">100-10000 steps</p>
              </div>
              <div className="space-y-2">
                <Label htmlFor="resolution">Resolution</Label>
                <select
                  id="resolution"
                  className="flex h-9 w-full rounded-md border border-border bg-input px-3 py-2 text-sm text-foreground focus:outline-none focus:border-accent"
                  value={config.resolution}
                  onChange={(e) => setConfig({ ...config, resolution: parseInt(e.target.value) })}
                >
                  <option value={512}>512px</option>
                  <option value={768}>768px</option>
                  <option value={1024}>1024px</option>
                </select>
              </div>
            </div>

            {/* Advanced Toggle */}
            <button
              onClick={() => setShowAdvanced(!showAdvanced)}
              className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              {showAdvanced ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
              Advanced Settings
            </button>

            {/* Advanced Settings */}
            {showAdvanced && (
              <div className="grid gap-4 md:grid-cols-2 pt-2 border-t border-border">
                <div className="space-y-2">
                  <Label htmlFor="lr">Learning Rate</Label>
                  <Input
                    id="lr"
                    type="number"
                    step="0.00001"
                    min={0.000001}
                    max={0.01}
                    value={config.learning_rate}
                    onChange={(e) => setConfig({ ...config, learning_rate: parseFloat(e.target.value) })}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="rank">LoRA Rank</Label>
                  <select
                    id="rank"
                    className="flex h-9 w-full rounded-md border border-border bg-input px-3 py-2 text-sm text-foreground focus:outline-none focus:border-accent"
                    value={config.lora_rank}
                    onChange={(e) => setConfig({ ...config, lora_rank: parseInt(e.target.value) })}
                  >
                    <option value={4}>4 (smaller)</option>
                    <option value={8}>8</option>
                    <option value={16}>16 (default)</option>
                    <option value={32}>32</option>
                    <option value={64}>64 (larger)</option>
                  </select>
                </div>
              </div>
            )}
          </CardContent>
          <CardFooter className="border-t border-border pt-5">
            <Button
              className="w-full"
              disabled={!selectedCharacter || startMutation.isPending}
              onClick={handleStartTraining}
            >
              <Play className="mr-2 h-4 w-4" />
              {startMutation.isPending ? 'Starting...' : 'Start Training'}
            </Button>
          </CardFooter>
        </Card>

        {/* Tips - 2 cols */}
        <Card className="lg:col-span-2 h-fit">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Info className="h-4 w-4 text-accent" />
              Training Tips
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-sm">
            <div>
              <h4 className="font-medium text-foreground mb-1">Recommended</h4>
              <ul className="space-y-1 text-muted-foreground">
                <li>10-20 high-quality images</li>
                <li>1000-1500 training steps</li>
                <li>Consistent lighting</li>
              </ul>
            </div>
            <div>
              <h4 className="font-medium text-foreground mb-1">Image Guidelines</h4>
              <ul className="space-y-1 text-muted-foreground">
                <li>Clear, well-lit photos</li>
                <li>Various angles & expressions</li>
                <li>No other people visible</li>
              </ul>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Training Jobs */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-medium text-foreground">Jobs</h2>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => queryClient.invalidateQueries({ queryKey: ['training-jobs'] })}
          >
            <RefreshCw className="h-4 w-4" />
          </Button>
        </div>

        {jobsLoading ? (
          <div className="flex items-center justify-center h-24">
            <div className="animate-spin rounded-full h-5 w-5 border-2 border-accent border-t-transparent" />
          </div>
        ) : jobs.length === 0 ? (
          <Card className="border-dashed">
            <CardContent className="py-8 text-center text-sm text-muted-foreground">
              No training jobs yet
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-3">
            {jobs.map((job) => (
              <TrainingJobCard
                key={job.id}
                job={job}
                character={characters.find(c => c.id === job.character_id)}
                onCancel={() => cancelMutation.mutate(job.id)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

interface TrainingJobCardProps {
  job: TrainingJob
  character?: Character
  onCancel: () => void
}

function TrainingJobCard({ job, character, onCancel }: TrainingJobCardProps) {
  const statusClasses: Record<string, string> = {
    pending: 'status-badge status-pending',
    queued: 'status-badge status-running',
    running: 'status-badge status-running',
    completed: 'status-badge status-success',
    failed: 'status-badge status-error',
    cancelled: 'status-badge status-pending',
  }

  return (
    <Card>
      <CardContent className="py-4">
        <div className="flex items-center justify-between mb-3">
          <div className="min-w-0">
            <h3 className="font-medium text-foreground truncate">
              {character?.name || 'Unknown'}
            </h3>
            <p className="text-xs text-muted-foreground font-mono">{job.id}</p>
          </div>
          <span className={statusClasses[job.status]}>{job.status}</span>
        </div>

        {(job.status === 'running' || job.status === 'queued') && (
          <div className="space-y-2">
            <Progress value={job.progress} />
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>Step {job.current_step} / {job.total_steps}</span>
              <span>{job.progress.toFixed(0)}%</span>
            </div>
          </div>
        )}

        {job.error_message && (
          <p className="text-sm text-destructive mt-2">{job.error_message}</p>
        )}

        {['running', 'queued', 'pending'].includes(job.status) && (
          <Button variant="outline" size="sm" className="mt-3" onClick={onCancel}>
            <Square className="mr-2 h-3.5 w-3.5" />
            Cancel
          </Button>
        )}
      </CardContent>
    </Card>
  )
}
