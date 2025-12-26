import { ReactNode, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { cn } from '@/lib/utils'
import {
  Users,
  Zap,
  Image,
  Video,
  ChevronLeft,
  ChevronRight,
  Cpu,
  Activity,
} from 'lucide-react'

interface LayoutProps {
  children: ReactNode
}

const navItems = [
  {
    path: '/characters',
    label: 'Characters',
    icon: Users,
    description: 'Manage identities',
  },
  {
    path: '/training',
    label: 'Training',
    icon: Zap,
    description: 'Train LoRA models',
  },
  {
    path: '/generate',
    label: 'Generate',
    icon: Image,
    description: 'Create images',
  },
  {
    path: '/video',
    label: 'Video',
    icon: Video,
    description: 'Coming soon',
    disabled: true,
  },
]

export default function Layout({ children }: LayoutProps) {
  const location = useLocation()
  const [collapsed, setCollapsed] = useState(false)

  return (
    <div className="flex h-screen bg-background overflow-hidden">
      {/* Sidebar */}
      <aside
        className={cn(
          "flex flex-col bg-background-secondary border-r border-border transition-all duration-200",
          collapsed ? "w-16" : "w-56"
        )}
      >
        {/* Logo */}
        <div className="flex items-center h-14 px-4 border-b border-border">
          <Link to="/" className="flex items-center gap-3 overflow-hidden">
            <div className="flex-shrink-0 w-8 h-8 rounded bg-gradient-to-br from-accent to-primary flex items-center justify-center">
              <Cpu className="w-4 h-4 text-white" />
            </div>
            {!collapsed && (
              <span className="font-semibold text-foreground tracking-tight">
                Isengard
              </span>
            )}
          </Link>
        </div>

        {/* Navigation */}
        <nav className="flex-1 py-4 px-2 space-y-1 overflow-y-auto">
          {navItems.map((item) => {
            const isActive = location.pathname === item.path
            return (
              <Link
                key={item.path}
                to={item.disabled ? '#' : item.path}
                className={cn(
                  "flex items-center gap-3 px-3 py-2.5 rounded-md transition-all group",
                  isActive
                    ? "bg-accent-soft text-accent"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted",
                  item.disabled && "opacity-50 cursor-not-allowed"
                )}
                onClick={(e) => item.disabled && e.preventDefault()}
              >
                <item.icon
                  className={cn(
                    "w-5 h-5 flex-shrink-0",
                    isActive ? "text-accent" : "text-muted-foreground group-hover:text-foreground"
                  )}
                />
                {!collapsed && (
                  <div className="flex flex-col min-w-0">
                    <span className="text-sm font-medium truncate">
                      {item.label}
                    </span>
                    <span className="text-xs text-muted-foreground truncate">
                      {item.description}
                    </span>
                  </div>
                )}
                {!collapsed && item.disabled && (
                  <span className="ml-auto text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground">
                    Soon
                  </span>
                )}
              </Link>
            )
          })}
        </nav>

        {/* Status Footer */}
        <div className="px-3 py-3 border-t border-border">
          {!collapsed ? (
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Activity className="w-3.5 h-3.5 text-success" />
              <span>System Ready</span>
            </div>
          ) : (
            <div className="flex justify-center">
              <Activity className="w-4 h-4 text-success" />
            </div>
          )}
        </div>

        {/* Collapse Toggle */}
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="flex items-center justify-center h-10 border-t border-border text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
        >
          {collapsed ? (
            <ChevronRight className="w-4 h-4" />
          ) : (
            <ChevronLeft className="w-4 h-4" />
          )}
        </button>
      </aside>

      {/* Main Content */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Top Bar */}
        <header className="flex items-center justify-between h-14 px-6 border-b border-border bg-background-secondary">
          <div className="flex items-center gap-4">
            <h1 className="text-lg font-medium text-foreground">
              {navItems.find((item) => item.path === location.pathname)?.label || 'Dashboard'}
            </h1>
          </div>
          <div className="flex items-center gap-3 text-sm text-muted-foreground">
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-success pulse-dot" />
              GPU Connected
            </span>
          </div>
        </header>

        {/* Page Content */}
        <main className="flex-1 overflow-y-auto">
          <div className="p-6 max-w-7xl">
            {children}
          </div>
        </main>
      </div>
    </div>
  )
}
