import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '../lib/api'
import { CheckCircle, XCircle, AlertTriangle, RefreshCw, Wifi, WifiOff } from 'lucide-react'
import { clsx } from 'clsx'

function Badge({ ok, warn, label }) {
  return (
    <span className={clsx('text-xs font-semibold px-2 py-0.5 rounded',
      ok   ? 'bg-green-900 text-green-400' :
      warn ? 'bg-yellow-900 text-yellow-400' :
             'bg-red-900 text-red-400'
    )}>{label}</span>
  )
}

function Row({ label, value, ok, warn, mono }) {
  return (
    <div className="flex justify-between items-center py-1 border-b border-terminal-border last:border-0 text-sm">
      <span className="text-gray-400">{label}</span>
      <span className={clsx(mono && 'font-mono', ok ? 'text-green-400' : warn ? 'text-yellow-400' : 'text-gray-200')}>
        {value}
      </span>
    </div>
  )
}

function Card({ title, children, accent }) {
  return (
    <div className={clsx('bg-terminal-card border rounded p-4',
      accent === 'green'  ? 'border-green-800'  :
      accent === 'yellow' ? 'border-yellow-800' :
      accent === 'red'    ? 'border-red-800'    :
                            'border-terminal-border'
    )}>
      <div className="text-xs text-gray-400 font-semibold uppercase mb-3">{title}</div>
      {children}
    </div>
  )
}

