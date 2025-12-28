import { useState, useEffect, useRef, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Play,
  Square,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  Info,
  Zap,
  Settings2,
  Terminal,
  Image as ImageIcon,
  Clock,
  Gauge,
  Sparkles,
  Download,
  AlertTriangle,
  Eye,
  ExternalLink,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Progress } from '@/components/ui/progress'
import { Collapsible, CollapsibleTrigger, CollapsibleContent } from '@/components/ui/collapsible'
import { DynamicControl, UnavailableControl } from '@/components/DynamicControl'
import { TrainingJobDetail } from '@/components/TrainingJobDetail'
import { api, Character, TrainingJob, TrainingConfig, TrainingCapabilities, ParameterSchema } from '@/lib/api'

// Preset configurations
const PRESETS = {
  quick: {
    name: 'Quick Train',
    icon: Zap,
    description: 'Fast training, good for testing',
    config: {
      steps: 500,
      learning_rate: 0.0002,
      lora_rank: 8,
      resolution: 768,
      batch_size: 1,
      optimizer: 'adamw8bit',
      scheduler: 'constant',
      precision: 'bf16',
    }
  },
  balanced: {
    name: 'Balanced',
    icon: Gauge,
    description: 'Recommended for most cases',
    config: {
      steps: 1000,
      learning_rate: 0.0001,
      lora_rank: 16,
      resolution: 1024,
      batch_size: 1,
      optimizer: 'adamw8bit',
      scheduler: 'cosine',
      precision: 'bf16',
    }
  },
  quality: {
    name: 'High Quality',
    icon: Sparkles,
    description: 'Best results, longer training',
    config: {
      steps: 2000,
      learning_rate: 0.00005,
      lora_rank: 32,
      resolution: 1024,
      batch_size: 1,
      optimizer: 'prodigy',
      scheduler: 'cosine_with_restarts',
      precision: 'bf16',
    }
  },
} as const

type PresetKey = keyof typeof PRESETS

interface ExtendedTrainingConfig extends TrainingConfig {
  optimizer?: string
  scheduler?: string
  precision?: string
}

const defaultConfig: ExtendedTrainingConfig = {
  method: 'lora',
  steps: 1000,
  learning_rate: 0.0001,
  batch_size: 1,
  resolution: 1024,
  lora_rank: 16,
  optimizer: 'adamw8bit',
  scheduler: 'cosine',
  precision: 'bf16',
}

