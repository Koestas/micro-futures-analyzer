import { useQuery } from '@tanstack/react-query'

const DOW = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat']

function Badge({ value, positive }) {
  if (value === null || value === undefined) return <span className="text-gray-500">—</span>
  const good = positive ? value > 0 : value < 0
  return (
    <span className={good ? 'text-green-400 font-bold' : value === 0 ? 'text-gray-400' : 'text-red-400 font-bold'}>
      {typeof value === 'number' && value % 1 !== 0 ? value.toFixed(1) : value}{typeof value === 'number' && String(value).includes('.') ? '' : ''}
    </span>
  )
}

export default function Analytics() {
  const { data, isLoading } = useQuery({
    queryKey: ['analytics-summary'],
    queryFn: () => fetch('/api/analytics/summary').then(r => r.json()),
    refetchInterval: 60_000,
  })

  if (isLoading) return <div className="p-6 text-gray-400">Loading analytics…</div>

  const winRates    = data?.win_rates ?? []
  const scoreBands  = data?.score_bands ?? []
  const ghostTrades = data?.ghost_trades ?? []
  const suggestions = data?.suggestions ?? []
  const heatmap     = data?.heatmap ?? []

  // Build heatmap grid: [dow][hour] = {total_pnl, trades, win_pct}
  const heatGrid = {}
  for (const row of heatmap) {
    if (!heatGrid[row.dow]) heatGrid[row.dow] = {}
    heatGrid[row.dow][row.hour_et] = row
  }
  const allPnls = heatmap.map(r => r.total_pnl).filter(Boolean)
  const maxAbs  = Math.max(...allPnls.map(Math.abs), 1)

  return (
    <div className="p-4 space-y-6 max-w-7xl mx-auto">
      <div>
        <h1 className="text-xl font-bold text-white">Bot Analytics — Learning Engine</h1>
        <p className="text-xs text-gray-400 mt-0.5">
          Win rates, ghost trade outcomes, and threshold suggestions based on all logged trades.
        </p>
      </div>

      {/* ── Win Rates by Session ── */}
      <section>
        <h2 className="text-sm font-semibold text-gray-300 mb-2 uppercase tracking-wide">Win Rate by Session</h2>
        {winRates.length === 0
          ? <p className="text-gray-500 text-sm">No completed trades yet — data builds as the bot trades.</p>
          : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead>
                <tr className="text-gray-400 border-b border-terminal-border">
                  <th className="pb-2 pr-4">Session</th>
                  <th className="pb-2 pr-4">Instrument</th>
                  <th className="pb-2 pr-4">Trades</th>
                  <th className="pb-2 pr-4">Win %</th>
                  <th className="pb-2 pr-4">Avg P&L</th>
                  <th className="pb-2 pr-4">Avg Mins</th>
                  <th className="pb-2 pr-4">Avg ADX</th>
                  <th className="pb-2 pr-4">Best</th>
                  <th className="pb-2">Worst</th>
                </tr>
              </thead>
              <tbody>
                {winRates.map((r, i) => (
                  <tr key={i} className="border-b border-terminal-border/40 hover:bg-terminal-card/50">
                    <td className="py-1.5 pr-4 text-white">{r.session}</td>
                    <td className="py-1.5 pr-4 text-blue-400">{r.instrument}</td>
                    <td className="py-1.5 pr-4 text-gray-300">{r.trades}</td>
                    <td className="py-1.5 pr-4">
                      <span className={r.win_pct >= 55 ? 'text-green-400 font-bold' : r.win_pct >= 45 ? 'text-yellow-400' : 'text-red-400'}>
                        {r.win_pct}%
                      </span>
                    </td>
                    <td className="py-1.5 pr-4"><Badge value={r.avg_pnl} positive /></td>
                    <td className="py-1.5 pr-4 text-gray-400">{r.avg_mins}m</td>
                    <td className="py-1.5 pr-4 text-gray-400">{r.avg_adx}</td>
                    <td className="py-1.5 pr-4 text-green-400">${r.best_trade?.toFixed(0)}</td>
                    <td className="py-1.5 text-red-400">${r.worst_trade?.toFixed(0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* ── Score Band Performance ── */}
      <section>
        <h2 className="text-sm font-semibold text-gray-300 mb-2 uppercase tracking-wide">Win Rate by Score Band</h2>
        {scoreBands.length === 0
          ? <p className="text-gray-500 text-sm">No data yet.</p>
          : (
          <div className="flex flex-wrap gap-3">
            {scoreBands.map((b, i) => (
              <div key={i} className="bg-terminal-card border border-terminal-border rounded p-3 min-w-[110px]">
                <div className="text-xs text-gray-400">{b.score_floor}–{b.score_ceil}</div>
                <div className={`text-lg font-bold ${b.win_pct >= 55 ? 'text-green-400' : b.win_pct >= 45 ? 'text-yellow-400' : 'text-red-400'}`}>
                  {b.win_pct}%
                </div>
                <div className="text-xs text-gray-500">{b.trades} trades</div>
                <div className={`text-xs font-mono ${b.avg_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                  avg ${b.avg_pnl?.toFixed(0)}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* ── Ghost Trades — Missed Setup Outcomes ── */}
      <section>
        <h2 className="text-sm font-semibold text-gray-300 mb-1 uppercase tracking-wide">Missed Setups — Would Have Happened</h2>
        <p className="text-xs text-gray-500 mb-2">Setups the bot skipped. Ghost trades track what would have happened over 90 minutes.</p>
        {ghostTrades.length === 0
          ? <p className="text-gray-500 text-sm">No resolved ghost trades yet — they populate 90 minutes after each skipped setup.</p>
          : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead>
                <tr className="text-gray-400 border-b border-terminal-border">
                  <th className="pb-2 pr-4">Session</th>
                  <th className="pb-2 pr-4">Instrument</th>
                  <th className="pb-2 pr-4">Skip Reason</th>
                  <th className="pb-2 pr-4">Skipped</th>
                  <th className="pb-2 pr-4">Would Win</th>
                  <th className="pb-2 pr-4">Ghost Win%</th>
                  <th className="pb-2">Avg Ghost P&L</th>
                </tr>
              </thead>
              <tbody>
                {ghostTrades.map((r, i) => (
                  <tr key={i} className="border-b border-terminal-border/40 hover:bg-terminal-card/50">
                    <td className="py-1.5 pr-4 text-white">{r.session}</td>
                    <td className="py-1.5 pr-4 text-blue-400">{r.instrument}</td>
                    <td className="py-1.5 pr-4 text-yellow-400">{r.skip_reason}</td>
                    <td className="py-1.5 pr-4 text-gray-300">{r.skipped}</td>
                    <td className="py-1.5 pr-4 text-green-400">{r.would_win}</td>
                    <td className="py-1.5 pr-4">
                      <span className={r.ghost_win_pct >= 55 ? 'text-green-400 font-bold' : r.ghost_win_pct >= 45 ? 'text-yellow-400' : 'text-red-400'}>
                        {r.ghost_win_pct ?? '—'}%
                      </span>
                    </td>
                    <td className="py-1.5"><Badge value={r.avg_ghost_pnl} positive /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* ── Threshold Suggestions ── */}
      <section>
        <h2 className="text-sm font-semibold text-gray-300 mb-2 uppercase tracking-wide">Threshold Suggestions</h2>
        {suggestions.length === 0
          ? <p className="text-gray-500 text-sm">Need 10+ trades per session for suggestions.</p>
          : (
          <div className="flex flex-wrap gap-3">
            {suggestions.map((s, i) => (
              <div key={i} className="bg-terminal-card border border-terminal-border rounded p-3 min-w-[180px]">
                <div className="text-sm font-semibold text-white">{s.session} — {s.instrument}</div>
                {s.suggested_min_score
                  ? <>
                      <div className="text-xs text-gray-400 mt-1">{s.sample_trades} trades · current WR {s.current_win_pct}%</div>
                      <div className="text-xs mt-1">
                        Raise min score to <span className="text-yellow-400 font-bold">{s.suggested_min_score}</span>
                        {' '}→ projected <span className="text-green-400 font-bold">{s.projected_win_pct}%</span> WR
                      </div>
                    </>
                  : <div className="text-xs text-gray-500 mt-1">{s.note}</div>
                }
              </div>
            ))}
          </div>
        )}
      </section>

      {/* ── P&L Heatmap ── */}
      <section>
        <h2 className="text-sm font-semibold text-gray-300 mb-2 uppercase tracking-wide">P&L Heatmap — Hour × Day</h2>
        {heatmap.length === 0
          ? <p className="text-gray-500 text-sm">No data yet.</p>
          : (
          <div className="overflow-x-auto">
            <table className="text-xs border-collapse">
              <thead>
                <tr>
                  <th className="pr-2 text-gray-500 font-normal text-right">Hour ET</th>
                  {DOW.map(d => <th key={d} className="px-2 pb-1 text-gray-400 font-normal">{d}</th>)}
                </tr>
              </thead>
              <tbody>
                {Array.from({length: 24}, (_, h) => (
                  <tr key={h}>
                    <td className="pr-2 text-gray-500 text-right">{h.toString().padStart(2,'0')}:00</td>
                    {[0,1,2,3,4,5,6].map(dow => {
                      const cell = heatGrid[dow]?.[h]
                      if (!cell) return <td key={dow} className="px-2 py-0.5 w-12 h-6 bg-gray-900/30 rounded-sm" />
                      const intensity = Math.min(Math.abs(cell.total_pnl) / maxAbs, 1)
                      const bg = cell.total_pnl > 0
                        ? `rgba(16,185,129,${0.15 + intensity * 0.7})`
                        : `rgba(239,68,68,${0.15 + intensity * 0.7})`
                      return (
                        <td key={dow} className="px-2 py-0.5 w-12 h-6 rounded-sm text-center cursor-default"
                            style={{ background: bg }}
                            title={`${DOW[dow]} ${h}:00 | ${cell.trades} trades | WR ${cell.win_pct}% | P&L $${cell.total_pnl}`}>
                          <span className="text-white/80">{cell.trades}</span>
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="text-xs text-gray-500 mt-1">Cell = trade count. Green = net profit, Red = net loss. Intensity = magnitude.</p>
          </div>
        )}
      </section>
    </div>
  )
}
