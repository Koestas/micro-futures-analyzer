import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'

function cn(...c) { return c.filter(Boolean).join(' ') }

const pnlColor = (v) => v > 0 ? 'text-green-400' : v < 0 ? 'text-red-400' : 'text-gray-400'
const pnlBg = (v) => v >= 600 ? 'bg-green-900' : v >= 400 ? 'bg-blue-900' : v >= 0 ? 'bg-terminal-border' : 'bg-red-900'

function StatCard({ label, value, sub, color }) {
  return (
    <div className="bg-terminal-card border border-terminal-border rounded p-3">
      <div className="text-xs text-gray-400">{label}</div>
      <div className={cn('text-xl font-bold mt-1', color || 'text-white')}>{value}</div>
      {sub && <div className="text-xs text-gray-500 mt-0.5">{sub}</div>}
    </div>
  )
}

function StrategyCard({ label, data, color }) {
  if (!data) return null
  const p = data.params || {}
  return (
    <div className={cn('bg-terminal-card border rounded p-4', color || 'border-terminal-border')}>
      <div className="text-sm font-bold text-white mb-3">{label}</div>
      <div className="grid grid-cols-3 gap-2 text-xs mb-3">
        <div><div className="text-gray-400">Trades</div><div className="font-bold text-white">{data.total}</div></div>
        <div><div className="text-gray-400">Win Rate</div><div className={cn('font-bold', data.win_rate>=60?'text-green-400':data.win_rate>=50?'text-yellow-400':'text-red-400')}>{data.win_rate}%</div></div>
        <div><div className="text-gray-400">Profit Factor</div><div className={cn('font-bold', data.profit_factor>=2?'text-green-400':'text-yellow-400')}>{data.profit_factor}x</div></div>
        <div><div className="text-gray-400">Avg Win</div><div className="text-green-400 font-bold">${data.avg_win?.toFixed(0)}</div></div>
        <div><div className="text-gray-400">Avg Loss</div><div className="text-red-400 font-bold">${data.avg_loss?.toFixed(0)}</div></div>
        <div><div className="text-gray-400">Max DD</div><div className="text-red-400 font-bold">${data.max_drawdown?.toFixed(0)}</div></div>
        <div><div className="text-gray-400">Avg Daily</div><div className={cn('font-bold', pnlColor(data.avg_daily_pnl))}>${data.avg_daily_pnl?.toFixed(0)}</div></div>
        <div><div className="text-gray-400">Days+</div><div className="text-white font-bold">{data.days_profitable}/{data.total_days}</div></div>
        <div><div className="text-gray-400">Net P&L</div><div className={cn('font-bold', pnlColor(data.gross_pnl))}>${data.gross_pnl?.toFixed(0)}</div></div>
      </div>
      {p.contracts && (
        <div className="text-xs text-gray-500 border-t border-terminal-border pt-2">
          {p.contracts} contracts · stop {p.stop_pts}pts (${p.usd_loss?.toFixed(0)} risk) · TP {p.tp_pts}pts (${p.usd_win?.toFixed(0)})
        </div>
      )}
    </div>
  )
}

