/**
 * DynamicControl - Schema-driven form control component
 *
 * Renders appropriate input based on parameter schema from /api/info.
 * Handles: int, float, enum, bool, string types with validation.
 */

import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ParameterSchema } from '@/lib/api'

interface DynamicControlProps {
  name: string
  schema: ParameterSchema
  value: unknown
  onChange: (value: unknown) => void
  disabled?: boolean
}

export function DynamicControl({
  name,
  schema,
  value,
  onChange,
  disabled = false,
}: DynamicControlProps) {
  const { type, min, max, step, options, description } = schema

  // Format label from snake_case to Title Case
  const label = name
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')

  const handleChange = (newValue: unknown) => {
    if (disabled) return
    onChange(newValue)
  }

  // Render based on type
  switch (type) {
    case 'int':
    case 'float': {
      const numValue = typeof value === 'number' ? value : (schema.default as number) ?? 0
      return (
        <div className="space-y-2">
          <Label htmlFor={name}>{label}</Label>
          <Input
            id={name}
            type="number"
            min={min}
            max={max}
            step={type === 'float' ? (step ?? 0.0001) : 1}
            value={numValue}
            onChange={(e) => {
              const parsed = type === 'int'
                ? parseInt(e.target.value, 10)
                : parseFloat(e.target.value)
              if (!isNaN(parsed)) {
                handleChange(parsed)
              }
            }}
            disabled={disabled}
            className={disabled ? 'opacity-50 cursor-not-allowed' : ''}
          />
          {description && (
            <p className="text-xs text-muted-foreground">{description}</p>
          )}
        </div>
      )
    }

    case 'enum': {
      // Guard against empty or undefined options
      const safeOptions = options && options.length > 0 ? options : [schema.default ?? '']
      const currentValue = value ?? schema.default ?? safeOptions[0]

      return (
        <div className="space-y-2">
          <Label htmlFor={name}>{label}</Label>
          <select
            id={name}
            value={String(currentValue)}
            onChange={(e) => {
              const rawValue = e.target.value
              // Coerce to number if options are numeric
              if (typeof safeOptions[0] === 'number') {
                handleChange(Number(rawValue))
              } else {
                handleChange(rawValue)
              }
            }}
            disabled={disabled}
            className={`flex h-9 w-full rounded-md border border-border bg-input px-3 py-2 text-sm text-foreground focus:outline-none focus:border-accent ${
              disabled ? 'opacity-50 cursor-not-allowed' : ''
            }`}
          >
            {safeOptions.map((opt) => (
              <option key={String(opt)} value={String(opt)}>
                {String(opt)}
              </option>
            ))}
          </select>
          {description && (
            <p className="text-xs text-muted-foreground">{description}</p>
          )}
        </div>
      )
    }

    case 'bool': {
      const boolValue = typeof value === 'boolean' ? value : (schema.default as boolean) ?? false
      return (
        <div className="flex items-center space-x-2">
          <input
            id={name}
            type="checkbox"
            checked={boolValue}
            onChange={(e) => handleChange(e.target.checked)}
            disabled={disabled}
            aria-label={label}
            className={`h-4 w-4 rounded border-border ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
          />
          <Label htmlFor={name} className={disabled ? 'opacity-50' : ''}>
            {label}
          </Label>
          {description && (
            <span className="text-xs text-muted-foreground">({description})</span>
          )}
        </div>
      )
    }

    case 'string':
    default: {
      const strValue = typeof value === 'string' ? value : (schema.default as string) ?? ''
      return (
        <div className="space-y-2">
          <Label htmlFor={name}>{label}</Label>
          <Input
            id={name}
            type="text"
            value={strValue}
            onChange={(e) => handleChange(e.target.value)}
            disabled={disabled}
            className={disabled ? 'opacity-50 cursor-not-allowed' : ''}
          />
          {description && (
            <p className="text-xs text-muted-foreground">{description}</p>
          )}
        </div>
      )
    }
  }
}

/**
 * UnavailableControl - Displays a disabled parameter with reason
 */
interface UnavailableControlProps {
  name: string
  schema: ParameterSchema
}

export function UnavailableControl({ name, schema }: UnavailableControlProps) {
  const label = name
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')

  return (
    <div className="flex items-center justify-between py-2 px-3 rounded-md bg-muted/30 border border-border/50">
      <div>
        <span className="text-sm text-muted-foreground">{label}</span>
        {schema.description && (
          <p className="text-xs text-muted-foreground/70">{schema.description}</p>
        )}
      </div>
      <span className="text-xs text-muted-foreground italic">
        {schema.reason || 'Not supported'}
      </span>
    </div>
  )
}
