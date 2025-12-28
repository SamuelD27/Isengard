import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Wand2, ChevronDown, ChevronUp, Image, Settings2, Sparkles, Maximize2, Smile, ArrowUpRight, Loader2, Download, RefreshCw, AlertCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Progress } from '@/components/ui/progress'
import { api, GenerationConfig, GenerationJob, ImageCapabilities } from '@/lib/api'

// Aspect ratio presets
const ASPECT_RATIOS = [
  { label: '1:1 Square', ratio: 1, width: 1024, height: 1024 },
  { label: '4:5 Portrait', ratio: 0.8, width: 896, height: 1120 },
  { label: '3:4 Portrait', ratio: 0.75, width: 896, height: 1152 },
  { label: '9:16 Tall', ratio: 0.5625, width: 768, height: 1344 },
  { label: '5:4 Landscape', ratio: 1.25, width: 1120, height: 896 },
  { label: '4:3 Landscape', ratio: 1.333, width: 1152, height: 896 },
  { label: '16:9 Wide', ratio: 1.778, width: 1344, height: 768 },
]

// Quality tiers for resolution scaling
const QUALITY_TIERS = [
  { label: 'Draft (Fast)', multiplier: 0.75 },
  { label: 'Standard', multiplier: 1.0 },
  { label: 'High Quality', multiplier: 1.25 },
]

const defaultConfig: GenerationConfig = {
  prompt: '',
  negative_prompt: 'blurry, low quality, distorted, deformed, ugly, bad anatomy',
  width: 1024,
  height: 1024,
  steps: 20,
  guidance_scale: 3.5,
  seed: null,
  lora_id: null,
  lora_strength: 0.8,
  use_controlnet: false,
  use_ipadapter: false,
  use_facedetailer: false,
  use_upscale: false,
}