export default function ScalpBacktest() {
  const [days, setDays] = useState(14)

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['scalp-backtest', days],
    queryFn: () => fetch(`/api/backtest/scalp?days=${days}`).then(r => r.json()),
    staleTime: 5 * 60_000,
    refetchOnWindowFocus: false,
  })

  const combined = data?.combined || {}
  const strategies = data?.strategies || {}
  const daily = combined.daily || []

  const maxBar = Math.max(...daily.map(d => Math.abs(d.pnl)), 1)

  return (
    <div className="space-y-4 max-w-6xl">

      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-xl font-bold text-white">Scalp + ICT Backtest</h1>
          <p className="text-xs text-gray-400">Real ProjectX 1m/5m bars — same criteria as live bot</p>
        </div>
        <div className="flex gap-2 items-center">
          {[7, 10, 14].map(d => (
            <button key={d} onClick={() => setDays(d)}
              className={cn('px-3 py-1 text-xs rounded border', days===d ? 'bg-blue-700 border-blue-500 text-white' : 'bg-terminal-card border-terminal-border text-gray-400 hover:border-blue-700')}>
              {d}d
            </button>
          ))}
          <button onClick={() => refetch()} className="text-xs text-blue-400 hover:underline ml-2">
            {isLoading ? 'Running...' : 'Run Backtest'}
          </button>
        </div>
      </div>

      {isLoading && (
        <div className="bg-terminal-card border border-terminal-border rounded p-8 text-center">
          <div className="text-blue-400 animate-pulse text-sm">Fetching {days} days of 1m bars from ProjectX and running simulation...</div>
          <div className="text-gray-500 text-xs mt-2">This takes 10-20 seconds (downloading ~15,000 bars)</div>
        </div>
      )}

      {!isLoading && data && (
        <>
          {/* Combined stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <StatCard label="Avg Daily P&L (combined)" value={`$${combined.avg_daily_pnl?.toFixed(0) || 0}`}
              color={pnlColor(combined.avg_daily_pnl)} sub="all strategies combined" />
            <StatCard label="Days ≥ $600 target" value={`${combined.days_over_600}/${combined.total_days}`}
              color={combined.days_over_600 > 0 ? 'text-green-400' : 'text-red-400'} />
            <StatCard label="Days ≥ $400" value={`${combined.days_over_400}/${combined.total_days}`}
              color="text-yellow-400" />
            <StatCard label="Bars analyzed" value={`${((data.bars_fetched?.mnq_1m||0)+(data.bars_fetched?.mgc_1m||0)).toLocaleString()}`}
              sub={`${data.period_days}d window`} />
          </div>

          {/* Strategy breakdown */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <StrategyCard label="MNQ Scalp (1m)" data={strategies.mnq_scalp} color="border-blue-800" />
            <StrategyCard label="MGC Scalp — Asia Only (1m)" data={strategies.mgc_scalp} color="border-yellow-800" />
            <StrategyCard label="MNQ ICT Swings (5m)" data={strategies.mnq_ict} color="border-green-800" />
          </div>

          {/* Daily P&L bar chart */}
          <div className="bg-terminal-card border border-terminal-border rounded p-4">
            <div className="text-xs text-gray-400 font-semibold uppercase mb-3">
              Combined Daily P&L — each bar = scalps + ICT swings that day
            </div>
            <div className="space-y-1">
              {daily.map((d, i) => (
                <div key={i} className="flex items-center gap-2 text-xs">
                  <span className="text-gray-500 w-20 shrink-0">{d.date.slice(5)}</span>
                  <div className="flex-1 flex items-center gap-1">
                    <div className={cn('h-5 rounded text-xs flex items-center px-2 font-bold transition-all',
                      pnlBg(d.pnl), d.pnl >= 0 ? 'text-white' : 'text-red-300')}
                      style={{ width: `${Math.max(4, Math.abs(d.pnl) / maxBar * 100)}%` }}>
                      ${d.pnl >= 0 ? '+' : ''}{d.pnl.toFixed(0)}
                    </div>
                    {d.pnl >= 600 && <span className="text-green-400 text-xs">🎯</span>}
                    {d.pnl < -500 && <span className="text-red-400 text-xs">⚠️</span>}
                  </div>
                </div>
              ))}
            </div>
            <div className="flex gap-4 text-xs text-gray-500 mt-3 pt-3 border-t border-terminal-border">
              <span className="flex items-center gap-1"><span className="w-3 h-3 bg-green-900 rounded inline-block"/>≥$600 target</span>
              <span className="flex items-center gap-1"><span className="w-3 h-3 bg-blue-900 rounded inline-block"/>≥$400</span>
              <span className="flex items-center gap-1"><span className="w-3 h-3 bg-terminal-border rounded inline-block"/>Profitable</span>
              <span className="flex items-center gap-1"><span className="w-3 h-3 bg-red-900 rounded inline-block"/>Loss day</span>
            </div>
          </div>

          {/* Sample trades */}
          {strategies.mnq_scalp?.sample_trades?.length > 0 && (
            <div className="bg-terminal-card border border-terminal-border rounded p-4">
              <div className="text-xs text-gray-400 font-semibold uppercase mb-3">Sample MNQ Scalp Trades</div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead><tr className="text-gray-500 border-b border-terminal-border">
                    <th className="text-left py-1">Date</th><th className="text-left py-1">Time</th>
                    <th className="text-left py-1">Dir</th><th className="text-right py-1">Entry</th>
                    <th className="text-right py-1">Exit</th><th className="text-center py-1">Result</th>
                    <th className="text-right py-1">P&L</th><th className="text-right py-1">ADX</th>
                  </tr></thead>
                  <tbody>
                    {strategies.mnq_scalp.sample_trades.map((t, i) => (
                      <tr key={i} className="border-b border-terminal-border last:border-0">
                        <td className="py-1 text-gray-400">{t.date?.slice(5)}</td>
                        <td className="py-1 text-gray-400">{t.time_et}</td>
                        <td className={cn('py-1 font-bold', t.direction==='bullish'?'text-green-400':'text-red-400')}>
                          {t.direction==='bullish'?'▲':'▼'}
                        </td>
                        <td className="py-1 text-right font-mono">{t.entry}</td>
                        <td className="py-1 text-right font-mono">{t.exit}</td>
                        <td className="py-1 text-center">
                          <span className={cn('px-1 rounded', t.outcome==='win'?'text-green-400':'t.outcome==="loss"?text-red-400':'text-gray-400')}>{t.outcome}</span>
                        </td>
                        <td className={cn('py-1 text-right font-bold', pnlColor(t.pnl))}>${t.pnl>=0?'+':''}{t.pnl}</td>
                        <td className="py-1 text-right text-gray-400">{t.adx}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}

    </div>
  )
}
