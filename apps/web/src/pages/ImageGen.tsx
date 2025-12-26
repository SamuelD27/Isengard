import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Wand2, Settings2, Image } from 'lucide-react'
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
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Image Generation</h1>
        <p className="text-muted-foreground">
          Generate images using your trained LoRA models
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Generation Form */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Generate Images</CardTitle>
            <CardDescription>
              Write a prompt and optionally select a character LoRA
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Prompt */}
            <div className="space-y-2">
              <Label htmlFor="prompt">Prompt</Label>
              <textarea
                id="prompt"
                className="flex min-h-[100px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                placeholder="Describe what you want to generate..."
                value={config.prompt}
                onChange={(e) => setConfig({ ...config, prompt: e.target.value })}
              />
              {selectedChar && (
                <p className="text-xs text-muted-foreground">
                  Tip: Include the trigger word "<code className="bg-muted px-1 rounded">{selectedChar.trigger_word}</code>" in your prompt
                </p>
              )}
            </div>

            {/* Character LoRA Selection */}
            <div className="space-y-2">
              <Label>Character LoRA (optional)</Label>
              {trainedCharacters.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No trained LoRAs available. Train a character first.
                </p>
              ) : (
                <select
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  value={config.lora_id || ''}
                  onChange={(e) => setConfig({ ...config, lora_id: e.target.value || null })}
                >
                  <option value="">No LoRA (base model only)</option>
                  {trainedCharacters.map((char) => (
                    <option key={char.id} value={char.id}>
                      {char.name} ({char.trigger_word})
                    </option>
                  ))}
                </select>
              )}
            </div>

            {/* Basic Settings Row */}
            <div className="grid gap-4 md:grid-cols-3">
              <div className="space-y-2">
                <Label htmlFor="size">Size</Label>
                <select
                  id="size"
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  value={`${config.width}x${config.height}`}
                  onChange={(e) => {
                    const [w, h] = e.target.value.split('x').map(Number)
                    setConfig({ ...config, width: w, height: h })
                  }}
                >
                  <option value="1024x1024">1024 x 1024 (Square)</option>
                  <option value="1024x768">1024 x 768 (Landscape)</option>
                  <option value="768x1024">768 x 1024 (Portrait)</option>
                  <option value="512x512">512 x 512 (Small)</option>
                </select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="count">Count</Label>
                <select
                  id="count"
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
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
                  <Label htmlFor="strength">LoRA Strength</Label>
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
              <div className="space-y-4 border-t pt-4">
                <div className="space-y-2">
                  <Label htmlFor="negative">Negative Prompt</Label>
                  <textarea
                    id="negative"
                    className="flex min-h-[60px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                    placeholder="What to avoid in the image..."
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
                    <Label htmlFor="cfg">Guidance Scale</Label>
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
                    <Label htmlFor="seed">Seed (optional)</Label>
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
          <CardFooter>
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

        {/* Recent Generations */}
        <Card>
          <CardHeader>
            <CardTitle>Recent Generations</CardTitle>
          </CardHeader>
          <CardContent>
            {jobs.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-8">
                No generations yet
              </p>
            ) : (
              <div className="space-y-4">
                {jobs.slice(0, 5).map((job) => (
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
  const statusColors: Record<string, string> = {
    pending: 'bg-yellow-100 text-yellow-800',
    queued: 'bg-blue-100 text-blue-800',
    running: 'bg-green-100 text-green-800',
    completed: 'bg-green-100 text-green-800',
    failed: 'bg-red-100 text-red-800',
  }

  return (
    <div className="border rounded-lg p-3">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs text-muted-foreground">{job.id}</span>
        <span className={`text-xs px-2 py-0.5 rounded-full ${statusColors[job.status]}`}>
          {job.status}
        </span>
      </div>
      <p className="text-sm truncate mb-2">{job.config.prompt}</p>
      {job.status === 'running' && (
        <Progress value={job.progress} className="h-2" />
      )}
      {job.status === 'completed' && job.output_paths.length > 0 && (
        <div className="flex items-center gap-2 mt-2">
          <Image className="h-4 w-4 text-muted-foreground" />
          <span className="text-xs text-muted-foreground">
            {job.output_paths.length} image(s)
          </span>
        </div>
      )}
    </div>
  )
}