export default function ImageGenPage() {
  const queryClient = useQueryClient()
  const [config, setConfig] = useState<GenerationConfig>(defaultConfig)
  const [count, setCount] = useState(1)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [selectedAspect, setSelectedAspect] = useState(0)
  const [selectedQuality, setSelectedQuality] = useState(1)
  const [selectedJob, setSelectedJob] = useState<string | null>(null)

  const { data: characters = [] } = useQuery({
    queryKey: ['characters'],
    queryFn: api.listCharacters,
  })

  const { data: apiInfo } = useQuery({
    queryKey: ['api-info'],
    queryFn: api.info,
    staleTime: 60000, // Cache for 1 minute
  })

  // Extract image capabilities from API info
  const capabilities: ImageCapabilities | undefined = apiInfo?.image_generation

  const { data: jobs = [], refetch: refetchJobs } = useQuery({
    queryKey: ['generation-jobs'],
    queryFn: () => api.listGenerationJobs(20),
    refetchInterval: 3000,
  })

  const generateMutation = useMutation({
    mutationFn: ({ config, count }: { config: GenerationConfig; count: number }) =>
      api.generateImages(config, count),
    onSuccess: (job) => {
      queryClient.invalidateQueries({ queryKey: ['generation-jobs'] })
      setSelectedJob(job.id)
    },
  })

  const handleAspectChange = (index: number) => {
    setSelectedAspect(index)
    const aspect = ASPECT_RATIOS[index]
    const quality = QUALITY_TIERS[selectedQuality]
    setConfig({
      ...config,
      width: Math.round(aspect.width * quality.multiplier),
      height: Math.round(aspect.height * quality.multiplier),
    })
  }

  const handleQualityChange = (index: number) => {
    setSelectedQuality(index)
    const aspect = ASPECT_RATIOS[selectedAspect]
    const quality = QUALITY_TIERS[index]
    setConfig({
      ...config,
      width: Math.round(aspect.width * quality.multiplier),
      height: Math.round(aspect.height * quality.multiplier),
    })
  }

  const handleGenerate = () => {
    if (config.prompt.trim()) {
      generateMutation.mutate({ config, count })
    }
  }

  const trainedCharacters = characters.filter((c: { lora_path: string | null }) => c.lora_path)
  const selectedChar = characters.find((c: { id: string }) => c.id === config.lora_id)

  // Get currently selected job details
  const currentJob = jobs.find((j: GenerationJob) => j.id === selectedJob)

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
        <div className="lg:col-span-2 space-y-6">
          <Card>
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
                    Include trigger word: <code className="text-accent">{(selectedChar as { trigger_word: string }).trigger_word}</code>
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
                    {trainedCharacters.map((char: { id: string; name: string; trigger_word: string }) => (
                      <option key={char.id} value={char.id}>
                        {char.name} ({char.trigger_word})
                      </option>
                    ))}
                  </select>
                )}
              </div>

              {/* Aspect Ratio & Quality */}
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label>Aspect Ratio</Label>
                  <div className="grid grid-cols-4 gap-2">
                    {ASPECT_RATIOS.slice(0, 4).map((aspect, i) => (
                      <button
                        key={i}
                        onClick={() => handleAspectChange(i)}
                        className={`p-2 text-xs rounded-md border transition-colors ${
                          selectedAspect === i
                            ? 'border-accent bg-accent/10 text-accent'
                            : 'border-border hover:border-border-hover text-muted-foreground'
                        }`}
                      >
                        {aspect.label.split(' ')[0]}
                      </button>
                    ))}
                  </div>
                  <div className="grid grid-cols-3 gap-2">
                    {ASPECT_RATIOS.slice(4).map((aspect, i) => (
                      <button
                        key={i + 4}
                        onClick={() => handleAspectChange(i + 4)}
                        className={`p-2 text-xs rounded-md border transition-colors ${
                          selectedAspect === i + 4
                            ? 'border-accent bg-accent/10 text-accent'
                            : 'border-border hover:border-border-hover text-muted-foreground'
                        }`}
                      >
                        {aspect.label.split(' ')[0]}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="space-y-2">
                  <Label>Quality</Label>
                  <div className="space-y-2">
                    {QUALITY_TIERS.map((tier, i) => (
                      <button
                        key={i}
                        onClick={() => handleQualityChange(i)}
                        className={`w-full p-2 text-sm rounded-md border transition-colors text-left ${
                          selectedQuality === i
                            ? 'border-accent bg-accent/10 text-accent'
                            : 'border-border hover:border-border-hover text-muted-foreground'
                        }`}
                      >
                        {tier.label}
                        <span className="text-xs ml-2 opacity-70">
                          ({Math.round(ASPECT_RATIOS[selectedAspect].width * tier.multiplier)}x{Math.round(ASPECT_RATIOS[selectedAspect].height * tier.multiplier)})
                        </span>
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {/* Basic Settings Row */}
              <div className="grid gap-4 md:grid-cols-3">
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
                <div className="space-y-2">
                  <Label htmlFor="steps">Steps</Label>
                  <Input
                    id="steps"
                    type="number"
                    min={1}
                    max={50}
                    value={config.steps}
                    onChange={(e) => setConfig({ ...config, steps: parseInt(e.target.value) || 20 })}
                  />
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

              {/* Advanced Toggles */}
              <div className="space-y-3">
                <Label className="flex items-center gap-2">
                  <Settings2 className="h-4 w-4" />
                  Advanced Features
                </Label>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  <FeatureToggle
                    icon={<Sparkles className="h-4 w-4" />}
                    label="ControlNet"
                    description={capabilities?.toggles?.use_controlnet?.description || "Pose/composition control"}
                    enabled={config.use_controlnet || false}
                    onChange={(v) => setConfig({ ...config, use_controlnet: v })}
                    disabled={!capabilities?.toggles?.use_controlnet?.supported}
                    disabledReason={capabilities?.toggles?.use_controlnet?.reason}
                  />
                  <FeatureToggle
                    icon={<Image className="h-4 w-4" />}
                    label="IP-Adapter"
                    description={capabilities?.toggles?.use_ipadapter?.description || "Reference image guidance"}
                    enabled={config.use_ipadapter || false}
                    onChange={(v) => setConfig({ ...config, use_ipadapter: v })}
                    disabled={!capabilities?.toggles?.use_ipadapter?.supported}
                    disabledReason={capabilities?.toggles?.use_ipadapter?.reason}
                  />
                  <FeatureToggle
                    icon={<Smile className="h-4 w-4" />}
                    label="Face Detailer"
                    description={capabilities?.toggles?.use_facedetailer?.description || "Enhance facial features"}
                    enabled={config.use_facedetailer || false}
                    onChange={(v) => setConfig({ ...config, use_facedetailer: v })}
                    disabled={!capabilities?.toggles?.use_facedetailer?.supported}
                    disabledReason={capabilities?.toggles?.use_facedetailer?.reason}
                  />
                  <FeatureToggle
                    icon={<Maximize2 className="h-4 w-4" />}
                    label="Upscale"
                    description={capabilities?.toggles?.use_upscale?.description || "2x resolution output"}
                    enabled={config.use_upscale || false}
                    onChange={(v) => setConfig({ ...config, use_upscale: v })}
                    disabled={!capabilities?.toggles?.use_upscale?.supported}
                    disabledReason={capabilities?.toggles?.use_upscale?.reason}
                  />
                </div>
              </div>

              {/* More Advanced Toggle */}
              <button
                onClick={() => setShowAdvanced(!showAdvanced)}
                className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
              >
                {showAdvanced ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                More Settings
              </button>

              {/* Additional Advanced Settings */}
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
                  <div className="grid gap-4 md:grid-cols-2">
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
                      <p className="text-xs text-muted-foreground">How closely to follow the prompt (1-20)</p>
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
                      <p className="text-xs text-muted-foreground">For reproducible results</p>
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
                {generateMutation.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Wand2 className="mr-2 h-4 w-4" />
                )}
                {generateMutation.isPending ? 'Generating...' : 'Generate'}
              </Button>
            </CardFooter>
          </Card>
        </div>

        {/* Right Column - Jobs & Gallery */}
        <div className="space-y-6">
          {/* Current Job Status */}
          {currentJob && (
            <Card className="border-accent/30">
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm">Current Generation</CardTitle>
                  <span className={`status-badge ${
                    currentJob.status === 'completed' ? 'status-success' :
                    currentJob.status === 'failed' ? 'status-error' :
                    'status-running'
                  }`}>
                    {currentJob.status}
                  </span>
                </div>
              </CardHeader>
              <CardContent>
                {currentJob.status === 'running' && (
                  <div className="space-y-2">
                    <Progress value={currentJob.progress} className="h-2" />
                    <p className="text-xs text-muted-foreground text-center">
                      {currentJob.progress.toFixed(0)}% complete
                    </p>
                  </div>
                )}
                {currentJob.status === 'completed' && currentJob.output_paths.length > 0 && (
                  <div className="grid grid-cols-2 gap-2">
                    {currentJob.output_paths.map((path, i) => (
                      <div key={i} className="relative aspect-square rounded-lg overflow-hidden bg-muted group">
                        <img
                          src={`/api/outputs/${path.split('/').pop()}`}
                          alt={`Generated ${i + 1}`}
                          className="w-full h-full object-cover"
                          onError={(e) => {
                            // Fallback for path resolution
                            (e.target as HTMLImageElement).src = path
                          }}
                        />
                        <div className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-2">
                          <Button size="icon" variant="secondary" className="h-8 w-8">
                            <Download className="h-4 w-4" />
                          </Button>
                          <Button size="icon" variant="secondary" className="h-8 w-8">
                            <ArrowUpRight className="h-4 w-4" />
                          </Button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                {currentJob.status === 'failed' && (
                  <p className="text-sm text-destructive">{currentJob.error_message}</p>
                )}
              </CardContent>
            </Card>
          )}

          {/* Recent Jobs */}
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm">Recent Generations</CardTitle>
                <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => refetchJobs()}>
                  <RefreshCw className="h-4 w-4" />
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              {jobs.length === 0 ? (
                <p className="text-sm text-muted-foreground text-center py-8">
                  No generations yet
                </p>
              ) : (
                <div className="space-y-2 max-h-[400px] overflow-y-auto">
                  {jobs.slice(0, 10).map((job: GenerationJob) => (
                    <div
                      key={job.id}
                      className={`rounded-md border p-3 transition-colors ${
                        selectedJob === job.id
                          ? 'border-accent bg-accent/5'
                          : 'border-border hover:border-border-hover'
                      }`}
                    >
                      <button
                        onClick={() => setSelectedJob(job.id)}
                        className="w-full text-left"
                      >
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-xs text-muted-foreground font-mono truncate max-w-[100px]">
                            {job.id}
                          </span>
                          <span className={`status-badge ${
                            job.status === 'completed' ? 'status-success' :
                            job.status === 'failed' ? 'status-error' :
                            job.status === 'running' ? 'status-running' :
                            'status-pending'
                          }`}>
                            {job.status}
                          </span>
                        </div>
                        <p className="text-sm text-foreground truncate">{job.config.prompt}</p>
                        {job.status === 'running' && (
                          <Progress value={job.progress} className="h-1 mt-2" />
                        )}
                        {job.status === 'completed' && job.output_paths.length > 0 && (
                          <div className="flex items-center gap-1 mt-2 text-xs text-muted-foreground">
                            <Image className="h-3 w-3" />
                            <span>{job.output_paths.length} image(s)</span>
                          </div>
                        )}
                      </button>
                      {/* Log download button for completed/failed jobs */}
                      {['completed', 'failed'].includes(job.status) && (
                        <div className="flex justify-end mt-2 pt-2 border-t border-border/50">
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-7 text-xs"
                            onClick={(e) => {
                              e.stopPropagation()
                              window.open(api.getJobLogUrl(job.id), '_blank')
                            }}
                            title="Download job logs"
                          >
                            <Download className="h-3 w-3 mr-1" />
                            Logs
                          </Button>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}

interface FeatureToggleProps {
  icon: React.ReactNode
  label: string
  description: string
  enabled: boolean
  onChange: (enabled: boolean) => void
  disabled?: boolean
  disabledReason?: string
}

function FeatureToggle({ icon, label, description, enabled, onChange, disabled, disabledReason }: FeatureToggleProps) {
  return (
    <button
      onClick={() => !disabled && onChange(!enabled)}
      disabled={disabled}
      title={disabled ? disabledReason : undefined}
      className={`flex flex-col items-center p-3 rounded-lg border transition-colors relative ${
        disabled
          ? 'border-border bg-muted/50 text-muted-foreground cursor-not-allowed opacity-60'
          : enabled
            ? 'border-accent bg-accent/10 text-accent'
            : 'border-border hover:border-border-hover text-muted-foreground'
      }`}
    >
      {disabled && (
        <div className="absolute top-1 right-1">
          <AlertCircle className="h-3 w-3 text-muted-foreground" />
        </div>
      )}
      <div className={`mb-1 ${enabled && !disabled ? 'text-accent' : ''}`}>
        {icon}
      </div>
      <span className="text-xs font-medium">{label}</span>
      <span className="text-[10px] opacity-70 text-center leading-tight mt-0.5">
        {disabled && disabledReason ? disabledReason : description}
      </span>
    </button>
  )
}
