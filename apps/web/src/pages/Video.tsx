import { Clock, Sparkles, Video as VideoIcon } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'

export default function VideoPage() {
  return (
    <div className="space-y-6 fade-in">
      {/* Page Header */}
      <div>
        <p className="text-sm text-muted-foreground">
          Create videos with trained identity models
        </p>
      </div>

      {/* In Development Notice */}
      <Card className="border-warning/30">
        <CardContent className="flex flex-col items-center justify-center py-16 text-center">
          <div className="rounded-full bg-warning-soft p-4 mb-6">
            <VideoIcon className="h-8 w-8 text-warning" />
          </div>

          <h2 className="text-xl font-medium text-foreground mb-2">Coming Soon</h2>

          <p className="text-sm text-muted-foreground max-w-md mb-8">
            Video generation is under development. We're integrating state-of-the-art
            video models that will work with your trained identity LoRAs.
          </p>

          <div className="grid gap-4 md:grid-cols-2 text-left max-w-lg">
            <div className="flex gap-3 p-4 rounded-md bg-muted">
              <Clock className="h-5 w-5 text-muted-foreground flex-shrink-0 mt-0.5" />
              <div>
                <h3 className="text-sm font-medium text-foreground mb-1">In Progress</h3>
                <p className="text-xs text-muted-foreground">
                  Active development with regular updates
                </p>
              </div>
            </div>

            <div className="flex gap-3 p-4 rounded-md bg-muted">
              <Sparkles className="h-5 w-5 text-muted-foreground flex-shrink-0 mt-0.5" />
              <div>
                <h3 className="text-sm font-medium text-foreground mb-1">Identity-Aware</h3>
                <p className="text-xs text-muted-foreground">
                  Will use your trained LoRAs for consistency
                </p>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
