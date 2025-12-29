/**
 * UELR Sanitization Tests
 *
 * Tests for the frontend sanitization/redaction functionality.
 */

import { describe, it, expect } from 'vitest'
import {
  redactString,
  sanitize,
  sanitizeBody,
  sanitizeHeaders,
  sanitizeError,
} from './sanitize'

describe('redactString', () => {
  it('should redact Hugging Face tokens', () => {
    const text = 'Using token hf_FAKE_TOKEN_FOR_TESTING_ONLY_XXX for auth'
    const result = redactString(text)
    expect(result).toContain('hf_***REDACTED***')
    expect(result).not.toContain('hf_FAKE_TOKEN_FOR_TESTING_ONLY_XXX')
  })

  it('should redact OpenAI API keys', () => {
    const text = 'API key: sk-proj-abc123def456ghi789'
    const result = redactString(text)
    expect(result).toContain('sk-***REDACTED***')
    expect(result).not.toContain('sk-proj-abc123def456ghi789')
  })

  it('should redact GitHub tokens', () => {
    const text = 'ghp_FAKE_TOKEN_FOR_TESTING_ONLY_XXX is my token'
    const result = redactString(text)
    expect(result).toContain('ghp_***REDACTED***')
    expect(result).not.toContain('ghp_FAKE_TOKEN_FOR_TESTING_ONLY_XXX')
  })

  it('should redact RunPod API keys', () => {
    const text = 'rpa_FAKE_TOKEN_FOR_TESTING_ONLY_XXXXXXXXXXXXX'
    const result = redactString(text)
    expect(result).toContain('rpa_***REDACTED***')
  })

  it('should redact Bearer tokens', () => {
    const text = 'Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test'
    const result = redactString(text)
    expect(result).toContain('Bearer ***REDACTED***')
    expect(result).not.toContain('eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9')
  })

  it('should redact tokens in URLs', () => {
    const text = 'https://api.example.com?token=secret123&other=value'
    const result = redactString(text)
    expect(result).toContain('token=***')
    expect(result).not.toContain('secret123')
  })

  it('should redact passwords', () => {
    const text = 'login?password=mysecretpass123'
    const result = redactString(text)
    expect(result).toContain('password=***')
    expect(result).not.toContain('mysecretpass123')
  })

  it('should preserve safe text', () => {
    const text = 'This is a normal log message about training step 42'
    const result = redactString(text)
    expect(result).toBe(text)
  })

  it('should handle multiple patterns', () => {
    const text = 'Using hf_token123 and ghp_abc456 with password=secret'
    const result = redactString(text)
    expect(result).toContain('hf_***REDACTED***')
    expect(result).toContain('ghp_***REDACTED***')
    expect(result).toContain('password=***')
  })
})

describe('sanitize', () => {
  it('should redact sensitive keys in objects', () => {
    const data = { authorization: 'Bearer token123', message: 'hello' }
    const result = sanitize(data)
    expect(result.authorization).toBe('***REDACTED***')
    expect(result.message).toBe('hello')
  })

  it('should handle nested objects', () => {
    const data = {
      config: {
        password: 'secret',
        host: 'localhost',
      },
      status: 'ok',
    }
    const result = sanitize(data)
    expect(result.config.password).toBe('***REDACTED***')
    expect(result.config.host).toBe('localhost')
    expect(result.status).toBe('ok')
  })

  it('should handle arrays', () => {
    const data = {
      tokens: ['hf_abc123', 'normal'],
      count: 2,
    }
    const result = sanitize(data)
    expect(result.tokens[0]).toBe('hf_***REDACTED***')
    expect(result.tokens[1]).toBe('normal')
    expect(result.count).toBe(2)
  })

  it('should preserve non-string values', () => {
    const data = {
      count: 42,
      enabled: true,
      ratio: 0.95,
      empty: null,
    }
    const result = sanitize(data)
    expect(result.count).toBe(42)
    expect(result.enabled).toBe(true)
    expect(result.ratio).toBe(0.95)
    expect(result.empty).toBeNull()
  })

  it('should apply pattern redaction to string values', () => {
    const data = {
      message: 'Error with token hf_secret123',
    }
    const result = sanitize(data)
    expect(result.message).toContain('hf_***REDACTED***')
  })

  it('should handle undefined and null', () => {
    expect(sanitize(null)).toBeNull()
    expect(sanitize(undefined)).toBeUndefined()
  })
})

describe('sanitizeBody', () => {
  it('should sanitize object bodies', () => {
    const body = { password: 'secret', data: 'value' }
    const result = sanitizeBody(body)
    expect(result.password).toBe('***REDACTED***')
    expect(result.data).toBe('value')
  })

  it('should truncate large bodies', () => {
    const largeBody = { data: 'x'.repeat(20000) }
    const result = sanitizeBody(largeBody, 1000) as { _truncated: boolean }
    expect(result._truncated).toBe(true)
  })

  it('should handle string bodies', () => {
    const body = 'password=secret123&user=test'
    const result = sanitizeBody(body)
    expect(result).toContain('password=***')
    expect(result).toContain('user=test')
  })

  it('should truncate long strings', () => {
    const longString = 'x'.repeat(20000)
    const result = sanitizeBody(longString, 1000) as string
    expect(result.length).toBeLessThan(longString.length)
    expect(result).toContain('TRUNCATED')
  })
})

describe('sanitizeHeaders', () => {
  it('should redact authorization headers', () => {
    const headers: Record<string, string> = {
      'authorization': 'Bearer secret',
      'content-type': 'application/json',
    }
    const result = sanitizeHeaders(headers)
    expect(result['authorization']).toBe('***REDACTED***')
    expect(result['content-type']).toBe('application/json')
  })

  it('should preserve safe headers', () => {
    const headers: Record<string, string> = {
      'content-type': 'application/json',
      'accept': 'application/json',
      'x-correlation-id': 'cor-abc123',
    }
    const result = sanitizeHeaders(headers)
    expect(result['content-type']).toBe('application/json')
    expect(result['accept']).toBe('application/json')
    expect(result['x-correlation-id']).toBe('cor-abc123')
  })
})

describe('sanitizeError', () => {
  it('should extract error info from Error objects', () => {
    const error = new Error('Something failed with token hf_abc123')
    const result = sanitizeError(error)
    expect(result.type).toBe('Error')
    expect(result.message).toContain('hf_***REDACTED***')
    expect(result.stack).toBeDefined()
  })

  it('should handle string errors', () => {
    const error = 'Simple error message'
    const result = sanitizeError(error)
    expect(result.type).toBe('Error')
    expect(result.message).toBe('Simple error message')
  })

  it('should handle unknown error types', () => {
    const error = { code: 500, msg: 'Failed' }
    const result = sanitizeError(error)
    expect(result.type).toBe('UnknownError')
    expect(result.message).toBeDefined()
  })

  it('should truncate long stack traces', () => {
    const error = new Error('Test')
    error.stack = new Array(20).fill('    at function (file.js:1:1)').join('\n')
    const result = sanitizeError(error)
    // Stack should be truncated to 5 lines
    expect(result.stack!.split('\n').length).toBeLessThanOrEqual(5)
  })
})
