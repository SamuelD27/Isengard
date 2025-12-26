import { Construction, Clock, Sparkles } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card'

export default function VideoPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Video Generation</h1>
        <p className="text-muted-foreground">
          Create videos using your trained identity models
        </p>
      </div>

      {/* In Development Banner */}
      <Card className="border-dashed border-2 border-yellow-500/50 bg-yellow-50/50">
        <CardContent className="flex flex-col items-center justify-center py-16 text-center">
          <div className="rounded-full bg-yellow-100 p-4 mb-6">
            <Construction className="h-12 w-12 text-yellow-600" />
          </div>

          <h2 className="text-2xl font-bold mb-2">In Development</h2>

          <p className="text-muted-foreground max-w-md mb-8">
            Video generation is coming in a future release. We're working on integrating
            state-of-the-art video generation models that will work seamlessly with your
            trained identity LoRAs.
          </p>

          <div className="grid gap-6 md:grid-cols-2 text-left max-w-lg">
            <div className="flex gap-3">
              <div className="rounded-lg bg-muted p-2 h-fit">
                <Clock className="h-5 w-5 text-muted-foreground" />
              </div>
              <div>
                <h3 className="font-medium mb-1">Coming Soon</h3>
                <p className="text-sm text-muted-foreground">
                  We're actively developing this feature and will announce when it's ready.
                </p>
              </div>
            </div>

            <div className="flex gap-3">
              <div className="rounded-lg bg-muted p-2 h-fit">
                <Sparkles className="h-5 w-5 text-muted-foreground" />
              </div>
              <div>
                <h3 className="font-medium mb-1">Identity-Aware</h3>
                <p className="text-sm text-muted-foreground">
                  Video generation will use your trained LoRAs for consistent identity.
                </p>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Placeholder Cards */}
      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3 opacity-50 pointer-events-none">
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Text to Video</CardTitle>
            <CardDescription>Generate videos from text prompts</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="h-32 rounded-lg bg-muted flex items-center justify-center text-muted-foreground">
              Preview placeholder
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Image to Video</CardTitle>
            <CardDescription>Animate your generated images</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="h-32 rounded-lg bg-muted flex items-center justify-center text-muted-foreground">
              Preview placeholder
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Video Queue</CardTitle>
            <CardDescription>Your recent video generations</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="h-32 rounded-lg bg-muted flex items-center justify-center text-muted-foreground">
              No videos yet
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
