import { generateCorrelationId } from './utils'

const API_BASE = '/api'

interface RequestOptions extends RequestInit {
  correlationId?: string
}

async function apiRequest<T>(
  endpoint: string,
  options: RequestOptions = {}
): Promise<T> {
  const correlationId = options.correlationId || generateCorrelationId()

  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'X-Correlation-ID': correlationId,
      ...options.headers,
    },
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  return response.json()
}

// Character types
export interface Character {
  id: string
  name: string
  description: string | null
  trigger_word: string
  created_at: string
  updated_at: string
  image_count: number
  lora_path: string | null
  lora_trained_at: string | null
}

export interface CreateCharacterRequest {
  name: string
  description?: string
  trigger_word: string
}

// Training types
export interface TrainingConfig {
  method: 'lora'
  steps: number
  learning_rate: number
  batch_size: number
  resolution: number
  lora_rank: number
}

export interface TrainingJob {
  id: string
  character_id: string
  status: 'pending' | 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'
  config: TrainingConfig
  progress: number
  current_step: number
  total_steps: number
  error_message: string | null
  created_at: string
  started_at: string | null
  completed_at: string | null
  output_path: string | null
}

// Generation types
export interface GenerationConfig {
  prompt: string
  negative_prompt: string
  width: number
  height: number
  steps: number
  guidance_scale: number
  seed: number | null
  lora_id: string | null
  lora_strength: number
}

export interface GenerationJob {
  id: string
  status: 'pending' | 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'
  config: GenerationConfig
  progress: number
  error_message: string | null
  created_at: string
  output_paths: string[]
}

// API functions
export const api = {
  // Health
  health: () => apiRequest<{ status: string }>('/health'),
  info: () => apiRequest<{ name: string; version: string; mode: string; capabilities: Record<string, string[]> }>('/info'),

  // Characters
  listCharacters: () => apiRequest<Character[]>('/characters'),
  getCharacter: (id: string) => apiRequest<Character>(`/characters/${id}`),
  createCharacter: (data: CreateCharacterRequest) =>
    apiRequest<Character>('/characters', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  updateCharacter: (id: string, data: Partial<CreateCharacterRequest>) =>
    apiRequest<Character>(`/characters/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
  deleteCharacter: (id: string) =>
    apiRequest<void>(`/characters/${id}`, { method: 'DELETE' }),
  uploadImages: async (characterId: string, files: FileList) => {
    const formData = new FormData()
    Array.from(files).forEach(file => formData.append('files', file))

    const correlationId = generateCorrelationId()
    const response = await fetch(`${API_BASE}/characters/${characterId}/images`, {
      method: 'POST',
      headers: { 'X-Correlation-ID': correlationId },
      body: formData,
    })

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Upload failed' }))
      throw new Error(error.detail)
    }

    return response.json()
  },
  listImages: (characterId: string) =>
    apiRequest<{ images: string[]; count: number }>(`/characters/${characterId}/images`),

  // Training
  startTraining: (characterId: string, config: Partial<TrainingConfig> = {}) =>
    apiRequest<TrainingJob>('/training', {
      method: 'POST',
      body: JSON.stringify({
        character_id: characterId,
        config: {
          method: 'lora',
          steps: 1000,
          learning_rate: 0.0001,
          batch_size: 1,
          resolution: 1024,
          lora_rank: 16,
          ...config,
        },
      }),
    }),
  getTrainingJob: (jobId: string) => apiRequest<TrainingJob>(`/training/${jobId}`),
  cancelTraining: (jobId: string) =>
    apiRequest<TrainingJob>(`/training/${jobId}/cancel`, { method: 'POST' }),
  listTrainingJobs: (characterId?: string) => {
    const query = characterId ? `?character_id=${characterId}` : ''
    return apiRequest<TrainingJob[]>(`/training${query}`)
  },

  // Generation
  generateImages: (config: GenerationConfig, count: number = 1) =>
    apiRequest<GenerationJob>('/generation', {
      method: 'POST',
      body: JSON.stringify({ config, count }),
    }),
  getGenerationJob: (jobId: string) => apiRequest<GenerationJob>(`/generation/${jobId}`),
  cancelGeneration: (jobId: string) =>
    apiRequest<GenerationJob>(`/generation/${jobId}/cancel`, { method: 'POST' }),
  listGenerationJobs: (limit: number = 20) =>
    apiRequest<GenerationJob[]>(`/generation?limit=${limit}`),
}
