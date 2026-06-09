import { useQuery } from '@tanstack/react-query'
import { apiFetch, fmt } from '../lib/api'
import BiasPanel from '../components/BiasPanel'
import ErrorBoundary from '../components/ErrorBoundary'
import { CardSkeleton, ChartSkeleton } from '../components/LoadingSkeleton'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { clsx } from 'clsx'
import { ChevronDown, ChevronUp } from 'lucide-react'
import { useState } from 'react'

function StatCard({ label, value, sub, color = 'text-terminal-text' }) {
  return (
    <div className="card">
      <div className="stat-label">{label}</div>
      <div className={`stat-value mt-1 ${color}`}>{value}</div>
      {sub && <div className="text-xs text-terminal-muted mt-1">{sub}</div>}
    </div>
  )
}

const DAILY_LIMIT = 1000

function DailyPnLCard() {
  const today = new Date().toISOString().slice(0, 10)
  const [pnl, setPnl] = useState(() => {
    try {
      const s = JSON.parse(localStorage.getItem('daily_pnl') || '{}')
      return s.date === today ? (s.pnl ?? 0) : 0
    } catch { return 0 }
  })
  const [input, setInput] = useState('')

  const save = (v) => {
    const rounded = Math.round(v * 100) / 100
    localStorage.setItem('daily_pnl', JSON.stringify({ date: today, pnl: rounded }))
    setPnl(rounded)
  }

  const addTrade = (e) => {
    e.preventDefault()
    const val = parseFloat(input)
    if (isNaN(val)) return
    save(pnl + val)
    setInput('')
  }

  const isLoss    = pnl < 0
  const usedPct   = Math.min(Math.abs(pnl) / DAILY_LIMIT * 100, 100)
  const barColor  = isLoss
    ? (usedPct >= 75 ? 'bg-terminal-red' : usedPct >= 50 ? 'bg-terminal-yellow' : 'bg-terminal-yellow/60')
    : 'bg-terminal-green'
  const pnlColor  = isLoss
    ? (usedPct >= 75 ? 'text-terminal-red' : 'text-terminal-yellow')
    : 'text-terminal-green'
  const dateStr   = new Date().toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', timeZone: 'America/New_York' })

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-2">
        <span className="stat-label">TODAY'S P&amp;L</span>
        <span className="text-[10px] text-terminal-muted">{dateStr}</span>
      </div>
      <div className={`font-mono font-bold text-2xl ${pnlColor} mb-1`}>
        {pnl >= 0 ? '+' : ''}${Math.abs(pnl).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
      </div>
      {/* Loss limit bar */}
      <div className="relative h-1.5 bg-terminal-border rounded-full overflow-hidden mb-1.5">
        <div className={`h-full rounded-full transition-all duration-500 ${barColor}`} style={{ width: `${usedPct}%` }} />
      </div>
      <div className="text-[10px] text-terminal-muted mb-2.5">
        {isLoss
          ? `${usedPct.toFixed(0)}% of $${DAILY_LIMIT.toLocaleString()} daily loss limit`
          : 'Green day — protect your profits'}
      </div>
      <form onSubmit={addTrade} className="flex gap-1">
        <input
          type="number"
          step="0.01"
          value={input}
          onChange={e => setInput(e.target.value)}
          placeholder="+250 or -150"
          className="flex-1 min-w-0 bg-terminal-bg border border-terminal-border rounded px-2 py-1 text-xs text-terminal-text placeholder:text-terminal-muted/50 focus:outline-none focus:border-terminal-blue"
        />
        <button type="submit"
          className="px-2 py-1 rounded bg-terminal-blue/20 border border-terminal-blue/40 text-terminal-blue text-xs hover:bg-terminal-blue/30 transition-colors whitespace-nowrap">
          + Add
        </button>
        {pnl !== 0 && (
          <button type="button" onClick={() => save(0)}
            className="px-2 py-1 rounded border border-terminal-border/60 text-terminal-muted text-xs hover:text-terminal-text transition-colors">
            Reset
          </button>
        )}
      </form>
    </div>
  )
}

