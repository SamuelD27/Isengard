/**
 * Loss Chart Component
 *
 * Real-time line chart showing training loss over steps.
 * Uses recharts for visualization with auto-updating data.
 */

import { useMemo } from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { TrendingDown } from 'lucide-react'

interface LossDataPoint {
  step: number
  loss: number
}

interface LossChartProps {
  data: LossDataPoint[]
  currentStep?: number
  totalSteps?: number
}

export function LossChart({ data, currentStep, totalSteps }: LossChartProps) {
  // Calculate min/max for Y axis domain
  const yDomain = useMemo(() => {
    if (data.length === 0) return [0, 1]
    const losses = data.map(d => d.loss).filter(l => l !== null && !isNaN(l))
    if (losses.length === 0) return [0, 1]
    const min = Math.min(...losses)
    const max = Math.max(...losses)
    const padding = (max - min) * 0.1 || 0.1
    return [Math.max(0, min - padding), max + padding]
  }, [data])

  // Format tooltip
  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-background border border-border rounded px-3 py-2 shadow-lg">
          <p className="text-sm text-muted-foreground">Step {label}</p>
          <p className="text-sm font-medium text-foreground">
            Loss: {payload[0].value?.toFixed(4)}
          </p>
        </div>
      )
    }
    return null
  }

  // Calculate trend (is loss decreasing?)
  const trend = useMemo(() => {
    if (data.length < 10) return null
    const recent = data.slice(-10)
    const older = data.slice(-20, -10)
    if (older.length === 0) return null
    const recentAvg = recent.reduce((a, b) => a + b.loss, 0) / recent.length
    const olderAvg = older.reduce((a, b) => a + b.loss, 0) / older.length
    return recentAvg < olderAvg ? 'decreasing' : 'increasing'
  }, [data])

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm flex items-center gap-2">
          <TrendingDown className="h-4 w-4" />
          Training Loss
          {trend && (
            <span className={`text-xs font-normal ${trend === 'decreasing' ? 'text-green-500' : 'text-yellow-500'}`}>
              ({trend})
            </span>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {data.length === 0 ? (
          <div className="h-[200px] flex items-center justify-center text-muted-foreground text-sm">
            Waiting for training data...
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={data} margin={{ top: 5, right: 5, left: -20, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.3} />
              <XAxis
                dataKey="step"
                stroke="hsl(var(--muted-foreground))"
                fontSize={10}
                tickFormatter={(value) => value.toString()}
                domain={[0, totalSteps || 'auto']}
              />
              <YAxis
                stroke="hsl(var(--muted-foreground))"
                fontSize={10}
                domain={yDomain}
                tickFormatter={(value) => value.toFixed(2)}
              />
              <Tooltip content={<CustomTooltip />} />
              <Line
                type="monotone"
                dataKey="loss"
                stroke="hsl(var(--accent))"
                strokeWidth={2}
                dot={false}
                animationDuration={0}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
        {data.length > 0 && (
          <div className="flex justify-between text-xs text-muted-foreground mt-2">
            <span>Start: {data[0]?.loss.toFixed(4)}</span>
            <span>Current: {data[data.length - 1]?.loss.toFixed(4)}</span>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
