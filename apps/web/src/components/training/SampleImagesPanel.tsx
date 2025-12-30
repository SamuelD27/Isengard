/**
 * Sample Images Panel Component
 *
 * Displays training sample images in a grid/carousel.
 * Shows skeleton loading state and empty state.
 * Clicking an image opens a modal with details.
 */

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { RefreshCw, Image as ImageIcon, Maximize2, X } from 'lucide-react'

interface SampleImage {
  name: string
  url: string
  step: number | null
  created_at: string
}

interface SampleImagesPanelProps {
  jobId: string
  isActive: boolean
}

export function SampleImagesPanel({ jobId, isActive }: SampleImagesPanelProps) {
  const [selectedSample, setSelectedSample] = useState<SampleImage | null>(null)

  const {
    data,
    isLoading,
    refetch,
    isFetching,
  } = useQuery({
    queryKey: ['job-samples', jobId],
    queryFn: async () => {
      const response = await fetch(`/api/jobs/${jobId}/artifacts`)
      if (!response.ok) {
        return { artifacts: [] }
      }
      const data = await response.json()
      // Filter only samples from artifacts
      const samples = (data.artifacts || [])
        .filter((a: { type: string }) => a.type === 'sample')
        .map((a: { name: string; url: string; step: number | null; created_at: string }) => ({
          name: a.name,
          url: a.url,
          step: a.step,
          created_at: a.created_at,
        }))
        .slice(-20) // Keep last 20 samples
      return { samples }
    },
    enabled: !!jobId,
    refetchInterval: isActive ? 5000 : false, // Poll every 5s during training
    staleTime: 3000,
  })

  const samples: SampleImage[] = data?.samples || []

  return (
    <>
      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm flex items-center gap-2">
              <ImageIcon className="h-4 w-4" />
              Sample Images ({samples.length})
            </CardTitle>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => refetch()}
              disabled={isFetching}
              title="Refresh samples"
            >
              <RefreshCw className={`h-3 w-3 ${isFetching ? 'animate-spin' : ''}`} />
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex gap-3 overflow-x-auto pb-2">
              {[1, 2, 3, 4].map((i) => (
                <div
                  key={i}
                  className="flex-shrink-0 h-24 w-24 rounded border border-border bg-muted animate-pulse"
                />
              ))}
            </div>
          ) : samples.length === 0 ? (
            <div className="flex items-center justify-center py-8 text-center">
              <div>
                <ImageIcon className="h-8 w-8 mx-auto text-muted-foreground/50 mb-2" />
                <p className="text-sm text-muted-foreground">
                  {isActive
                    ? 'No samples yet. Samples are generated at configured intervals during training.'
                    : 'No sample images were generated during training.'}
                </p>
              </div>
            </div>
          ) : (
            <div className="flex gap-3 overflow-x-auto pb-2">
              {samples.map((sample) => (
                <button
                  key={sample.name}
                  onClick={() => setSelectedSample(sample)}
                  className="flex-shrink-0 relative group"
                >
                  <img
                    src={sample.url}
                    alt={sample.name}
                    className="h-24 w-24 object-cover rounded border border-border hover:border-accent transition-colors"
                    loading="lazy"
                  />
                  <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity rounded flex items-center justify-center">
                    <Maximize2 className="h-5 w-5 text-white" />
                  </div>
                  {sample.step !== null && (
                    <span className="absolute bottom-1 right-1 text-xs bg-black/70 text-white px-1 rounded">
                      #{sample.step}
                    </span>
                  )}
                </button>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Sample Image Modal */}
      {selectedSample && (
        <div
          className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center p-8"
          onClick={() => setSelectedSample(null)}
        >
          <div className="relative max-w-4xl max-h-full" onClick={(e) => e.stopPropagation()}>
            <img
              src={selectedSample.url}
              alt={selectedSample.name}
              className="max-w-full max-h-[80vh] object-contain rounded"
            />
            <div className="absolute bottom-4 left-4 bg-black/70 text-white px-3 py-2 rounded text-sm">
              {selectedSample.step !== null && (
                <div>Step {selectedSample.step}</div>
              )}
              <div className="text-xs text-white/70">
                {new Date(selectedSample.created_at).toLocaleString()}
              </div>
            </div>
            <Button
              variant="ghost"
              size="sm"
              className="absolute top-4 right-4 text-white hover:bg-white/20"
              onClick={() => setSelectedSample(null)}
            >
              <X className="h-5 w-5" />
            </Button>
          </div>
        </div>
      )}
    </>
  )
}
