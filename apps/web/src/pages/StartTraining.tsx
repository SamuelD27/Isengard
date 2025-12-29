/**
 * Start Training Page
 *
 * Training configuration form with:
 * - 3 default presets (Quick, Balanced, High Quality)
 * - 1 custom option
 * - Advanced settings
 * - On successful job creation, redirects to the job detail page
 */

import { useState, useEffect, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  Play,
  ArrowLeft,
  ChevronDown,
  ChevronUp,
  Zap,
  Gauge,
  Sparkles,
  Settings2,
  Clock,
  AlertTriangle,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Collapsible, CollapsibleTrigger, CollapsibleContent } from '@/components/ui/collapsible'
import { DynamicControl, UnavailableControl } from '@/components/DynamicControl'
import { api, Character, TrainingConfig, TrainingCapabilities, ParameterSchema } from '@/lib/api'

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

export default function StartTrainingPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [selectedCharacter, setSelectedCharacter] = useState<string>('')
  const [selectedPreset, setSelectedPreset] = useState<PresetKey | 'custom'>('balanced')
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [showUnavailable, setShowUnavailable] = useState(false)
  const [config, setConfig] = useState<ExtendedTrainingConfig>(defaultConfig)
  const [configInitialized, setConfigInitialized] = useState(false)

  // Fetch capabilities from /api/info
  const { data: apiInfo } = useQuery({
    queryKey: ['api-info'],
    queryFn: api.info,
    staleTime: 60000,
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

  const startMutation = useMutation({
    mutationFn: ({ characterId, config, presetName }: { characterId: string; config: ExtendedTrainingConfig; presetName: string }) => {
      console.log('[Training] Starting training with:', { characterId, config, presetName })
      return api.startTraining(characterId, config, presetName, 'flux-dev')
    },
    onSuccess: (data) => {
      console.log('[Training] Job created:', data)
      queryClient.invalidateQueries({ queryKey: ['training-jobs'] })
      queryClient.invalidateQueries({ queryKey: ['training-jobs-ongoing'] })
      // Navigate to the job detail page
      navigate(`/training/${data.id}`)
    },
    onError: (error) => {
      console.error('[Training] Mutation error:', error)
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
    if (selectedCharacter) {
      startMutation.mutate({
        characterId: selectedCharacter,
        config,
        presetName: selectedPreset,
      })
    }
  }

  const eligibleCharacters = characters.filter((c: Character) => c.image_count > 0)
  const selectedChar = characters.find((c: Character) => c.id === selectedCharacter)

  // Estimate training time based on steps and batch size
  const estimatedMinutes = Math.ceil((config.steps * 2) / 60)

  return (
    <div className="space-y-6 fade-in max-w-4xl mx-auto">
      {/* Page Header */}
      <div className="flex items-center gap-4">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => navigate('/training')}
        >
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div>
          <h1 className="text-xl font-semibold text-foreground">Start Training</h1>
          <p className="text-sm text-muted-foreground">
            Configure and launch a new LoRA training job
          </p>
        </div>
      </div>

      {/* Presets */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Training Preset</CardTitle>
          <CardDescription>Choose a preset or customize settings</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-4 gap-3">
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
            {/* Custom option */}
            <button
              onClick={() => handlePresetChange('custom')}
              className={`relative p-4 rounded-lg border-2 text-left transition-all ${
                selectedPreset === 'custom'
                  ? 'border-accent bg-accent-soft'
                  : 'border-border hover:border-border-hover bg-background'
              }`}
            >
              <Settings2 className={`h-5 w-5 mb-2 ${selectedPreset === 'custom' ? 'text-accent' : 'text-muted-foreground'}`} />
              <h3 className={`font-medium text-sm ${selectedPreset === 'custom' ? 'text-accent' : 'text-foreground'}`}>
                Custom
              </h3>
              <p className="text-xs text-muted-foreground mt-1">Full control over all settings</p>
              {selectedPreset === 'custom' && (
                <div className="absolute top-2 right-2 w-2 h-2 rounded-full bg-accent" />
              )}
            </button>
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
                  <span className="text-warning">Will be versioned (new v{(selectedChar.lora_path.match(/v(\d+)/) || ['', '0'])[1] ? parseInt((selectedChar.lora_path.match(/v(\d+)/) || ['', '0'])[1]) + 1 : 1})</span>
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

          {/* Advanced Settings */}
          {showAdvanced && (
            <div className="space-y-4 pt-4 border-t border-border">
              {Object.keys(wiredParams).length > 0 ? (
                <div className="grid gap-4 md:grid-cols-2">
                  {Object.entries(wiredParams)
                    .filter(([key]) => !['steps', 'resolution'].includes(key))
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

              {/* Unavailable Parameters */}
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
            disabled={!selectedCharacter || startMutation.isPending}
            onClick={handleStartTraining}
          >
            <Play className="mr-2 h-4 w-4" />
            {startMutation.isPending ? 'Starting...' : 'Start Training'}
          </Button>
        </CardFooter>
      </Card>
    </div>
  )
}
