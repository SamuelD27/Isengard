import { generateCorrelationId } from './utils'
import { uelr, type InteractionContext } from '@/uelr'
import {
  ApiMisrouteError,
  ApiJsonParseError,
  isHtmlResponse,
  getDiagnosticHint,
  sanitizeBodyPreview,
} from './api-errors'

const API_BASE = '/api'

// Re-export error types for consumers
export { ApiMisrouteError, ApiJsonParseError } from './api-errors'

interface RequestOptions extends RequestInit {
  correlationId?: string
  /** UELR interaction context for tracking */
  uelrContext?: InteractionContext
  /** Skip UELR tracking for this request */
  skipUelrTracking?: boolean
}

/**
 * Validates that a response is valid JSON from the API backend,
 * not an HTML page from a static file server.
 *
 * This catches the common "GUI→API misroute" class of bugs where
 * /api/* requests are handled by the frontend's static server
 * instead of being proxied to the backend.
 */
async function validateApiResponse(
  response: Response,
  method: string,
  url: string,
  correlationId: string
): Promise<{ isValid: boolean; bodyText?: string; error?: ApiMisrouteError | ApiJsonParseError }> {
  const contentType = response.headers.get('content-type')

  // Clone response so we can read body for validation while preserving original
  const clonedResponse = response.clone()
  let bodyText: string

  try {
    bodyText = await clonedResponse.text()
  } catch {
    // If we can't read the body, let the caller handle it
    return { isValid: true }
  }

  // Check for HTML response (static server fallback)
  if (isHtmlResponse(contentType, bodyText)) {
    const bodyPreview = sanitizeBodyPreview(bodyText)
    const diagnosticHint = getDiagnosticHint(url, contentType, bodyText)

    const error = new ApiMisrouteError(
      url,
      method,
      response.status,
      contentType,
      bodyPreview,
      correlationId,
      diagnosticHint
    )

    // Log to console for immediate visibility
    console.error('[API Misroute Detected]', error.toJSON())

    return { isValid: false, bodyText, error }
  }

  // Check if response claims to be JSON but isn't parseable
  if (contentType?.includes('application/json') && bodyText.trim()) {
    try {
      JSON.parse(bodyText)
    } catch (parseErr) {
      const bodyPreview = sanitizeBodyPreview(bodyText)
      const error = new ApiJsonParseError(
        url,
        method,
        response.status,
        contentType,
        bodyPreview,
        correlationId,
        parseErr instanceof Error ? parseErr.message : 'Unknown parse error'
      )

      console.error('[API JSON Parse Error]', error.toJSON())
      return { isValid: false, bodyText, error }
    }
  }

  return { isValid: true, bodyText }
}

async function apiRequest<T>(
  endpoint: string,
  options: RequestOptions = {}
): Promise<T> {
  const { uelrContext, skipUelrTracking, ...fetchOptions } = options
  const correlationId = options.correlationId || uelrContext?.correlation_id || generateCorrelationId()
  const url = `${API_BASE}${endpoint}`
  const method = fetchOptions.method || 'GET'

  // Build headers
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'X-Correlation-ID': correlationId,
    ...(fetchOptions.headers as Record<string, string> || {}),
  }

  // Add interaction ID if we have a context
  if (uelrContext) {
    headers['X-Interaction-ID'] = uelrContext.interaction_id
  }

  // Log request start if we have a context and tracking is not skipped
  const context = uelrContext || (!skipUelrTracking ? uelr.getActiveContext() : undefined)
  const startTime = performance.now()

  if (context) {
    uelr.logNetworkRequestStart(context, method, url, fetchOptions.body)
  }

  try {
    const response = await fetch(url, {
      ...fetchOptions,
      headers,
    })

    // === API MISROUTE DETECTION ===
    // Validate response before processing to catch static server fallback
    const validation = await validateApiResponse(response, method, url, correlationId)
    if (!validation.isValid && validation.error) {
      // Log the misroute error via UELR for traceability
      if (context) {
        uelr.logStep(context, {
          type: 'NETWORK_REQUEST_END',
          component: 'frontend',
          message: `API MISROUTE: ${method} ${url}`,
          status: 'error',
          duration_ms: performance.now() - startTime,
          details: validation.error.toJSON(),
        })
      }
      throw validation.error
    }

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
      const errorMessage = error.detail || `HTTP ${response.status}`

      if (context) {
        uelr.logNetworkRequestEnd(context, method, url, startTime, response.status, error, new Error(errorMessage))
      }

      throw new Error(errorMessage)
    }

    const data = await response.json()

    if (context) {
      uelr.logNetworkRequestEnd(context, method, url, startTime, response.status, data)
    }

    return data
  } catch (error) {
    if (context) {
      uelr.logNetworkRequestEnd(context, method, url, startTime, 0, undefined, error)
    }
    throw error
  }
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
  // Advanced parameters (optional)
  optimizer?: string
  scheduler?: string
  precision?: string
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
  use_controlnet?: boolean
  use_ipadapter?: boolean
  use_facedetailer?: boolean
  use_upscale?: boolean
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