function Tech9Card({ data, isLoading }) {
  if (isLoading) return (
    <div className="card animate-pulse">
      <div className="stat-label mb-2">TECH-9 BREADTH</div>
      <div className="grid grid-cols-3 gap-1.5">
        {Array(9).fill(0).map((_, i) => (
          <div key={i} className="h-6 rounded bg-terminal-border/40" />
        ))}
      </div>
    </div>
  )
  const stocks = data?.stocks || []
  const greenCount = data?.green_count ?? 0
  const redCount = data?.red_count ?? 0
  const allRed   = redCount === 9
  const allGreen = greenCount === 9
  const broadStrength = greenCount >= 7
  const breadthColor = broadStrength ? 'text-terminal-green' : redCount >= 7 ? 'text-terminal-red' : 'text-terminal-yellow'

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-2">
        <span className="stat-label">TECH-9 BREADTH</span>
        <span className={`text-[10px] font-bold ${breadthColor}`}>{greenCount}/9 green</span>
      </div>
      <div className="grid grid-cols-3 gap-1 mb-2">
        {stocks.map((s) => (
          <div key={s.ticker} className={`flex items-center justify-between px-1.5 py-0.5 rounded text-[10px] font-mono
            ${s.bullish ? 'bg-terminal-green/10 text-terminal-green' : 'bg-terminal-red/10 text-terminal-red'}`}>
            <span className="font-bold">{s.ticker === 'GOOGL' ? 'GOOG' : s.ticker}</span>
            <span>{s.change_pct != null ? `${s.change_pct > 0 ? '+' : ''}${s.change_pct.toFixed(1)}%` : '--'}</span>
          </div>
        ))}
      </div>
      {allRed && (
        <div className="text-[10px] text-terminal-red bg-terminal-red/10 border border-terminal-red/20 rounded px-2 py-1 text-center font-bold">
          FADE SIGNAL — All 9 red, watch for fake pump
        </div>
      )}
      {allGreen && (
        <div className="text-[10px] text-terminal-green bg-terminal-green/10 border border-terminal-green/20 rounded px-2 py-1 text-center font-bold">
          BROAD STRENGTH — All 9 confirming
        </div>
      )}
      {!allRed && !allGreen && broadStrength && (
        <div className="text-[10px] text-terminal-green bg-terminal-green/10 border border-terminal-green/20 rounded px-2 py-1 text-center">
          {greenCount}/9 leading — broad NASDAQ strength
        </div>
      )}
      {!allRed && !allGreen && !broadStrength && redCount >= 7 && (
        <div className="text-[10px] text-terminal-red bg-terminal-red/10 border border-terminal-red/20 rounded px-2 py-1 text-center">
          {redCount}/9 red — broad NASDAQ weakness
        </div>
      )}
    </div>
  )
}

function ExplainPanel({ title, children }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="border border-terminal-border/40 rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-4 py-2 text-xs text-terminal-muted hover:text-terminal-text bg-terminal-card2 transition-colors"
      >
        <span className="uppercase tracking-wider">{title}</span>
        {open ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
      </button>
      {open && (
        <div className="px-4 py-3 bg-terminal-card text-xs text-terminal-muted space-y-1">
          {children}
        </div>
      )}
    </div>
  )
}

