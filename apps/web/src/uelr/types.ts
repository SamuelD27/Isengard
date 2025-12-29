/**
 * UELR (User End Log Register) Type Definitions
 *
 * Shared types for tracking user interactions end-to-end across
 * frontend, backend, and worker components.
 */

// Step types that can occur in an interaction timeline
export type StepType =
  | 'UI_ACTION_START'
  | 'UI_ACTION_END'
  | 'UI_STATE_CHANGE'
  | 'NETWORK_REQUEST_START'
  | 'NETWORK_REQUEST_END'
  | 'SSE_CONNECT'
  | 'SSE_MESSAGE'
  | 'SSE_CLOSE'
  | 'SSE_ERROR'
  | 'BACKEND_ROUTE_START'
  | 'BACKEND_ROUTE_END'
  | 'BACKEND_ERROR'
  | 'JOB_ENQUEUE'
  | 'JOB_START'
  | 'JOB_PROGRESS'
  | 'JOB_END'
  | 'WORKER_TASK_START'
  | 'WORKER_TASK_END'
  | 'PLUGIN_CALL'
  | 'PLUGIN_RESPONSE'
  | 'COMFYUI_REQUEST'
  | 'COMFYUI_RESPONSE'
  | 'ERROR'
  | 'WARNING'
  | 'INFO';

// Component that generated the step
export type StepComponent = 'frontend' | 'backend' | 'worker' | 'plugin' | 'comfyui' | 'redis';

// Status of a step or interaction
export type StepStatus = 'pending' | 'success' | 'error' | 'cancelled';

/**
 * A single step in an interaction timeline
 */
export interface UELRStep {
  // Unique ID for this step
  step_id: string;

  // Link to parent interaction
  interaction_id: string;
  correlation_id: string;

  // Step classification
  type: StepType;
  component: StepComponent;

  // Timing
  timestamp: string; // ISO 8601
  duration_ms?: number;

  // Human-readable message
  message: string;

  // Status
  status: StepStatus;

  // Optional detailed data (sanitized)
  details?: {
    // Network request details
    method?: string;
    url?: string;
    status_code?: number;
    request_size?: number;
    response_size?: number;

    // Job details
    job_id?: string;
    job_type?: string;
    progress?: number;

    // Route details
    route?: string;
    handler?: string;

    // Error details
    error_type?: string;
    error_message?: string;
    stack_trace?: string;

    // Generic key-value pairs (all sanitized)
    [key: string]: unknown;
  };
}

/**
 * An interaction represents a single user action and all downstream effects
 */
export interface UELRInteraction {
  // Unique IDs
  interaction_id: string;
  correlation_id: string;

  // Action identification
  action_name: string;
  action_category?: string; // e.g., 'character', 'training', 'generation'

  // Timing
  started_at: string; // ISO 8601
  ended_at?: string;
  duration_ms?: number;

  // Status
  status: StepStatus;

  // Error summary if failed
  error_summary?: string;

  // User context
  page?: string;
  user_agent?: string;

  // Step count summary
  step_count: number;
  error_count: number;

  // Steps are loaded separately for performance
  steps?: UELRStep[];
}

/**
 * Request to create a new interaction
 */
export interface CreateInteractionRequest {
  interaction_id: string;
  correlation_id: string;
  action_name: string;
  action_category?: string;
  page?: string;
  user_agent?: string;
}

/**
 * Request to append steps to an interaction
 */
export interface AppendStepsRequest {
  interaction_id: string;
  steps: Omit<UELRStep, 'interaction_id'>[];
}

/**
 * Request to complete an interaction
 */
export interface CompleteInteractionRequest {
  interaction_id: string;
  status: StepStatus;
  error_summary?: string;
}

/**
 * Response from listing interactions
 */
export interface ListInteractionsResponse {
  interactions: UELRInteraction[];
  total: number;
  has_more: boolean;
}

/**
 * Filter options for listing interactions
 */
export interface InteractionFilter {
  limit?: number;
  offset?: number;
  action_name?: string;
  status?: StepStatus;
  correlation_id?: string;
  from_date?: string;
  to_date?: string;
}

/**
 * Bundle download request
 */
export interface BundleRequest {
  interaction_id: string;
  include_backend_logs?: boolean;
  include_worker_logs?: boolean;
}

// Sensitive fields that should be redacted
export const SENSITIVE_FIELDS = [
  'authorization',
  'cookie',
  'set-cookie',
  'x-api-key',
  'api_key',
  'apikey',
  'token',
  'password',
  'secret',
  'credential',
  'auth',
  'bearer',
  'hf_token',
  'runpod_api_key',
  'github_token',
  'cloudflare_api_token',
] as const;

// Patterns to redact in string values
export const REDACTION_PATTERNS = [
  { pattern: /hf_[A-Za-z0-9]+/g, replacement: 'hf_***REDACTED***' },
  { pattern: /sk-[A-Za-z0-9-]+/g, replacement: 'sk-***REDACTED***' },
  { pattern: /ghp_[A-Za-z0-9]+/g, replacement: 'ghp_***REDACTED***' },
  { pattern: /rpa_[A-Za-z0-9]+/g, replacement: 'rpa_***REDACTED***' },
  { pattern: /Bearer [A-Za-z0-9._-]+/gi, replacement: 'Bearer ***REDACTED***' },
  { pattern: /token=[^&\s]+/gi, replacement: 'token=***' },
  { pattern: /password=[^\s&]+/gi, replacement: 'password=***' },
  { pattern: /api[_-]?key=[^&\s]+/gi, replacement: 'api_key=***' },
] as const;