export default function Diagnostics() {
  const { data: providers, refetch: refetchProviders } = useQuery({
    queryKey: ['providers'],
    queryFn: () => apiFetch('/api/providers/status'),
    refetchInterval: 30_000,
  })

  const { data: px, refetch: refetchPx } = useQuery({
    queryKey: ['px-diag'],
    queryFn: () => fetch('/api/projectx/status').then(r => r.json()),
    refetchInterval: 15_000,
  })

  const { data: bot } = useQuery({
    queryKey: ['bot-diag'],
    queryFn: () => fetch('/api/bot/status').then(r => r.json()),
    refetchInterval: 10_000,
  })

  const { data: quotes } = useQuery({
    queryKey: ['px-quotes-diag'],
    queryFn: () => fetch('/api/projectx/quotes').then(r => r.json()),
    refetchInterval: 5_000,
  })

  const p = providers?.providers || {}
  const pxAcct = px?.accounts?.find(a => a.name?.startsWith('PRAC')) || px?.accounts?.[0]

  return (
    <div className="space-y-4 max-w-5xl">

      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold text-white">System Diagnostics</h1>
        <button onClick={() => { refetchProviders(); refetchPx() }}
          className="flex items-center gap-1 text-xs text-blue-400 hover:underline">
          <RefreshCw size={11} /> Refresh
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">

        {/* ProjectX / TopstepX */}
        <Card title="ProjectX — TopstepX" accent={px?.connected ? 'green' : 'red'}>
          <Row label="Connection"  value={px?.connected ? '● Connected' : '○ Disconnected'} ok={px?.connected} />
          <Row label="WebSocket"   value={px?.ws_live   ? '● Live feed'  : '○ REST fallback'} ok={px?.ws_live} warn={!px?.ws_live && px?.connected} />
          <Row label="Account"     value={pxAcct?.name || '—'} mono />
          <Row label="Balance"     value={pxAcct ? `$${pxAcct.balance.toLocaleString()}` : '—'} ok={!!pxAcct} />
          <Row label="Can Trade"   value={pxAcct?.canTrade ? 'Yes' : 'No'} ok={pxAcct?.canTrade} />
          <Row label="Token exp."  value={px?.token_expires ? new Date(px.token_expires).toLocaleTimeString() : '—'} />
          <Row label="Account ID"  value={px?.account_id || '—'} mono />
        </Card>

        {/* Live quotes */}
        <Card title="Live Quotes" accent={quotes?.quotes?.MNQ ? 'green' : 'yellow'}>
          {['MNQ', 'MES', 'MGC'].map(sym => {
            const q = quotes?.quotes?.[sym]
            return (
              <div key={sym} className="flex justify-between items-center py-1.5 border-b border-terminal-border last:border-0 text-sm">
                <span className="text-white font-bold w-12">{sym}</span>
                <span className="font-mono text-white">{q?.lastPrice?.toFixed(2) ?? '—'}</span>
                <span className={clsx('text-xs', !q ? 'text-gray-600' : q.source === 'websocket' ? 'text-green-400' : 'text-yellow-400')}>
                  {q ? (q.source === 'websocket' ? '● WS' : '○ REST') : 'no data'}
                </span>
              </div>
            )
          })}
          <div className="text-xs text-gray-600 mt-2">
            Source: TopstepX practice account — real market prices
          </div>
        </Card>

        {/* Auto-bot */}
        <Card title="Auto-Trader Bot" accent={bot?.running ? 'green' : 'yellow'}>
          <Row label="Status"    value={bot?.running ? '● Running' : '○ Stopped'} ok={bot?.running} />
          <Row label="Session"   value={bot?.current_session || '—'} ok={!!bot?.current_session && bot?.current_session !== 'Off'} />
          <Row label="Today P&L" value={bot?.daily_pnl != null ? `$${bot.daily_pnl >= 0 ? '+' : ''}${bot.daily_pnl.toFixed(2)}` : '—'}
            ok={(bot?.daily_pnl ?? 0) > 0} warn={(bot?.daily_pnl ?? 0) === 0} />
          <Row label="Trades"    value={bot?.trades_today ?? 0} />
          <Row label="Positions" value={bot?.positions?.length ?? 0} warn={(bot?.positions?.length ?? 0) > 0} />
          <Row label="Last check" value={bot?.last_check || '—'} />
        </Card>

        {/* Yahoo Finance (fallback) */}
        <Card title="Yahoo Finance (fallback)" accent={p.yahoo?.status === 'ok' ? 'green' : 'yellow'}>
          <Row label="Status"   value={p.yahoo?.status || '—'} ok={p.yahoo?.status === 'ok'} />
          <Row label="Role"     value="Options flow · news · equity data" />
          <Row label="Delay"    value="~15 min (free tier)" warn />
          <Row label="Used for" value="WAVE, GEX, chain, leadership" />
          <div className="text-xs text-gray-600 mt-2">
            Futures data now served by ProjectX (real-time).
          </div>
        </Card>

        {/* Database */}
        <Card title="SQLite Database" accent={p.sqlite?.status === 'ok' ? 'green' : 'red'}>
          <Row label="Status"  value={p.sqlite?.status || '—'} ok={p.sqlite?.status === 'ok'} />
          <Row label="Path"    value={p.sqlite?.path || '—'} mono />
          <Row label="Size"    value={p.sqlite?.size_bytes ? `${(p.sqlite.size_bytes / 1024).toFixed(1)} KB` : '—'} />
        </Card>

        {/* Schwab (optional) */}
        <Card title="Schwab API (optional)" accent={p.schwab?.status === 'ok' ? 'green' : 'yellow'}>
          <Row label="Status"  value={p.schwab?.status || 'not_configured'} ok={p.schwab?.status === 'ok'} warn={p.schwab?.status !== 'ok'} />
          <Row label="Role"    value="Live equity quotes (optional)" />
          <div className="text-xs text-gray-600 mt-2">
            Not needed — ProjectX covers futures data. Set up in .env if you want live equity quotes.
          </div>
        </Card>

      </div>

      {/* All accounts */}
      {px?.accounts?.length > 0 && (
        <Card title="All TopstepX Accounts">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-gray-500 border-b border-terminal-border">
                  <th className="text-left py-1">Account</th>
                  <th className="text-right py-1">Balance</th>
                  <th className="text-center py-1">Can Trade</th>
                  <th className="text-center py-1">Simulated</th>
                  <th className="text-center py-1">Active Bot</th>
                </tr>
              </thead>
              <tbody>
                {px.accounts.map(a => (
                  <tr key={a.id} className={clsx('border-b border-terminal-border last:border-0',
                    a.id === px.account_id ? 'bg-green-950' : ''
                  )}>
                    <td className="py-1.5 font-mono text-xs text-gray-300">{a.name}</td>
                    <td className="text-right text-green-400 font-bold">${a.balance.toLocaleString()}</td>
                    <td className="text-center">{a.canTrade ? <span className="text-green-400">✓</span> : <span className="text-gray-600">—</span>}</td>
                    <td className="text-center text-gray-400">{a.simulated ? 'Yes' : 'No'}</td>
                    <td className="text-center">{a.id === px.account_id ? <span className="text-green-400 text-xs">● active</span> : ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Session schedule */}
      <Card title="Trading Session Schedule">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
          {[
            { name: 'Asia',   time: '9 PM – 1 AM ET',    inst: 'MGC',       score: '≥58', contracts: '5', color: 'text-yellow-400' },
            { name: 'London', time: '3 AM – 5 AM ET',    inst: 'MNQ / MES', score: '≥62', contracts: '5', color: 'text-blue-400'   },
            { name: 'NY AM',  time: '9:30 – 11:30 AM ET',inst: 'MNQ / MES', score: '≥65', contracts: '5', color: 'text-green-400'  },
            { name: 'NY PM',  time: '1:30 – 3:30 PM ET', inst: 'MNQ',       score: '≥68', contracts: '4', color: 'text-purple-400' },
          ].map(s => (
            <div key={s.name} className="border border-terminal-border rounded p-2">
              <div className={clsx('font-bold', s.color)}>{s.name}</div>
              <div className="text-xs text-gray-400 mt-1">{s.time}</div>
              <div className="text-xs text-white mt-1">{s.inst}</div>
              <div className="text-xs text-gray-400">{s.contracts} contracts · score {s.score}</div>
            </div>
          ))}
        </div>
        <div className="text-xs text-gray-600 mt-3">
          Market closed 4–6 PM ET daily (CME). Max 2 trades/session · 6/day · $3K daily loss limit.
        </div>
      </Card>

    </div>
  )
}
