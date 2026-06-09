import { useQuery } from '@tanstack/react-query'
import { apiFetch, fmt } from '../lib/api'
import { RefreshCw, Circle, Zap, Bot } from 'lucide-react'
import { clsx } from 'clsx'

function MarketStatus() {
  const now = new Date()
  const et = new Date(now.toLocaleString('en-US', { timeZone: 'America/New_York' }))
  const h = et.getHours(), m = et.getMinutes(), day = et.getDay()
  const mins = h * 60 + m
  if (day === 0 || day === 6) return <span className="badge-muted">WEEKEND</span>
  if (mins < 9 * 60 + 30) return <span className="badge badge-yellow">PRE-MKT</span>
  if (mins < 16 * 60) return <span className="badge-green">OPEN</span>
  return <span className="badge-muted">CLOSED</span>
}

function KillzoneIndicator() {
  const now = new Date()
  const et = new Date(now.toLocaleString('en-US', { timeZone: 'America/New_York' }))
  const mins = et.getHours() * 60 + et.getMinutes()
  const active = et.getDay() > 0 && et.getDay() < 6 && mins >= 9 * 60 + 30 && mins <= 11 * 60 + 30
  if (!active) return null
  return (
    <span className="badge badge-green animate-pulse-slow">
      <Zap size={10} className="mr-1" /> NY KILLZONE
    </span>
  )
}

