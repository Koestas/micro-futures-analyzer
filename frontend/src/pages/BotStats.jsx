import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'

function cn(...c) { return c.filter(Boolean).join(' ') }

const COLORS = {
  'Asia':        'text-yellow-400 border-yellow-800',
  'Asia-London': 'text-orange-400 border-orange-800',
  'London':      'text-blue-400  border-blue-800',
  'Pre-Market':  'text-cyan-400  border-cyan-800',
  'NY AM':       'text-green-400 border-green-800',
  'Midday':      'text-gray-400  border-gray-700',
  'NY PM':       'text-purple-400 border-purple-800',
  'Post-Open':   'text-pink-400  border-pink-800',
}

function Stat({ label, value, sub, color }) {
  return (
    <div className="bg-terminal-card border border-terminal-border rounded p-3">
      <div className="text-xs text-gray-400">{label}</div>
      <div className={cn('text-xl font-bold mt-1', color || 'text-white')}>{value}</div>
      {sub && <div className="text-xs text-gray-500 mt-0.5">{sub}</div>}
    </div>
  )
}

export default function BotStats() {
  const [days, setDays] = useState(30)

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['bot-stats', days],
    queryFn: () => fetch(`/api/bot/stats?days=${days}`).then(r => r.json()),
    refetchInterval: 30_000,
  })

  const s = data || {}
  const curve   = s.pnl_curve    || []
  const byDay   = s.by_day       || {}
  const bySess  = s.by_session   || {}
  const trades  = s.recent_trades || []

  const maxCum  = curve.length ? Math.max(...curve.map(c => c.cum_pnl), 0) : 0
  const minCum  = curve.length ? Math.min(...curve.map(c => c.cum_pnl), 0) : 0
  const range   = maxCum - minCum || 1

  // Simple SVG sparkline
  const W = 600, H = 120, pad = 10
  const pts = curve.map((c, i) => {
    const x = pad + (i / Math.max(curve.length - 1, 1)) * (W - 2 * pad)
    const y = H - pad - ((c.cum_pnl - minCum) / range) * (H - 2 * pad)
    return `${x},${y}`
  }).join(' ')

  const pnlColor = (v) => v > 0 ? 'text-green-400' : v < 0 ? 'text-red-400' : 'text-gray-400'

  return (
    <div className="space-y-4 max-w-6xl">

      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-xl font-bold text-white">Bot Performance</h1>
          <p className="text-xs text-gray-400">TopstepX practice account — live trade history from ProjectX API</p>
        </div>
        <div className="flex gap-2 items-center">
          {[7, 14, 30, 60].map(d => (
            <button key={d} onClick={() => setDays(d)}
              className={cn('px-3 py-1 text-xs rounded', days === d ? 'bg-blue-700 text-white' : 'bg-terminal-card text-gray-400 border border-terminal-border hover:border-blue-700')}>
              {d}d
            </button>
          ))}
          <button onClick={() => refetch()} className="text-xs text-blue-400 hover:underline ml-2">Refresh</button>
        </div>
      </div>

      {/* Top stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-3">
        <Stat label="Net P&L"       value={`$${(s.net_pnl||0) >= 0 ? '+' : ''}${(s.net_pnl||0).toFixed(0)}`} color={pnlColor(s.net_pnl)} />
        <Stat label="Today P&L"     value={`$${(s.today_pnl||0) >= 0 ? '+' : ''}${(s.today_pnl||0).toFixed(0)}`} color={pnlColor(s.today_pnl)} />
        <Stat label="Win Rate"      value={`${s.win_rate||0}%`} color={(s.win_rate||0) >= 60 ? 'text-green-400' : (s.win_rate||0) >= 50 ? 'text-yellow-400' : 'text-red-400'} />
        <Stat label="Total Trades"  value={s.total_trades||0} sub={`${s.wins||0}W / ${s.losses||0}L`} />
        <Stat label="Avg Win"       value={`$${(s.avg_win||0).toFixed(0)}`}  color="text-green-400" />
        <Stat label="Avg Loss"      value={`-$${Math.abs(s.avg_loss||0).toFixed(0)}`} color="text-red-400" />
        <Stat label="Profit Factor" value={(s.profit_factor||0).toFixed(2)} color={(s.profit_factor||0) >= 2 ? 'text-green-400' : 'text-yellow-400'} />
        <Stat label="Max Drawdown"  value={`-$${(s.max_drawdown||0).toFixed(0)}`} color="text-red-400" />
      </div>

      {/* Trail mode banner */}
      {s.trail_mode && (
        <div className="bg-yellow-950 border border-yellow-700 rounded p-3 flex items-center gap-3">
          <span className="text-yellow-400 text-lg">⚡</span>
          <div>
            <span className="text-yellow-400 font-bold">TRAIL MODE ACTIVE</span>
            <span className="text-yellow-300 ml-3">Floor locked at ${s.trail_floor?.toFixed(0)}</span>
          </div>
        </div>
      )}

      {/* P&L curve */}
      <div className="bg-terminal-card border border-terminal-border rounded p-4">
        <div className="text-xs text-gray-400 font-semibold uppercase mb-3">Cumulative P&L Curve</div>
        {curve.length < 2 ? (
          <div className="text-gray-600 text-sm italic text-center py-8">No trades yet — waiting for first entry</div>
        ) : (
          <div className="w-full overflow-x-auto">
            <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-28" preserveAspectRatio="none">
              {/* Zero line */}
              <line
                x1={pad} y1={H - pad - (-minCum / range) * (H - 2 * pad)}
                x2={W - pad} y2={H - pad - (-minCum / range) * (H - 2 * pad)}
                stroke="#374151" strokeWidth="1" strokeDasharray="4,4"
              />
              {/* Curve */}
              <polyline points={pts} fill="none" stroke="#3b82f6" strokeWidth="2" />
              {/* Fill under */}
              <polygon
                points={`${pad},${H - pad} ${pts} ${W - pad},${H - pad}`}
                fill="url(#grad)" opacity="0.15"
              />
              <defs>
                <linearGradient id="grad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#3b82f6" />
                  <stop offset="100%" stopColor="#3b82f6" stopOpacity="0" />
                </linearGradient>
              </defs>
            </svg>
            <div className="flex justify-between text-xs text-gray-600 mt-1">
              <span>{curve[0]?.date}</span>
              <span className={pnlColor(s.net_pnl)}>Final: ${(s.net_pnl||0) >= 0 ? '+' : ''}{(s.net_pnl||0).toFixed(0)}</span>
              <span>{curve[curve.length-1]?.date}</span>
            </div>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">

        {/* By session */}
        <div className="bg-terminal-card border border-terminal-border rounded p-4">
          <div className="text-xs text-gray-400 font-semibold uppercase mb-3">By Session</div>
          {Object.keys(bySess).length === 0
            ? <p className="text-gray-600 text-xs italic">No data yet</p>
            : <div className="space-y-2">
                {Object.entries(bySess).sort((a,b) => b[1].pnl - a[1].pnl).map(([sess, d]) => (
                  <div key={sess} className={cn('flex items-center gap-3 p-2 rounded border', COLORS[sess] || 'text-gray-400 border-gray-700')}>
                    <span className="font-bold text-sm w-24">{sess}</span>
                    <span className="text-gray-300 text-xs">{d.trades}T {d.win_rate}%WR</span>
                    <span className={cn('font-bold ml-auto text-sm', pnlColor(d.pnl))}>${d.pnl >= 0 ? '+' : ''}{d.pnl.toFixed(0)}</span>
                  </div>
                ))}
              </div>
          }
        </div>

        {/* Daily P&L */}
        <div className="bg-terminal-card border border-terminal-border rounded p-4">
          <div className="text-xs text-gray-400 font-semibold uppercase mb-3">Daily P&L (last 14 days)</div>
          {Object.keys(byDay).length === 0
            ? <p className="text-gray-600 text-xs italic">No data yet</p>
            : <div className="space-y-1">
                {Object.entries(byDay).slice(-14).reverse().map(([day, d]) => {
                  const barW = Math.min(100, Math.abs(d.pnl) / 10)
                  return (
                    <div key={day} className="flex items-center gap-2 text-xs">
                      <span className="text-gray-500 w-20">{day.slice(5)}</span>
                      <span className="text-gray-400 w-8">{d.trades}T</span>
                      <div className="flex-1 h-4 bg-terminal-border rounded overflow-hidden">
                        <div className={cn('h-full rounded', d.pnl >= 0 ? 'bg-green-700' : 'bg-red-800')}
                          style={{ width: `${barW}%` }} />
                      </div>
                      <span className={cn('w-16 text-right font-bold', pnlColor(d.pnl))}>
                        ${d.pnl >= 0 ? '+' : ''}{d.pnl.toFixed(0)}
                      </span>
                    </div>
                  )
                })}
              </div>
          }
        </div>
      </div>

      {/* Recent trades */}
      <div className="bg-terminal-card border border-terminal-border rounded p-4">
        <div className="text-xs text-gray-400 font-semibold uppercase mb-3">Recent Trades</div>
        {trades.length === 0
          ? <p className="text-gray-600 text-xs italic">No trades in the selected period</p>
          : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-gray-500 border-b border-terminal-border">
                    <th className="text-left py-1">Date</th>
                    <th className="text-left py-1">Time ET</th>
                    <th className="text-left py-1">Symbol</th>
                    <th className="text-left py-1">Side</th>
                    <th className="text-right py-1">Size</th>
                    <th className="text-right py-1">Price</th>
                    <th className="text-left py-1">Session</th>
                    <th className="text-right py-1">P&L</th>
                  </tr>
                </thead>
                <tbody>
                  {[...trades].reverse().map((t, i) => (
                    <tr key={i} className="border-b border-terminal-border last:border-0 hover:bg-terminal-border/20">
                      <td className="py-1 text-gray-400">{t.date}</td>
                      <td className="py-1 text-gray-400">{t.time_et}</td>
                      <td className="py-1 font-bold text-white">{t.symbol}</td>
                      <td className={cn('py-1 font-bold', t.side === 'Long' ? 'text-green-400' : 'text-red-400')}>{t.side}</td>
                      <td className="py-1 text-right text-gray-300">{t.size}</td>
                      <td className="py-1 text-right font-mono text-gray-300">{t.price?.toFixed(2)}</td>
                      <td className="py-1">
                        <span className={cn('px-1.5 py-0.5 rounded text-xs', COLORS[t.session]?.split(' ')[0] || 'text-gray-400')}>
                          {t.session}
                        </span>
                      </td>
                      <td className={cn('py-1 text-right font-bold', pnlColor(t.pnl))}>
                        ${t.pnl >= 0 ? '+' : ''}{t.pnl.toFixed(2)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        }
      </div>

    </div>
  )
}
