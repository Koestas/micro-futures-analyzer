import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

const API = 'http://localhost:8000'

function cn(...c) { return c.filter(Boolean).join(' ') }

const SESSIONS = [
  { name: 'Asia',    time: '9 PM – 1 AM ET',   symbol: 'MGC',       color: 'text-yellow-400' },
  { name: 'London',  time: '3 AM – 5 AM ET',    symbol: 'MNQ / MES', color: 'text-blue-400'   },
  { name: 'NY AM',   time: '9:30 – 11:30 AM ET',symbol: 'MNQ / MES', color: 'text-green-400'  },
  { name: 'NY PM',   time: '1:30 – 3:30 PM ET', symbol: 'MNQ',       color: 'text-purple-400' },
]

export default function Bot() {
  const qc = useQueryClient()
  const [forceSymbol, setForceSymbol] = useState('MNQ')
  const [forceSide, setForceSide] = useState(0)
  const [forceSize, setForceSize] = useState(1)
  const [forceStop, setForceStop] = useState(40)
  const [forceTp, setForceTp] = useState(80)

  const { data, isLoading } = useQuery({
    queryKey: ['bot-status'],
    queryFn: () => fetch(`${API}/api/bot/status`).then(r => r.json()),
    refetchInterval: 5000,
  })

  const pxStatus = useQuery({
    queryKey: ['px-status'],
    queryFn: () => fetch(`${API}/api/projectx/status`).then(r => r.json()),
    refetchInterval: 10000,
  })

  const startMut  = useMutation({ mutationFn: () => fetch(`${API}/api/bot/start`,    { method: 'POST' }).then(r => r.json()), onSuccess: () => qc.invalidateQueries(['bot-status']) })
  const stopMut   = useMutation({ mutationFn: () => fetch(`${API}/api/bot/stop`,     { method: 'POST' }).then(r => r.json()), onSuccess: () => qc.invalidateQueries(['bot-status']) })
  const closeAll  = useMutation({ mutationFn: () => fetch(`${API}/api/bot/close-all`,{ method: 'POST' }).then(r => r.json()), onSuccess: () => qc.invalidateQueries(['bot-status']) })
  const forceMut  = useMutation({
    mutationFn: () => fetch(
      `${API}/api/bot/force-trade?symbol=${forceSymbol}&side=${forceSide}&size=${forceSize}&stop_ticks=${forceStop}&tp_ticks=${forceTp}`,
      { method: 'POST' }
    ).then(r => r.json()),
    onSuccess: () => qc.invalidateQueries(['bot-status']),
  })

  const running   = data?.running
  const pnl       = data?.daily_pnl ?? 0
  const session   = data?.current_session ?? '—'
  const lastCheck = data?.last_check ?? '—'
  const trades    = data?.trades_today ?? 0
  const positions = data?.positions ?? []
  const orders    = data?.open_orders ?? []
  const quotes    = data?.quotes ?? {}
  const botLog    = data?.bot_log ?? []
  const tradeLog  = data?.trade_log ?? []
  const lastSig   = data?.last_signal ?? {}

  const px = pxStatus.data
  const accounts = px?.accounts ?? []
  const practiceAcct = accounts.find(a => a.name?.startsWith('PRAC'))
  const pnlColor = pnl > 0 ? 'text-green-400' : pnl < 0 ? 'text-red-400' : 'text-gray-400'

  return (
    <div className="p-4 space-y-4 max-w-7xl mx-auto">

      {/* ── Header ── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white">Live Bot — ICT Auto-Trader</h1>
          <p className="text-xs text-gray-400 mt-0.5">
            TopstepX practice account · Real market data · Real order execution
          </p>
        </div>
        <div className="flex gap-2">
          {running
            ? <button onClick={() => stopMut.mutate()} className="px-4 py-2 bg-red-600 hover:bg-red-500 text-white text-sm rounded font-semibold">
                ■ Stop Bot
              </button>
            : <button onClick={() => startMut.mutate()} className="px-4 py-2 bg-green-600 hover:bg-green-500 text-white text-sm rounded font-semibold">
                ▶ Start Bot
              </button>
          }
          <button onClick={() => closeAll.mutate()} className="px-3 py-2 bg-orange-700 hover:bg-orange-600 text-white text-sm rounded">
            Close All
          </button>
        </div>
      </div>

      {/* ── Status bar ── */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <Stat label="Bot Status"    value={running ? '● LIVE' : '○ Stopped'} color={running ? 'text-green-400' : 'text-gray-500'} />
        <Stat label="Session"       value={session} />
        <Stat label="Today P&L"     value={`$${pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}`} color={pnlColor} />
        <Stat label="Trades Today"  value={trades} />
        <Stat label="Last Check"    value={lastCheck} small />
      </div>

      {/* ── Account overview ── */}
      {practiceAcct && (
        <div className="bg-terminal-card border border-terminal-border rounded p-3 flex gap-6 text-sm">
          <div><span className="text-gray-400">Account</span> <span className="text-white font-mono ml-2">{practiceAcct.name}</span></div>
          <div><span className="text-gray-400">Balance</span> <span className="text-green-400 font-bold ml-2">${practiceAcct.balance.toLocaleString()}</span></div>
          <div><span className="text-gray-400">Can Trade</span> <span className={cn('ml-2 font-bold', practiceAcct.canTrade ? 'text-green-400' : 'text-red-400')}>{practiceAcct.canTrade ? 'Yes' : 'No'}</span></div>
          <div><span className="text-gray-400">WS</span> <span className={cn('ml-2', px?.ws_live ? 'text-green-400' : 'text-red-400')}>{px?.ws_live ? '● Live' : '○ REST'}</span></div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">

        {/* ── Live quotes ── */}
        <div className="bg-terminal-card border border-terminal-border rounded p-3">
          <div className="text-xs text-gray-400 font-semibold uppercase mb-2">Live Quotes</div>
          {['MNQ', 'MES', 'MGC'].map(sym => {
            const q = quotes[sym]
            if (!q) return <div key={sym} className="text-gray-600 text-xs py-1">{sym}: waiting…</div>
            const chg = q.changePct ?? 0
            return (
              <div key={sym} className="flex justify-between items-center py-1.5 border-b border-terminal-border last:border-0">
                <span className="text-white font-bold text-sm">{sym}</span>
                <span className="text-white font-mono">{q.lastPrice?.toFixed(2)}</span>
                <span className={cn('text-xs', chg >= 0 ? 'text-green-400' : 'text-red-400')}>
                  {chg >= 0 ? '+' : ''}{chg?.toFixed(2)}%
                </span>
                <span className="text-gray-500 text-xs">{q.source === 'websocket' ? '● WS' : 'REST'}</span>
              </div>
            )
          })}
        </div>

        {/* ── Last signal ── */}
        <div className="bg-terminal-card border border-terminal-border rounded p-3">
          <div className="text-xs text-gray-400 font-semibold uppercase mb-2">Last Signal Evaluated</div>
          {lastSig?.instrument ? (
            <div className="space-y-1 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-400">Instrument</span>
                <span className="text-white font-bold">{lastSig.instrument}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-400">Direction</span>
                <span className={cn('font-bold', lastSig.direction === 'bullish' ? 'text-green-400' : 'text-red-400')}>
                  {lastSig.direction?.toUpperCase()}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-400">Score</span>
                <span className="text-yellow-400 font-bold">{lastSig.score}/100</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-400">ADX / RSI</span>
                <span className="text-white">{lastSig.adx} / {lastSig.rsi}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-400">Contracts</span>
                <span className="text-white">{lastSig.contracts}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-400">Risk</span>
                <span className="text-red-400">${lastSig.usd_risk?.toFixed(0)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-400">HTF Bias</span>
                <span className="text-purple-400">{lastSig.htf_direction}</span>
              </div>
              <div className="text-gray-500 text-xs mt-1">{lastSig.timestamp?.slice(11, 19)} ET</div>
            </div>
          ) : (
            <div className="text-gray-500 text-sm italic">
              {lastSig?.result || 'No signal yet — start bot to scan'}
            </div>
          )}
        </div>

        {/* ── Sessions ── */}
        <div className="bg-terminal-card border border-terminal-border rounded p-3">
          <div className="text-xs text-gray-400 font-semibold uppercase mb-2">Session Schedule</div>
          <div className="space-y-2">
            {SESSIONS.map(s => (
              <div key={s.name} className={cn(
                'flex justify-between items-center text-sm p-1.5 rounded',
                session === s.name ? 'bg-terminal-border' : ''
              )}>
                <div>
                  <span className={cn('font-bold', s.color)}>{s.name}</span>
                  <span className="text-gray-500 ml-2 text-xs">{s.symbol}</span>
                </div>
                <span className="text-gray-400 text-xs">{s.time}</span>
                {session === s.name && <span className="text-green-400 text-xs ml-1">●</span>}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── Open positions ── */}
      {positions.length > 0 && (
        <div className="bg-terminal-card border border-yellow-600 rounded p-3">
          <div className="text-xs text-yellow-400 font-semibold uppercase mb-2">Open Positions</div>
          <div className="space-y-1">
            {positions.map((p, i) => (
              <div key={i} className="flex gap-4 text-sm">
                <span className="text-white font-bold">{p.symbol || p.contractId}</span>
                <span className={cn(p.type === 1 ? 'text-green-400' : 'text-red-400')}>
                  {p.type === 1 ? 'LONG' : 'SHORT'} x{p.size}
                </span>
                <span className="text-gray-400">avg @ {p.averagePrice}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">

        {/* ── Trade log ── */}
        <div className="bg-terminal-card border border-terminal-border rounded p-3">
          <div className="text-xs text-gray-400 font-semibold uppercase mb-2">Trade Log</div>
          {tradeLog.length === 0
            ? <p className="text-gray-600 text-xs italic">No trades yet this session.</p>
            : <div className="space-y-1">
                {[...tradeLog].reverse().map((t, i) => (
                  <div key={i} className="flex gap-3 text-xs py-1 border-b border-terminal-border last:border-0">
                    <span className="text-gray-500">{t.timestamp?.slice(11,16)}</span>
                    <span className="text-white font-bold">{t.instrument}</span>
                    <span className={cn(t.direction === 'bullish' ? 'text-green-400' : 'text-red-400', 'font-bold')}>
                      {t.direction === 'bullish' ? '▲ LONG' : '▼ SHORT'}
                    </span>
                    <span className="text-gray-300">x{t.contracts}</span>
                    <span className="text-yellow-400">score={t.score}</span>
                    <span className="text-gray-400">#{t.order_id}</span>
                  </div>
                ))}
              </div>
          }
        </div>

        {/* ── Bot log ── */}
        <div className="bg-terminal-card border border-terminal-border rounded p-3">
          <div className="text-xs text-gray-400 font-semibold uppercase mb-2">Bot Log</div>
          <div className="space-y-0.5 max-h-48 overflow-y-auto font-mono text-xs">
            {[...botLog].reverse().map((l, i) => (
              <div key={i} className={cn(
                l.level === 'error'   ? 'text-red-400'    :
                l.level === 'warning' ? 'text-yellow-400' : 'text-gray-400'
              )}>
                <span className="text-gray-600">{l.ts} </span>{l.msg}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── Manual override ── */}
      <div className="bg-terminal-card border border-orange-800 rounded p-3">
        <div className="text-xs text-orange-400 font-semibold uppercase mb-3">Manual Override — Force Order</div>
        <div className="flex flex-wrap gap-3 items-end">
          <div>
            <label className="text-xs text-gray-400 block mb-1">Symbol</label>
            <select value={forceSymbol} onChange={e => setForceSymbol(e.target.value)}
              className="bg-terminal-bg border border-terminal-border text-white text-sm rounded px-2 py-1">
              <option>MNQ</option><option>MES</option><option>MGC</option>
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-400 block mb-1">Side</label>
            <select value={forceSide} onChange={e => setForceSide(Number(e.target.value))}
              className="bg-terminal-bg border border-terminal-border text-white text-sm rounded px-2 py-1">
              <option value={0}>Buy (Long)</option>
              <option value={1}>Sell (Short)</option>
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-400 block mb-1">Size</label>
            <input type="number" min={1} max={10} value={forceSize} onChange={e => setForceSize(Number(e.target.value))}
              className="w-16 bg-terminal-bg border border-terminal-border text-white text-sm rounded px-2 py-1" />
          </div>
          <div>
            <label className="text-xs text-gray-400 block mb-1">SL Ticks</label>
            <input type="number" min={10} max={200} value={forceStop} onChange={e => setForceStop(Number(e.target.value))}
              className="w-20 bg-terminal-bg border border-terminal-border text-white text-sm rounded px-2 py-1" />
          </div>
          <div>
            <label className="text-xs text-gray-400 block mb-1">TP Ticks</label>
            <input type="number" min={10} max={400} value={forceTp} onChange={e => setForceTp(Number(e.target.value))}
              className="w-20 bg-terminal-bg border border-terminal-border text-white text-sm rounded px-2 py-1" />
          </div>
          <button onClick={() => forceMut.mutate()}
            className="px-4 py-1.5 bg-orange-700 hover:bg-orange-600 text-white text-sm rounded font-semibold">
            Fire Order
          </button>
        </div>
        <p className="text-xs text-gray-600 mt-2">
          MNQ tick=0.25pt=$0.50 · MES tick=0.25pt=$1.25 · MGC tick=0.10pt=$1.00 ·
          40 ticks SL on MNQ = 10pts = $20/ct · 80 ticks TP = $40/ct
        </p>
      </div>

    </div>
  )
}

function Stat({ label, value, color, small }) {
  return (
    <div className="bg-terminal-card border border-terminal-border rounded p-3">
      <div className="text-xs text-gray-400">{label}</div>
      <div className={cn('font-bold mt-1', small ? 'text-xs' : 'text-lg', color || 'text-white')}>
        {value}
      </div>
    </div>
  )
}
