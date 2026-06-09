import { NavLink } from 'react-router-dom'
import { useState } from 'react'
import {
  LayoutDashboard, Activity, BarChart2, TrendingUp, Zap,
  Table2, Layers, BookOpen, Newspaper, List, History,
  BookMarked, Settings2, ChevronLeft, ChevronRight, Crosshair, ShieldAlert, LineChart,
  GraduationCap, FlaskConical, ClipboardCheck, Bot
} from 'lucide-react'
import { clsx } from 'clsx'

const NAV = [
  { to: '/', icon: LayoutDashboard, label: 'Overview' },
  { to: '/wave', icon: Activity, label: 'WAVE' },
  { to: '/gex', icon: BarChart2, label: 'GEX / Gamma' },
  { to: '/top-flow', icon: TrendingUp, label: 'Top Flow' },
  { to: '/unusual', icon: Zap, label: 'Unusual' },
  { to: '/raw-chain', icon: Table2, label: 'Raw Chain' },
  { to: '/leadership', icon: Layers, label: 'Leadership' },
  { to: '/structure', icon: BookOpen, label: 'Structure' },
  { to: '/bot', icon: Bot, label: 'Live Bot' },
  { to: '/ict', icon: Crosshair, label: 'ICT / SMC' },
  { to: '/checklist', icon: ClipboardCheck, label: 'Pre-Trade Check' },
  { to: '/risk', icon: ShieldAlert, label: 'Risk Manager' },
  { to: '/charts', icon: LineChart, label: 'Charts' },
  { to: '/learn', icon: GraduationCap, label: 'Learn / Practice' },
  { to: '/backtest', icon: FlaskConical, label: 'Backtest' },
  { to: '/news', icon: Newspaper, label: 'News' },
  { to: '/tape', icon: List, label: 'Tape' },
  { to: '/replay', icon: History, label: 'Replay' },
  { to: '/journal', icon: BookMarked, label: 'Journal' },
  { to: '/diagnostics', icon: Settings2, label: 'Diagnostics' },
]

export default function Sidebar() {
  const [collapsed, setCollapsed] = useState(false)

  return (
    <aside className={clsx(
      'fixed left-0 top-[76px] bottom-0 z-40 flex flex-col bg-terminal-card border-r border-terminal-border transition-all duration-200',
      collapsed ? 'w-12' : 'w-44'
    )}>
      <nav className="flex-1 py-2 overflow-y-auto">
        {NAV.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) => clsx(
              'flex items-center gap-3 px-3 py-2 mx-1 rounded transition-colors text-sm',
              isActive
                ? 'text-terminal-blue bg-terminal-blue/10 border-l-2 border-terminal-blue'
                : 'text-terminal-muted hover:text-terminal-text hover:bg-terminal-border/30'
            )}
          >
            <Icon size={15} className="shrink-0" />
            {!collapsed && <span className="truncate">{label}</span>}
          </NavLink>
        ))}
      </nav>

      <button
        onClick={() => setCollapsed(c => !c)}
        className="flex items-center justify-center h-10 border-t border-terminal-border text-terminal-muted hover:text-terminal-text transition-colors"
      >
        {collapsed ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
      </button>
    </aside>
  )
}