export default function TrainingPage() {
  const queryClient = useQueryClient()
  const [selectedCharacter, setSelectedCharacter] = useState<string>('')
  const [selectedPreset, setSelectedPreset] = useState<PresetKey | 'custom'>('balanced')
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [showUnavailable, setShowUnavailable] = useState(false)
  const [config, setConfig] = useState<ExtendedTrainingConfig>(defaultConfig)
  const [configInitialized, setConfigInitialized] = useState(false)
  const [activeJobId, setActiveJobId] = useState<string | null>(null)
  const [logs, setLogs] = useState<string[]>([])
  const [selectedJobDetail, setSelectedJobDetail] = useState<TrainingJob | null>(null)
  const logsEndRef = useRef<HTMLDivElement>(null)

  // Fetch capabilities from /api/info
  const { data: apiInfo } = useQuery({
    queryKey: ['api-info'],
    queryFn: api.info,
    staleTime: 60000, // Cache for 1 minute
  })

  const capabilities: TrainingCapabilities | undefined = apiInfo?.training

  // Separate wired vs unwired parameters
  const { wiredParams, unwiredParams } = useMemo(() => {
    if (!capabilities?.parameters) {
      return { wiredParams: {} as Record<string, ParameterSchema>, unwiredParams: {} as Record<string, ParameterSchema> }
    }
    const wired: Record<string, ParameterSchema> = {}
    const unwired: Record<string, ParameterSchema> = {}
    for (const [key, schema] of Object.entries(capabilities.parameters)) {
      if (schema.wired) {
        wired[key] = schema
      } else {
        unwired[key] = schema
      }
    }
    return { wiredParams: wired, unwiredParams: unwired }
  }, [capabilities])

  // Initialize config from schema defaults ONCE
  useEffect(() => {
    if (capabilities?.parameters && !configInitialized) {
      const schemaDefaults: Partial<ExtendedTrainingConfig> = {}
      for (const [key, schema] of Object.entries(capabilities.parameters)) {
        if (schema.default !== undefined) {
          (schemaDefaults as Record<string, unknown>)[key] = schema.default
        }
      }
      // Merge schema defaults with preset defaults
      setConfig(prev => ({ ...prev, ...schemaDefaults, ...PRESETS.balanced.config }))
      setConfigInitialized(true)
    }
  }, [capabilities, configInitialized])

  // Count preset params that are not wired (skip note)
  const presetSkipCount = useMemo(() => {
    if (!capabilities?.parameters) return 0
    const presetKeys = Object.keys(PRESETS.balanced.config)
    return presetKeys.filter(key => {
      const schema = capabilities.parameters[key]
      return schema && !schema.wired
    }).length
  }, [capabilities])

  const { data: characters = [] } = useQuery({
    queryKey: ['characters'],
    queryFn: api.listCharacters,
  })

  const { data: jobs = [], isLoading: jobsLoading } = useQuery({
    queryKey: ['training-jobs'],
    queryFn: () => api.listTrainingJobs(),
    refetchInterval: 5000,
  })

  // Find active running job
  const runningJob = jobs.find(j => j.status === 'running' || j.status === 'queued')

  // SSE connection for live logs
  useEffect(() => {
    if (!runningJob) {
      setActiveJobId(null)
      return
    }

    if (activeJobId === runningJob.id) return

    setActiveJobId(runningJob.id)
    setLogs([`[${new Date().toLocaleTimeString()}] Connected to training stream...`])

    const eventSource = new EventSource(`/api/training/${runningJob.id}/stream`)

    eventSource.addEventListener('progress', (e) => {
      try {
        const data = JSON.parse(e.data)
        if (data.message) {
          setLogs(prev => [...prev.slice(-100), `[${new Date().toLocaleTimeString()}] ${data.message}`])
        }
      } catch (err) {
        console.error('Failed to parse SSE data:', err)
      }
    })

    eventSource.addEventListener('complete', (e) => {
      try {
        const data = JSON.parse(e.data)
        setLogs(prev => [...prev, `[${new Date().toLocaleTimeString()}] Training ${data.status}: ${data.message || 'Done'}`])
      } catch (err) {
        console.error('Failed to parse SSE data:', err)
      }
      eventSource.close()
      queryClient.invalidateQueries({ queryKey: ['training-jobs'] })
      queryClient.invalidateQueries({ queryKey: ['characters'] })
    })

    eventSource.onerror = () => {
      setLogs(prev => [...prev, `[${new Date().toLocaleTimeString()}] Connection lost, retrying...`])
    }

    return () => {
      eventSource.close()
    }
  }, [runningJob?.id, activeJobId, queryClient])

  // Auto-scroll logs
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  const startMutation = useMutation({
    mutationFn: ({ characterId, config }: { characterId: string; config: ExtendedTrainingConfig }) => {
      console.log('[Training] Starting mutation with:', { characterId, config })
      return api.startTraining(characterId, config)
    },
    onSuccess: (data) => {
      console.log('[Training] Mutation success:', data)
      queryClient.invalidateQueries({ queryKey: ['training-jobs'] })
      setLogs([])
    },
    onError: (error) => {
      console.error('[Training] Mutation error:', error)
    },
  })

  const cancelMutation = useMutation({
    mutationFn: api.cancelTraining,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['training-jobs'] })
    },
  })

  const handlePresetChange = (preset: PresetKey | 'custom') => {
    setSelectedPreset(preset)
    if (preset !== 'custom') {
      setConfig({ ...defaultConfig, ...PRESETS[preset].config })
    }
  }

  const handleConfigChange = (updates: Partial<ExtendedTrainingConfig>) => {
    setConfig(prev => ({ ...prev, ...updates }))
    setSelectedPreset('custom')
  }

  const handleStartTraining = () => {
    console.log('[Training] handleStartTraining called, selectedCharacter:', selectedCharacter)
    if (selectedCharacter) {
      console.log('[Training] Calling startMutation.mutate')
      startMutation.mutate({ characterId: selectedCharacter, config })
    } else {
      console.log('[Training] No character selected, mutation not called')
    }
  }

  const eligibleCharacters = characters.filter((c: Character) => c.image_count > 0)
  const selectedChar = characters.find((c: Character) => c.id === selectedCharacter)

  // Estimate training time based on steps and batch size
  const estimatedMinutes = Math.ceil((config.steps * 2) / 60) // ~2s per step estimate

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
        <div className="lg:col-span-3 space-y-6">
          {/* Presets */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Training Preset</CardTitle>
              <CardDescription>Choose a preset or customize settings</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="grid grid-cols-3 gap-3">
                {(Object.entries(PRESETS) as [PresetKey, typeof PRESETS[PresetKey]][]).map(([key, preset]) => {
                  const Icon = preset.icon
                  const isSelected = selectedPreset === key
                  return (
                    <button
                      key={key}
                      onClick={() => handlePresetChange(key)}
                      className={`relative p-4 rounded-lg border-2 text-left transition-all ${
                        isSelected
                          ? 'border-accent bg-accent-soft'
                          : 'border-border hover:border-border-hover bg-background'
                      }`}
                    >
                      <Icon className={`h-5 w-5 mb-2 ${isSelected ? 'text-accent' : 'text-muted-foreground'}`} />
                      <h3 className={`font-medium text-sm ${isSelected ? 'text-accent' : 'text-foreground'}`}>
                        {preset.name}
                      </h3>
                      <p className="text-xs text-muted-foreground mt-1">{preset.description}</p>
                      {isSelected && (
                        <div className="absolute top-2 right-2 w-2 h-2 rounded-full bg-accent" />
                      )}
                    </button>
                  )
                })}
              </div>
              {/* Preset skip note */}
              {presetSkipCount > 0 && selectedPreset !== 'custom' && (
                <div className="flex items-center gap-2 text-xs text-muted-foreground bg-muted/50 rounded-md px-3 py-2">
                  <AlertTriangle className="h-3.5 w-3.5" />
                  <span>{presetSkipCount} preset parameter(s) not supported by current backend</span>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Main Configuration */}
          <Card>
            <CardHeader>
              <CardTitle>Configuration</CardTitle>
              <CardDescription>
                {selectedPreset === 'custom' ? 'Custom settings' : `Using ${PRESETS[selectedPreset as PresetKey].name} preset`}
              </CardDescription>
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
                    {eligibleCharacters.map((char: Character) => (
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
                  {selectedChar.lora_path && (
                    <p className="text-foreground">
                      <span className="text-muted-foreground">Existing LoRA:</span>{' '}
                      <span className="text-warning">Will be overwritten</span>
                    </p>
                  )}
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
                    onChange={(e) => handleConfigChange({ steps: parseInt(e.target.value) || 1000 })}
                  />
                  <p className="text-xs text-muted-foreground flex items-center gap-1">
                    <Clock className="h-3 w-3" />
                    ~{estimatedMinutes} min
                  </p>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="resolution">Resolution</Label>
                  <select
                    id="resolution"
                    className="flex h-9 w-full rounded-md border border-border bg-input px-3 py-2 text-sm text-foreground focus:outline-none focus:border-accent"
                    value={config.resolution}
                    onChange={(e) => handleConfigChange({ resolution: parseInt(e.target.value) })}
                  >
                    <option value={512}>512px (fast)</option>
                    <option value={768}>768px</option>
                    <option value={1024}>1024px (recommended)</option>
                  </select>
                </div>
              </div>

              {/* Advanced Toggle */}
              <button
                onClick={() => setShowAdvanced(!showAdvanced)}
                className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
              >
                <Settings2 className="h-4 w-4" />
                {showAdvanced ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                Advanced Settings
              </button>

              {/* Advanced Settings - Rendered dynamically from schema */}
              {showAdvanced && (
                <div className="space-y-4 pt-4 border-t border-border">
                  {/* Wired parameters from schema */}
                  {Object.keys(wiredParams).length > 0 ? (
                    <div className="grid gap-4 md:grid-cols-2">
                      {Object.entries(wiredParams)
                        .filter(([key]) => !['steps', 'resolution'].includes(key)) // Already shown above
                        .map(([key, schema]) => (
                          <DynamicControl
                            key={key}
                            name={key}
                            schema={schema}
                            value={(config as unknown as Record<string, unknown>)[key]}
                            onChange={(value) => handleConfigChange({ [key]: value } as Partial<ExtendedTrainingConfig>)}
                          />
                        ))}
                    </div>
                  ) : (
                    /* Fallback to hardcoded if no schema */
                    <>
                      <div className="grid gap-4 md:grid-cols-2">
                        <div className="space-y-2">
                          <Label htmlFor="lr">Learning Rate</Label>
                          <Input
                            id="lr"
                            type="number"
                            step="0.00001"
                            min={0.000001}
                            max={0.01}
                            value={config.learning_rate}
                            onChange={(e) => handleConfigChange({ learning_rate: parseFloat(e.target.value) })}
                          />
                        </div>
                        <div className="space-y-2">
                          <Label htmlFor="rank">LoRA Rank</Label>
                          <select
                            id="rank"
                            className="flex h-9 w-full rounded-md border border-border bg-input px-3 py-2 text-sm text-foreground focus:outline-none focus:border-accent"
                            value={config.lora_rank}
                            onChange={(e) => handleConfigChange({ lora_rank: parseInt(e.target.value) })}
                          >
                            <option value={4}>4 (smallest, fastest)</option>
                            <option value={8}>8</option>
                            <option value={16}>16 (default)</option>
                            <option value={32}>32</option>
                            <option value={64}>64</option>
                            <option value={128}>128 (largest, slowest)</option>
                          </select>
                        </div>
                      </div>

                      <div className="grid gap-4 md:grid-cols-3">
                        <div className="space-y-2">
                          <Label htmlFor="optimizer">Optimizer</Label>
                          <select
                            id="optimizer"
                            className="flex h-9 w-full rounded-md border border-border bg-input px-3 py-2 text-sm text-foreground focus:outline-none focus:border-accent"
                            value={config.optimizer}
                            onChange={(e) => handleConfigChange({ optimizer: e.target.value })}
                          >
                            <option value="adamw8bit">AdamW 8-bit</option>
                            <option value="adamw">AdamW</option>
                            <option value="prodigy">Prodigy</option>
                          </select>
                        </div>
                        <div className="space-y-2">
                          <Label htmlFor="scheduler">LR Scheduler</Label>
                          <select
                            id="scheduler"
                            className="flex h-9 w-full rounded-md border border-border bg-input px-3 py-2 text-sm text-foreground focus:outline-none focus:border-accent"
                            value={config.scheduler}
                            onChange={(e) => handleConfigChange({ scheduler: e.target.value })}
                          >
                            <option value="constant">Constant</option>
                            <option value="cosine">Cosine</option>
                            <option value="cosine_with_restarts">Cosine w/ Restarts</option>
                            <option value="linear">Linear</option>
                          </select>
                        </div>
                        <div className="space-y-2">
                          <Label htmlFor="precision">Precision</Label>
                          <select
                            id="precision"
                            className="flex h-9 w-full rounded-md border border-border bg-input px-3 py-2 text-sm text-foreground focus:outline-none focus:border-accent"
                            value={config.precision}
                            onChange={(e) => handleConfigChange({ precision: e.target.value })}
                          >
                            <option value="bf16">BFloat16 (recommended)</option>
                            <option value="fp16">Float16</option>
                            <option value="fp32">Float32 (slow)</option>
                          </select>
                        </div>
                      </div>

                      <div className="grid gap-4 md:grid-cols-2">
                        <div className="space-y-2">
                          <Label htmlFor="batch">Batch Size</Label>
                          <select
                            id="batch"
                            className="flex h-9 w-full rounded-md border border-border bg-input px-3 py-2 text-sm text-foreground focus:outline-none focus:border-accent"
                            value={config.batch_size}
                            onChange={(e) => handleConfigChange({ batch_size: parseInt(e.target.value) })}
                          >
                            <option value={1}>1 (low VRAM)</option>
                            <option value={2}>2</option>
                            <option value={4}>4 (more VRAM)</option>
                          </select>
                        </div>
                      </div>
                    </>
                  )}

                  {/* Unavailable Parameters (unwired) */}
                  {Object.keys(unwiredParams).length > 0 && (
                    <Collapsible open={showUnavailable} onOpenChange={setShowUnavailable} className="mt-4">
                      <CollapsibleTrigger className="text-muted-foreground">
                        Unavailable Parameters ({Object.keys(unwiredParams).length})
                      </CollapsibleTrigger>
                      <CollapsibleContent>
                        <div className="space-y-2 mt-2">
                          {Object.entries(unwiredParams).map(([key, schema]) => (
                            <UnavailableControl key={key} name={key} schema={schema} />
                          ))}
                        </div>
                      </CollapsibleContent>
                    </Collapsible>
                  )}
                </div>
              )}
            </CardContent>
            <CardFooter className="border-t border-border pt-5">
              <Button
                className="w-full"
                disabled={!selectedCharacter || startMutation.isPending || !!runningJob}
                onClick={handleStartTraining}
              >
                <Play className="mr-2 h-4 w-4" />
                {startMutation.isPending ? 'Starting...' : runningJob ? 'Training in Progress...' : 'Start Training'}
              </Button>
            </CardFooter>
          </Card>
        </div>

        {/* Right Column - 2 cols */}
        <div className="lg:col-span-2 space-y-6">
          {/* Tips */}
          <Card className="h-fit">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
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
              <div>
                <h4 className="font-medium text-foreground mb-1">Presets Guide</h4>
                <ul className="space-y-1 text-muted-foreground">
                  <li><strong>Quick:</strong> Test if images work</li>
                  <li><strong>Balanced:</strong> Production ready</li>
                  <li><strong>Quality:</strong> Best likeness</li>
                </ul>
              </div>
            </CardContent>
          </Card>

          {/* Live Logs */}
          {runningJob && (
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-2 text-base">
                  <Terminal className="h-4 w-4 text-accent" />
                  Training Log
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="bg-background rounded-md border border-border p-3 h-48 overflow-y-auto font-mono text-xs">
                  {logs.length === 0 ? (
                    <p className="text-muted-foreground">Waiting for logs...</p>
                  ) : (
                    logs.map((log, i) => (
                      <div key={i} className="text-muted-foreground py-0.5">
                        {log}
                      </div>
                    ))
                  )}
                  <div ref={logsEndRef} />
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      </div>

      {/* Training Jobs */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-medium text-foreground">Training History</h2>
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
            {jobs.map((job: TrainingJob) => (
              <TrainingJobCard
                key={job.id}
                job={job}
                character={characters.find((c: Character) => c.id === job.character_id)}
                onCancel={() => cancelMutation.mutate(job.id)}
                onViewDetails={() => setSelectedJobDetail(job)}
                isActive={job.id === runningJob?.id}
              />
            ))}
          </div>

          {/* Job Detail Modal */}
          {selectedJobDetail && (
            <TrainingJobDetail
              job={selectedJobDetail}
              characterName={characters.find((c: Character) => c.id === selectedJobDetail.character_id)?.name}
              onClose={() => setSelectedJobDetail(null)}
              onCancel={() => {
                cancelMutation.mutate(selectedJobDetail.id)
                setSelectedJobDetail(null)
              }}
            />
          )}
        )}
      </div>
    </div>
  )
}

interface TrainingJobCardProps {
  job: TrainingJob
  character?: Character
  onCancel: () => void
  onViewDetails: () => void
  isActive: boolean
}

function TrainingJobCard({ job, character, onCancel, onViewDetails, isActive }: TrainingJobCardProps) {
  const statusClasses: Record<string, string> = {
    pending: 'status-badge status-pending',
    queued: 'status-badge status-running',
    running: 'status-badge status-running',
    completed: 'status-badge status-success',
    failed: 'status-badge status-error',
    cancelled: 'status-badge status-pending',
  }

  return (
    <Card className={`${isActive ? 'border-accent' : ''} cursor-pointer hover:border-accent/50 transition-colors`} onClick={onViewDetails}>
      <CardContent className="py-4">
        <div className="flex items-center justify-between mb-3">
          <div className="min-w-0">
            <h3 className="font-medium text-foreground truncate flex items-center gap-2">
              {character?.name || 'Unknown'}
              {isActive && <span className="w-2 h-2 rounded-full bg-accent animate-pulse" />}
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

        {job.status === 'completed' && job.output_path && (
          <div className="flex items-center gap-2 text-sm text-success mt-2">
            <ImageIcon className="h-4 w-4" />
            <span>LoRA saved successfully</span>
          </div>
        )}

        {job.error_message && (
          <p className="text-sm text-destructive mt-2 truncate" title={job.error_message}>
            {job.error_message}
          </p>
        )}

        <div className="flex items-center justify-between mt-3">
          <div className="text-xs text-muted-foreground">
            {job.config.steps} steps @ {job.config.resolution}px | rank {job.config.lora_rank}
          </div>
          <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
            <Button
              variant="ghost"
              size="sm"
              onClick={onViewDetails}
              title="View details"
            >
              <Eye className="h-3.5 w-3.5" />
            </Button>
            {['completed', 'failed'].includes(job.status) && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => window.open(api.getJobLogUrl(job.id), '_blank')}
                title="Download job logs"
              >
                <Download className="h-3.5 w-3.5" />
              </Button>
            )}
            {['running', 'queued', 'pending'].includes(job.status) && (
              <Button variant="outline" size="sm" onClick={onCancel}>
                <Square className="mr-2 h-3.5 w-3.5" />
                Cancel
              </Button>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