// Dataset types
export interface DatasetImage {
  id: string
  filename: string
  character_id: string
  split: 'reference' | 'train' | 'synthetic'
  size_bytes: number
  width: number
  height: number
  caption: string | null
  created_at: string
}

// Capability types from /info endpoint
export interface ToggleSchema {
  supported: boolean
  reason?: string
  description?: string
}

export interface ParameterSchema {
  type: 'int' | 'float' | 'enum' | 'bool' | 'string'
  min?: number
  max?: number
  step?: number
  options?: (string | number)[]
  default?: unknown
  wired: boolean
  reason?: string
  description?: string
}

export interface ImageCapabilities {
  backend: string
  model_variants: string[]
  toggles: Record<string, ToggleSchema>
  parameters: Record<string, ParameterSchema>
}

export interface TrainingCapabilities {
  method: string
  backend: string
  parameters: Record<string, ParameterSchema>
}

export interface ApiInfo {
  name: string
  version: string
  mode: string
  training: TrainingCapabilities
  image_generation: ImageCapabilities
}

// API functions
export const api = {
  // Health
  health: () => apiRequest<{ status: string }>('/health'),
  info: () => apiRequest<ApiInfo>('/info'),

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
  uploadImages: async (characterId: string, files: FileList, uelrContext?: InteractionContext) => {
    const formData = new FormData()
    Array.from(files).forEach(file => formData.append('files', file))

    const context = uelrContext || uelr.getActiveContext()
    const correlationId = context?.correlation_id || generateCorrelationId()
    const url = `${API_BASE}/characters/${characterId}/images`
    const method = 'POST'

    const headers: Record<string, string> = { 'X-Correlation-ID': correlationId }
    if (context) {
      headers['X-Interaction-ID'] = context.interaction_id
    }

    const startTime = performance.now()
    if (context) {
      uelr.logNetworkRequestStart(context, method, url, { files: files.length })
    }

    try {
      const response = await fetch(url, {
        method,
        headers,
        body: formData,
      })

      // === API MISROUTE DETECTION ===
      const validation = await validateApiResponse(response, method, url, correlationId)
      if (!validation.isValid && validation.error) {
        if (context) {
          uelr.logStep(context, {
            type: 'NETWORK_REQUEST_END',
            component: 'frontend',
            message: `API MISROUTE (upload): ${method} ${url}`,
            status: 'error',
            duration_ms: performance.now() - startTime,
            details: validation.error.toJSON(),
          })
        }
        throw validation.error
      }

      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Upload failed' }))
        if (context) {
          uelr.logNetworkRequestEnd(context, method, url, startTime, response.status, error, new Error(error.detail))
        }
        throw new Error(error.detail)
      }

      const data = await response.json()
      if (context) {
        uelr.logNetworkRequestEnd(context, method, url, startTime, response.status, data)
      }
      return data
    } catch (error) {
      if (context) {
        uelr.logNetworkRequestEnd(context, method, url, startTime, 0, undefined, error)
      }
      throw error
    }
  },
  listImages: (characterId: string) =>
    apiRequest<{ images: string[]; count: number }>(`/characters/${characterId}/images`),
  deleteImage: (characterId: string, filename: string) =>
    apiRequest<void>(`/characters/${characterId}/images/${encodeURIComponent(filename)}`, { method: 'DELETE' }),

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

  // Job Logs
  getJobLogUrl: (jobId: string) => `${API_BASE}/jobs/${jobId}/logs`,
}
