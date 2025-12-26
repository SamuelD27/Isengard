import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Wand2, ChevronDown, ChevronUp, Image } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Progress } from '@/components/ui/progress'
import { api, GenerationConfig, GenerationJob } from '@/lib/api'

const defaultConfig: GenerationConfig = {
  prompt: '',
  negative_prompt: 'blurry, low quality, distorted',
  width: 1024,
  height: 1024,
  steps: 30,
  guidance_scale: 7.5,
  seed: null,
  lora_id: null,
  lora_strength: 0.8,
}

export default function ImageGenPage() {
  const queryClient = useQueryClient()
  const [config, setConfig] = useState<GenerationConfig>(defaultConfig)
  const [count, setCount] = useState(1)
  const [showAdvanced, setShowAdvanced] = useState(false)

  const { data: characters = [] } = useQuery({
    queryKey: ['characters'],
    queryFn: api.listCharacters,
  })

  const { data: jobs = [] } = useQuery({
    queryKey: ['generation-jobs'],
    queryFn: () => api.listGenerationJobs(10),
    refetchInterval: 3000,
  })

  const generateMutation = useMutation({
    mutationFn: ({ config, count }: { config: GenerationConfig; count: number }) =>
      api.generateImages(config, count),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['generation-jobs'] })
    },
  })

  const handleGenerate = () => {
    if (config.prompt.trim()) {
      generateMutation.mutate({ config, count })
    }
  }

  const trainedCharacters = characters.filter(c => c.lora_path)
  const selectedChar = characters.find(c => c.id === config.lora_id)

  return (
    <div className="space-y-6 fade-in">
      {/* Page Header */}
      <div>
        <p className="text-sm text-muted-foreground">
          Create images with trained LoRA models
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Generation Form - 2 cols */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Generate Images</CardTitle>
            <CardDescription>Write a prompt and configure settings</CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            {/* Prompt */}
            <div className="space-y-2">
              <Label htmlFor="prompt">Prompt</Label>
              <textarea
                id="prompt"
                className="flex min-h-[100px] w-full rounded-md border border-border bg-input px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-accent resize-none"
                placeholder="Describe what you want to generate..."
                value={config.prompt}
                onChange={(e) => setConfig({ ...config, prompt: e.target.value })}
              />
              {selectedChar && (
                <p className="text-xs text-muted-foreground">
                  Include trigger word: <code className="text-accent">{selectedChar.trigger_word}</code>
                </p>
              )}
            </div>

            {/* LoRA Selection */}
            <div className="space-y-2">
              <Label>Character LoRA</Label>
              {trainedCharacters.length === 0 ? (
                <p className="text-sm text-muted-foreground py-1">
                  No trained LoRAs available
                </p>
              ) : (
                <select
                  className="flex h-9 w-full rounded-md border border-border bg-input px-3 py-2 text-sm text-foreground focus:outline-none focus:border-accent"
                  value={config.lora_id || ''}
                  onChange={(e) => setConfig({ ...config, lora_id: e.target.value || null })}
                >
                  <option value="">Base model only</option>
                  {trainedCharacters.map((char) => (
                    <option key={char.id} value={char.id}>
                      {char.name} ({char.trigger_word})
                    </option>
                  ))}
                </select>
              )}
            </div>

            {/* Basic Settings */}
            <div className="grid gap-4 md:grid-cols-3">
              <div className="space-y-2">
                <Label htmlFor="size">Size</Label>
                <select
                  id="size"
                  className="flex h-9 w-full rounded-md border border-border bg-input px-3 py-2 text-sm text-foreground focus:outline-none focus:border-accent"
                  value={`${config.width}x${config.height}`}
                  onChange={(e) => {
                    const [w, h] = e.target.value.split('x').map(Number)
                    setConfig({ ...config, width: w, height: h })
                  }}
                >
                  <option value="1024x1024">1024x1024</option>
                  <option value="1024x768">1024x768</option>
                  <option value="768x1024">768x1024</option>
                  <option value="512x512">512x512</option>
                </select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="count">Count</Label>
                <select
                  id="count"
                  className="flex h-9 w-full rounded-md border border-border bg-input px-3 py-2 text-sm text-foreground focus:outline-none focus:border-accent"
                  value={count}
                  onChange={(e) => setCount(parseInt(e.target.value))}
                >
                  <option value={1}>1 image</option>
                  <option value={2}>2 images</option>
                  <option value={4}>4 images</option>
                </select>
              </div>
              {config.lora_id && (
                <div className="space-y-2">
                  <Label htmlFor="strength">Strength</Label>
                  <Input
                    id="strength"
                    type="number"
                    step="0.1"
                    min={0}
                    max={1.5}
                    value={config.lora_strength}
                    onChange={(e) => setConfig({ ...config, lora_strength: parseFloat(e.target.value) })}
                  />
                </div>
              )}
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
              <div className="space-y-4 pt-2 border-t border-border">
                <div className="space-y-2">
                  <Label htmlFor="negative">Negative Prompt</Label>
                  <textarea
                    id="negative"
                    className="flex min-h-[60px] w-full rounded-md border border-border bg-input px-3 py-2 text-sm text-foreground focus:outline-none focus:border-accent resize-none"
                    placeholder="What to avoid..."
                    value={config.negative_prompt}
                    onChange={(e) => setConfig({ ...config, negative_prompt: e.target.value })}
                  />
                </div>
                <div className="grid gap-4 md:grid-cols-3">
                  <div className="space-y-2">
                    <Label htmlFor="steps">Steps</Label>
                    <Input
                      id="steps"
                      type="number"
                      min={1}
                      max={100}
                      value={config.steps}
                      onChange={(e) => setConfig({ ...config, steps: parseInt(e.target.value) })}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="cfg">Guidance</Label>
                    <Input
                      id="cfg"
                      type="number"
                      step="0.5"
                      min={1}
                      max={20}
                      value={config.guidance_scale}
                      onChange={(e) => setConfig({ ...config, guidance_scale: parseFloat(e.target.value) })}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="seed">Seed</Label>
                    <Input
                      id="seed"
                      type="number"
                      placeholder="Random"
                      value={config.seed ?? ''}
                      onChange={(e) => setConfig({ ...config, seed: e.target.value ? parseInt(e.target.value) : null })}
                    />
                  </div>
                </div>
              </div>
            )}
          </CardContent>
          <CardFooter className="border-t border-border pt-5">
            <Button
              className="w-full"
              disabled={!config.prompt.trim() || generateMutation.isPending}
              onClick={handleGenerate}
            >
              <Wand2 className="mr-2 h-4 w-4" />
              {generateMutation.isPending ? 'Generating...' : 'Generate'}
            </Button>
          </CardFooter>
        </Card>

        {/* Recent Jobs - 1 col */}
        <Card>
          <CardHeader>
            <CardTitle>Recent</CardTitle>
          </CardHeader>
          <CardContent>
            {jobs.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-8">
                No generations yet
              </p>
            ) : (
              <div className="space-y-3">
                {jobs.slice(0, 6).map((job) => (
                  <GenerationJobItem key={job.id} job={job} />
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

function GenerationJobItem({ job }: { job: GenerationJob }) {
  const statusClasses: Record<string, string> = {
    pending: 'status-badge status-pending',
    queued: 'status-badge status-running',
    running: 'status-badge status-running',
    completed: 'status-badge status-success',
    failed: 'status-badge status-error',
  }

  return (
    <div className="rounded-md border border-border p-3 space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-xs text-muted-foreground font-mono truncate max-w-[120px]">
          {job.id}
        </span>
        <span className={statusClasses[job.status]}>{job.status}</span>
      </div>
      <p className="text-sm text-foreground truncate">{job.config.prompt}</p>
      {job.status === 'running' && (
        <Progress value={job.progress} className="h-1.5" />
      )}
      {job.status === 'completed' && job.output_paths.length > 0 && (
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Image className="h-3.5 w-3.5" />
          <span>{job.output_paths.length} image(s)</span>
        </div>
      )}
    </div>
  )
}
