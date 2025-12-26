import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Play, Square, RefreshCw, Settings2, Info } from 'lucide-react'
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
    refetchInterval: 5000, // Poll every 5 seconds
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
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Training</h1>
        <p className="text-muted-foreground">
          Train LoRA models for your characters
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Training Configuration */}
        <Card>
          <CardHeader>
            <CardTitle>New Training Job</CardTitle>
            <CardDescription>
              Configure and start LoRA training for a character
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Character Selection */}
            <div className="space-y-2">
              <Label>Select Character</Label>
              {eligibleCharacters.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No characters with training images. Upload images first.
                </p>
              ) : (
                <select
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  value={selectedCharacter}
                  onChange={(e) => setSelectedCharacter(e.target.value)}
                >
                  <option value="">Choose a character...</option>
                  {eligibleCharacters.map((char) => (
                    <option key={char.id} value={char.id}>
                      {char.name} ({char.image_count} images)
                    </option>
                  ))}
                </select>
              )}
            </div>

            {selectedChar && (
              <div className="rounded-lg bg-muted p-3 text-sm">
                <p><strong>Trigger word:</strong> {selectedChar.trigger_word}</p>
                <p><strong>Images:</strong> {selectedChar.image_count}</p>
              </div>
            )}

            {/* Basic Settings */}
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="steps">
                  Training Steps
                  <span className="ml-1 text-xs text-muted-foreground">(100-10000)</span>
                </Label>
                <Input
                  id="steps"
                  type="number"
                  min={100}
                  max={10000}
                  value={config.steps}
                  onChange={(e) => setConfig({ ...config, steps: parseInt(e.target.value) || 1000 })}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="resolution">Resolution</Label>
                <select
                  id="resolution"
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  value={config.resolution}
                  onChange={(e) => setConfig({ ...config, resolution: parseInt(e.target.value) })}
                >
                  <option value={512}>512px</option>
                  <option value={768}>768px</option>
                  <option value={1024}>1024px (recommended)</option>
                </select>
              </div>
            </div>

            {/* Advanced Settings Toggle */}
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setShowAdvanced(!showAdvanced)}
              className="text-muted-foreground"
            >
              <Settings2 className="mr-2 h-4 w-4" />
              {showAdvanced ? 'Hide' : 'Show'} Advanced Settings
            </Button>

            {/* Advanced Settings */}
            {showAdvanced && (
              <div className="grid gap-4 md:grid-cols-2 border-t pt-4">
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
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                    value={config.lora_rank}
                    onChange={(e) => setConfig({ ...config, lora_rank: parseInt(e.target.value) })}
                  >
                    <option value={4}>4 (smaller file, less detail)</option>
                    <option value={8}>8</option>
                    <option value={16}>16 (recommended)</option>
                    <option value={32}>32</option>
                    <option value={64}>64 (larger file, more detail)</option>
                  </select>
                </div>
              </div>
            )}
          </CardContent>
          <CardFooter>
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

        {/* Info Card */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Info className="h-5 w-5" />
              Training Tips
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-sm">
            <div>
              <h4 className="font-medium mb-1">Recommended Settings</h4>
              <ul className="list-disc list-inside text-muted-foreground space-y-1">
                <li>10-20 high-quality images of the subject</li>
                <li>1000-1500 steps for good results</li>
                <li>Consistent lighting and backgrounds</li>
              </ul>
            </div>
            <div>
              <h4 className="font-medium mb-1">Image Guidelines</h4>
              <ul className="list-disc list-inside text-muted-foreground space-y-1">
                <li>Clear, well-lit photos</li>
                <li>Various angles and expressions</li>
                <li>No other people in the frame</li>
                <li>Square or close-to-square aspect ratio</li>
              </ul>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Active Jobs */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-semibold">Training Jobs</h2>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => queryClient.invalidateQueries({ queryKey: ['training-jobs'] })}
          >
            <RefreshCw className="mr-2 h-4 w-4" />
            Refresh
          </Button>
        </div>

        {jobsLoading ? (
          <div className="flex items-center justify-center h-32">
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary"></div>
          </div>
        ) : jobs.length === 0 ? (
          <Card className="p-8 text-center text-muted-foreground">
            No training jobs yet. Start one above!
          </Card>
        ) : (
          <div className="space-y-4">
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
  const statusColors: Record<string, string> = {
    pending: 'bg-yellow-100 text-yellow-800',
    queued: 'bg-blue-100 text-blue-800',
    running: 'bg-green-100 text-green-800',
    completed: 'bg-green-100 text-green-800',
    failed: 'bg-red-100 text-red-800',
    cancelled: 'bg-gray-100 text-gray-800',
  }

  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="font-medium">{character?.name || job.character_id}</h3>
            <p className="text-sm text-muted-foreground">Job ID: {job.id}</p>
          </div>
          <span className={`text-xs px-2 py-1 rounded-full ${statusColors[job.status]}`}>
            {job.status}
          </span>
        </div>

        {(job.status === 'running' || job.status === 'queued') && (
          <>
            <Progress value={job.progress} className="mb-2" />
            <div className="flex items-center justify-between text-sm text-muted-foreground">
              <span>Step {job.current_step} / {job.total_steps}</span>
              <span>{job.progress.toFixed(1)}%</span>
            </div>
          </>
        )}

        {job.error_message && (
          <p className="text-sm text-destructive mt-2">{job.error_message}</p>
        )}

        {(job.status === 'running' || job.status === 'queued' || job.status === 'pending') && (
          <Button
            variant="outline"
            size="sm"
            className="mt-4"
            onClick={onCancel}
          >
            <Square className="mr-2 h-4 w-4" />
            Cancel
          </Button>
        )}
      </CardContent>
    </Card>
  )
}
