import { ReactNode } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { Users, Zap, Image, Video, Settings } from 'lucide-react'

interface LayoutProps {
  children: ReactNode
}

const navItems = [
  { path: '/characters', label: 'Characters', icon: Users },
  { path: '/training', label: 'Training', icon: Zap },
  { path: '/generate', label: 'Image Gen', icon: Image },
  { path: '/video', label: 'Video', icon: Video, badge: 'Soon' },
]

export default function Layout({ children }: LayoutProps) {
  const location = useLocation()

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="container flex h-14 items-center">
          <div className="mr-4 flex">
            <Link to="/" className="mr-6 flex items-center space-x-2">
              <div className="h-8 w-8 rounded-lg bg-primary flex items-center justify-center">
                <span className="text-primary-foreground font-bold text-lg">I</span>
              </div>
              <span className="font-bold text-xl">Isengard</span>
            </Link>
          </div>

          <nav className="flex items-center space-x-6 text-sm font-medium">
            {navItems.map((item) => (
              <Link
                key={item.path}
                to={item.path}
                className={cn(
                  "flex items-center gap-2 transition-colors hover:text-foreground/80",
                  location.pathname === item.path
                    ? "text-foreground"
                    : "text-foreground/60"
                )}
              >
                <item.icon className="h-4 w-4" />
                {item.label}
                {item.badge && (
                  <span className="text-xs bg-muted px-1.5 py-0.5 rounded text-muted-foreground">
                    {item.badge}
                  </span>
                )}
              </Link>
            ))}
          </nav>

          <div className="flex flex-1 items-center justify-end space-x-2">
            <button className="inline-flex items-center justify-center rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 hover:bg-accent hover:text-accent-foreground h-10 w-10">
              <Settings className="h-4 w-4" />
              <span className="sr-only">Settings</span>
            </button>
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="container py-6">
        {children}
      </main>

      {/* Footer */}
      <footer className="border-t py-6">
        <div className="container flex items-center justify-between text-sm text-muted-foreground">
          <p>Isengard v0.1.0</p>
          <p>Identity LoRA Training Platform</p>
        </div>
      </footer>
    </div>
  )
}