export default function Overview() {
  const { data, isLoading } = useQuery({
    queryKey: ['overview'],
    queryFn: () => apiFetch('/api/market/overview'),
    refetchInterval: 30_000,
  })

  const { data: waveData, isLoading: waveLoading } = useQuery({
    queryKey: ['wave'],
    queryFn: () => apiFetch('/api/flow/wave'),
    refetchInterval: 20_000,
  })

  const { data: unusualData } = useQuery({
    queryKey: ['unusual'],
    queryFn: () => apiFetch('/api/flow/unusual'),
    refetchInterval: 30_000,
  })

  const { data: newsData } = useQuery({
    queryKey: ['news'],
    queryFn: () => apiFetch('/api/market/news'),
    refetchInterval: 60_000,
  })

  const { data: tech9Data, isLoading: tech9Loading } = useQuery({
    queryKey: ['tech9'],
    queryFn: () => apiFetch('/api/market/tech9'),
    refetchInterval: 30_000,
    staleTime: 20_000,
  })

  const { data: botData } = useQuery({
    queryKey: ['overview-bot'],
    queryFn: () => fetch('/api/bot/status').then(r => r.json()),
    refetchInterval: 10_000,
  })

  const { data: thinkData } = useQuery({
    queryKey: ['overview-thinking'],
    queryFn: () => fetch('/api/bot/thinking').then(r => r.json()),
    refetchInterval: 30_000,
    enabled: botData?.running,
  })

  const price = data?.price
  const wave = data?.wave_summary
  const leadership = data?.leadership_summary
  const session = data?.session
  const unusual = unusualData?.contracts || []
  const news = newsData?.news || []
  const history = waveData?.history || []

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold text-terminal-text">Overview</h1>
        {session && (
          <div className="flex items-center gap-2 text-xs">
            <span className={clsx('badge', session.in_killzone ? 'badge-green' : 'badge-muted')}>
              {session.session}
            </span>
            <span className="text-terminal-muted">{session.time_et}</span>
          </div>
        )}
      </div>

      {session?.session_note && (
        <div className="text-xs text-terminal-yellow/80 bg-terminal-yellow/5 border border-terminal-yellow/20 rounded px-3 py-2">
          {session.session_note}
        </div>
      )}

      {/* Bot Status Widget */}
      {botData && (
        <a href="/bot" className="block no-underline">
          <div className={`rounded border p-3 flex items-center gap-4 text-sm cursor-pointer hover:border-green-600 transition-colors ${
            botData.running ? 'border-green-800 bg-green-950/30' : 'border-terminal-border bg-terminal-card'
          }`}>
            <div className={`text-lg font-bold ${botData.running ? 'text-green-400' : 'text-gray-500'}`}>
              {botData.running ? '● BOT LIVE' : '○ BOT STOPPED'}
            </div>
            <div className="flex gap-4 text-xs flex-wrap">
              <span><span className="text-gray-400">Session </span><span className="text-white font-semibold">{botData.current_session || '—'}</span></span>
              <span><span className="text-gray-400">Today </span><span className={`font-bold ${(botData.daily_pnl||0)>=0?'text-green-400':'text-red-400'}`}>${(botData.daily_pnl||0)>=0?'+':''}{(botData.daily_pnl||0).toFixed(0)}</span></span>
              <span><span className="text-gray-400">Target </span><span className="text-yellow-400">${botData.daily_target||600}</span></span>
              <span><span className="text-gray-400">Trades </span><span className="text-white">{botData.trades_today||0} ICT + {botData.scalp_today||0} scalps</span></span>
              {botData.trail_mode && <span className="text-yellow-400 font-bold animate-pulse">⚡ TRAIL MODE — floor ${botData.trail_floor?.toFixed(0)}</span>}
            </div>
            {thinkData && (
              <div className="flex gap-3 text-xs ml-auto flex-wrap">
                {['MNQ','MES','MGC'].map(sym => {
                  const t = thinkData.instruments?.[sym]
                  if (!t) return null
                  return (
                    <div key={sym} className={`px-2 py-0.5 rounded border font-mono ${t.ready ? 'border-green-600 text-green-400' : 'border-gray-700 text-gray-500'}`}>
                      {sym} {t.best_score}/{t.min_score}
                      {t.scalp_ready && <span className="text-yellow-400 ml-1">⚡</span>}
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </a>
      )}

      {/* Bias Panel */}
      <ErrorBoundary>
        {isLoading ? <CardSkeleton /> : <BiasPanel bias={data?.bias} wave={wave} />}
      </ErrorBoundary>

      {/* Stat Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        <ErrorBoundary>
          <DailyPnLCard />
        </ErrorBoundary>
        <ErrorBoundary>
          {isLoading ? <CardSkeleton /> : (
            <StatCard
              label="QQQ Price"
              value={fmt.price(price?.price)}
              sub={`${fmt.pct(price?.change_pct)} today`}
              color={(price?.change_pct || 0) >= 0 ? 'text-terminal-green' : 'text-terminal-red'}
            />
          )}
        </ErrorBoundary>
        <ErrorBoundary>
          {isLoading ? <CardSkeleton /> : (
            <StatCard
              label="Net Premium"
              value={fmt.premium(wave?.net_wave)}
              sub={wave?.wave_direction}
              color={(wave?.net_wave || 0) >= 0 ? 'text-terminal-green' : 'text-terminal-red'}
            />
          )}
        </ErrorBoundary>
        <ErrorBoundary>
          {isLoading ? <CardSkeleton /> : (
            <StatCard
              label="Call/Put Ratio"
              value={wave?.call_put_ratio ? wave.call_put_ratio.toFixed(2) : '--'}
              sub={wave?.call_dominance_pct ? `${wave.call_dominance_pct.toFixed(1)}% call dominance` : ''}
              color="text-terminal-text"
            />
          )}
        </ErrorBoundary>
        <ErrorBoundary>
          {isLoading ? <CardSkeleton /> : (
            <StatCard
              label="Leadership"
              value={leadership ? `${leadership.green}/${leadership.total}` : '--'}
              sub={leadership ? `${leadership.breadth_pct}% green` : ''}
              color={leadership?.breadth_pct >= 60 ? 'text-terminal-green' : leadership?.breadth_pct <= 40 ? 'text-terminal-red' : 'text-terminal-yellow'}
            />
          )}
        </ErrorBoundary>
      </div>

      {/* Tech-9 Breadth */}
      <ErrorBoundary>
        <Tech9Card data={tech9Data} isLoading={tech9Loading} />
      </ErrorBoundary>

      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* WAVE chart */}
        <ErrorBoundary>
          <div className="card">
            <div className="stat-label mb-3">WAVE — Call vs Put Premium</div>
            {waveLoading || history.length === 0 ? (
              <ChartSkeleton height={160} />
            ) : (
              <ResponsiveContainer width="100%" height={160}>
                <AreaChart data={history} margin={{ top: 4, right: 0, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id="callGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#00ff88" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#00ff88" stopOpacity={0} />
                    </linearGradient>
                    <linearGradient id="putGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#ff4466" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#ff4466" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="timestamp" hide />
                  <YAxis hide />
                  <Tooltip
                    contentStyle={{ background: '#0f1623', border: '1px solid #1e2d40', fontSize: 11 }}
                    formatter={(v, name) => [fmt.premium(v), name]}
                  />
                  <Area type="monotone" dataKey="call_wave" stroke="#00ff88" fill="url(#callGrad)" strokeWidth={1.5} name="Calls" dot={false} />
                  <Area type="monotone" dataKey="put_wave" stroke="#ff4466" fill="url(#putGrad)" strokeWidth={1.5} name="Puts" dot={false} />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>
        </ErrorBoundary>

        {/* Levels card */}
        <ErrorBoundary>
          <div className="card space-y-2">
            <div className="stat-label mb-1">Key Levels</div>
            {isLoading ? <CardSkeleton /> : (
              <div className="space-y-2 text-sm">
                {[
                  { label: 'VWAP', value: fmt.price(data?.vwap), status: data?.vwap_status },
                  { label: 'Call Wall', value: fmt.price(data?.call_wall) },
                  { label: 'Put Wall', value: fmt.price(data?.put_wall) },
                  { label: 'Day High', value: fmt.price(price?.day_high) },
                  { label: 'Day Low', value: fmt.price(price?.day_low) },
                ].map(({ label, value, status }) => (
                  <div key={label} className="flex items-center justify-between">
                    <span className="text-terminal-muted">{label}</span>
                    <div className="flex items-center gap-2">
                      <span className="text-terminal-text font-semibold">{value}</span>
                      {status && (
                        <span className={clsx('badge text-xs', status === 'above' ? 'badge-green' : 'badge-red')}>
                          {status}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </ErrorBoundary>
      </div>

      {/* Unusual activity */}
      {unusual.length > 0 && (
        <ErrorBoundary>
          <div className="card">
            <div className="stat-label mb-3">Recent Unusual Activity</div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr>
                    {['Contract', 'Premium', 'Vol/OI', 'Signal', 'Reason'].map(h => (
                      <th key={h} className="table-header">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {unusual.slice(0, 5).map((c, i) => (
                    <tr key={i} className={c.side === 'call' ? 'bg-terminal-green/5' : 'bg-terminal-red/5'}>
                      <td className="table-cell font-semibold">
                        QQQ {c.strike} {c.side?.toUpperCase()} {c.expiration}
                      </td>
                      <td className={`table-cell font-semibold ${c.side === 'call' ? 'text-terminal-green' : 'text-terminal-red'}`}>
                        {fmt.premium(c.estimated_premium)}
                      </td>
                      <td className="table-cell">{c.volume_oi_ratio?.toFixed(1)}x</td>
                      <td className="table-cell">
                        <span className={c.side === 'call' ? 'badge-green' : 'badge-red'}>
                          {c.side === 'call' ? '▲ Bullish' : '▼ Bearish'}
                        </span>
                      </td>
                      <td className="table-cell text-terminal-muted">
                        {c.unusual_reasons?.[0] || '--'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </ErrorBoundary>
      )}

      {/* News feed */}
      {news.length > 0 && (
        <ErrorBoundary>
          <div className="card">
            <div className="stat-label mb-3">Latest News</div>
            <div className="space-y-2">
              {news.slice(0, 5).map((item, i) => (
                <div key={i} className="flex items-start gap-2 py-1 border-b border-terminal-border/30 last:border-0">
                  <span className={clsx('badge mt-0.5 shrink-0',
                    item.sentiment === 'bullish' ? 'badge-green' :
                    item.sentiment === 'bearish' ? 'badge-red' : 'badge-muted'
                  )}>
                    {item.sentiment}
                  </span>
                  <div>
                    <div className="text-xs text-terminal-text">{item.title}</div>
                    <div className="text-xs text-terminal-muted">{item.publisher} · {fmt.timeAgo(item.timestamp)}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </ErrorBoundary>
      )}

      <ExplainPanel title="How to use the Overview">
        <p>Start here before every trade. This tab answers: <strong className="text-terminal-text">Should I look for longs, shorts, or no trade?</strong></p>
        <p className="mt-1">The <strong className="text-terminal-green">Bias Score</strong> combines VWAP position, WAVE direction, leadership breadth, and price momentum into a single -100 to +100 reading.</p>
        <p className="mt-1"><strong className="text-terminal-yellow">Important:</strong> Wait for the NY Killzone (9:30–11:30 AM ET) for highest-quality setups. Avoid first 5 minutes.</p>
      </ExplainPanel>
    </div>
  )
}