export default function TopBar() {
  const { data, isLoading, dataUpdatedAt, refetch } = useQuery({
    queryKey: ['overview'],
    queryFn: () => apiFetch('/api/market/overview'),
    refetchInterval: 30_000,
  })

  const { data: futuresData } = useQuery({
    queryKey: ['futures-prices'],
    queryFn: () => apiFetch('/api/market/futures'),
    refetchInterval: 30_000,
  })

  // Live ProjectX quotes — real-time, replaces Yahoo delayed futures prices
  const { data: pxQuotes } = useQuery({
    queryKey: ['topbar-px-quotes'],
    queryFn: () => fetch('/api/projectx/quotes').then(r => r.json()),
    refetchInterval: 5_000,   // every 5 seconds from WebSocket cache
  })

  // Bot status for top bar pill
  const { data: botData } = useQuery({
    queryKey: ['topbar-bot'],
    queryFn: () => fetch('/api/bot/status').then(r => r.json()),
    refetchInterval: 10_000,
  })

  const price = data?.price
  const bias = data?.bias
  const wave = data?.wave_summary
  const leadership = data?.leadership_summary
  const isUp = (price?.change_pct || 0) >= 0

  const biasColor = bias?.score > 25 ? 'text-terminal-green'
    : bias?.score < -25 ? 'text-terminal-red'
    : 'text-terminal-yellow'

  return (
    <div className="fixed top-0 left-0 right-0 z-50 h-12 bg-terminal-card border-b border-terminal-border flex items-center px-4 gap-4 text-xs overflow-x-auto">
      {/* Logo */}
      <div className="text-terminal-blue font-bold text-sm shrink-0 mr-2">MFA</div>

      {/* QQQ Price */}
      <div className="flex items-center gap-1 shrink-0">
        <span className="text-terminal-muted">QQQ</span>
        <span className={`font-bold text-sm ${isUp ? 'text-terminal-green' : 'text-terminal-red'}`}>
          {isLoading ? '...' : fmt.price(price?.price)}
        </span>
        <span className={isUp ? 'text-terminal-green' : 'text-terminal-red'}>
          {isLoading ? '' : fmt.pct(price?.change_pct)}
        </span>
      </div>

      <div className="w-px h-6 bg-terminal-border shrink-0" />

      {/* VWAP */}
      <div className="flex items-center gap-1 shrink-0">
        <span className="text-terminal-muted">VWAP</span>
        <span className={data?.vwap_status === 'above' ? 'text-terminal-green font-semibold' : 'text-terminal-red font-semibold'}>
          {isLoading ? '...' : (data?.vwap_status === 'above' ? '▲ Above' : '▼ Below')}
        </span>
      </div>

      <div className="w-px h-6 bg-terminal-border shrink-0" />

      {/* Bias */}
      <div className="flex items-center gap-1 shrink-0">
        <span className="text-terminal-muted">Bias</span>
        <span className={`font-bold ${biasColor}`}>
          {isLoading ? '...' : (bias?.label || '--')}
        </span>
        {bias?.score != null && (
          <span className="text-terminal-muted">({bias.score > 0 ? '+' : ''}{bias.score})</span>
        )}
      </div>

      <div className="w-px h-6 bg-terminal-border shrink-0" />

      {/* Confidence */}
      <div className="flex items-center gap-1 shrink-0">
        <span className="text-terminal-muted">Conf</span>
        <span className="text-terminal-text font-semibold">
          {isLoading ? '...' : (bias?.confidence != null ? `${bias.confidence}%` : '--')}
        </span>
      </div>

      <div className="w-px h-6 bg-terminal-border shrink-0" />

      {/* Net Premium */}
      <div className="flex items-center gap-1 shrink-0">
        <span className="text-terminal-muted">Net Prem</span>
        <span className={clsx('font-semibold', (wave?.net_wave || 0) >= 0 ? 'text-terminal-green' : 'text-terminal-red')}>
          {isLoading ? '...' : fmt.premium(wave?.net_wave)}
        </span>
      </div>

      <div className="w-px h-6 bg-terminal-border shrink-0" />

      {/* Leadership */}
      <div className="flex items-center gap-1 shrink-0">
        <span className="text-terminal-muted">Leaders</span>
        <span className="text-terminal-text">
          {isLoading ? '...' : (leadership ? `${leadership.green}/${leadership.total}` : '--')}
        </span>
        <span className="text-terminal-muted">green</span>
      </div>

      <div className="w-px h-6 bg-terminal-border shrink-0" />

      {/* Futures: live from ProjectX WebSocket, fallback to Yahoo */}
      {['MNQ', 'MES', 'MGC'].map(sym => {
        const liveQ = pxQuotes?.quotes?.[sym]
        const yahooF = futuresData?.find(f => f.instrument === sym)
        const price = liveQ?.lastPrice ?? yahooF?.price
        const chgPct = liveQ?.changePct ?? yahooF?.change_pct
        const isLive = !!liveQ
        const up = (chgPct || 0) >= 0
        return (
          <div key={sym} className="flex items-center gap-1 shrink-0">
            <span className="text-terminal-muted text-xs">{sym}</span>
            {isLive && <span className="text-green-500 text-xs">●</span>}
            <span className={`font-bold text-sm ${up ? 'text-terminal-green' : 'text-terminal-red'}`}>
              {price != null ? (sym === 'MGC' ? price.toFixed(1) : Math.round(price).toLocaleString()) : '--'}
            </span>
            <span className={`text-xs ${up ? 'text-terminal-green' : 'text-terminal-red'}`}>
              {chgPct != null ? `${up ? '+' : ''}${chgPct.toFixed(2)}%` : ''}
            </span>
            <div className="w-px h-6 bg-terminal-border shrink-0 ml-1" />
          </div>
        )
      })}

      {/* Regime */}
      <div className="flex items-center gap-1 shrink-0">
        <span className="text-terminal-muted">Regime</span>
        <span className="text-terminal-blue font-semibold">
          {isLoading ? '...' : (bias?.regime || '--')}
        </span>
      </div>

      <div className="flex-1" />

      {/* Bot status pill */}
      {botData && (
        <a href="/bot" className={clsx(
          'flex items-center gap-1 px-2 py-0.5 rounded text-xs font-bold border shrink-0',
          botData.running
            ? 'bg-green-950 border-green-700 text-green-400'
            : 'bg-terminal-card border-terminal-border text-gray-500'
        )}>
          <Bot size={10} />
          {botData.running ? `BOT ● $${(botData.daily_pnl || 0) >= 0 ? '+' : ''}${(botData.daily_pnl || 0).toFixed(0)}` : 'BOT ○'}
        </a>
      )}

      {/* Status indicators */}
      <KillzoneIndicator />
      <MarketStatus />

      {/* Last updated */}
      <span className="text-terminal-muted shrink-0">
        {dataUpdatedAt ? fmt.timeAgo(new Date(dataUpdatedAt).toISOString()) : ''}
      </span>

      <button
        onClick={() => refetch()}
        className="text-terminal-muted hover:text-terminal-blue transition-colors shrink-0"
        title="Refresh"
      >
        <RefreshCw size={13} />
      </button>
    </div>
  )
}
