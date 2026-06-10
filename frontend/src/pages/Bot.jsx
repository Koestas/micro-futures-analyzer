import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

function cn(...c) { return c.filter(Boolean).join(' ') }

const SESSIONS = [
  { name: 'Asia',    time: '9 PM – 1 AM ET',    symbol: 'MGC',       color: 'text-yellow-400' },
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
  const [switchMsg, setSwitchMsg] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['bot-status'],
    queryFn: () => fetch('/api/bot/status').then(r => r.json()),
    refetchInterval: 5000,
  })

  const pxStatus = useQuery({
    queryKey: ['px-status'],
    queryFn: () => fetch('/api/projectx/status').then(r => r.json()),
    refetchInterval: 10000,
  })

  const startMut = useMutation({ mutationFn: () => fetch('/api/bot/start',     { method: 'POST' }).then(r => r.json()), onSuccess: () => qc.invalidateQueries(['bot-status']) })
  const stopMut  = useMutation({ mutationFn: () => fetch('/api/bot/stop',      { method: 'POST' }).then(r => r.json()), onSuccess: () => qc.invalidateQueries(['bot-status']) })
  const closeAll = useMutation({ mutationFn: () => fetch('/api/bot/close-all', { method: 'POST' }).then(r => r.json()), onSuccess: () => qc.invalidateQueries(['bot-status']) })

  const { data: thinking } = useQuery({
    queryKey: ['bot-thinking'],
    queryFn: () => fetch('/api/bot/thinking').then(r => r.json()),
    refetchInterval: 15_000,
  })

  const switchAccount = async (accountId) => {
    const r = await fetch(`/api/bot/switch-account?account_id=${accountId}`, { method: 'POST' }).then(x => x.json())
    setSwitchMsg(r.success ? `✓ Switched to ${r.name} ($${r.balance?.toLocaleString()})` : `✗ ${r.error}`)
    qc.invalidateQueries(['bot-status'])
    qc.invalidateQueries(['px-status'])
  }
  const forceMut = useMutation({
    mutationFn: () => fetch(
      `/api/bot/force-trade?symbol=${forceSymbol}&side=${forceSide}&size=${forceSize}&stop_ticks=${forceStop}&tp_ticks=${forceTp}`,
      { method: 'POST' }
    ).then(r => r.json()),
    onSuccess: () => qc.invalidateQueries(['bot-status']),
  })

  const running      = data?.running
  const pnl          = data?.daily_pnl ?? 0
  const session      = data?.current_session ?? '—'
  const lastCheck    = data?.last_check ?? '—'
  const trades       = data?.trades_today ?? 0
  const positions    = data?.positions ?? []
  const orders       = data?.open_orders ?? []
  const quotes       = data?.quotes ?? {}
  const botLog       = data?.bot_log ?? []
  const tradeLog     = data?.trade_log ?? []
  const lastSig      = data?.last_signal ?? {}
  const dailyFloor   = data?.daily_floor ?? -1000
  const sizeFactor   = data?.daily_size_factor ?? 1.0
  const dailyMaxProfit = data?.daily_max_profit ?? 1500
  const dailyMaxLoss   = data?.daily_max_loss ?? 1000

  const px = pxStatus.data
  const accounts = px?.accounts ?? []
  const practiceAcct = accounts.find(a => a.name?.startsWith('PRAC'))
  const pnlColor = pnl > 0 ? 'text-green-400' : pnl < 0 ? 'text-red-400' : 'text-gray-400'

  // Account-derived session P&L (balance now minus balance at bot start) — ground truth
  const startBal  = data?.session_start_balance ?? 0
  const acctPnl   = startBal > 0 && practiceAcct ? practiceAcct.balance - startBal : null
  const acctColor = acctPnl === null ? 'text-gray-400' : acctPnl > 0 ? 'text-green-400' : acctPnl < 0 ? 'text-red-400' : 'text-gray-400'

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
          <a href="/scalp-backtest" className="px-3 py-2 bg-terminal-card border border-terminal-border text-gray-400 hover:text-white text-sm rounded">
            Backtest Results
          </a>
        </div>
      </div>

      {/* ── Status bar ── */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <Stat label="Bot Status"    value={running ? '● LIVE' : '○ Stopped'} color={running ? 'text-green-400' : 'text-gray-500'} />
        <Stat label="Session"       value={session} />
        <Stat label="Bot P&L"       value={`$${pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}`} color={pnlColor} />
        <Stat label="Account P&L"   value={acctPnl !== null ? `$${acctPnl >= 0 ? '+' : ''}${acctPnl.toFixed(2)}` : '—'} color={acctColor} />
        <Stat label="ICT Trades"    value={trades} />
        <Stat label="Scalps Today"  value={data?.scalp_today ?? 0} />
        <Stat label="Profit Floor"  value={dailyFloor > 0 ? `$${dailyFloor}` : 'None'} color={dailyFloor > 0 ? 'text-yellow-400' : 'text-gray-400'} small />
        <Stat label="Size Factor"   value={`${Math.round(sizeFactor * 100)}%`} color={sizeFactor < 1 ? 'text-yellow-400' : 'text-green-400'} small />
        <Stat label="Max Profit"    value={`$${dailyMaxProfit}`} small />
        <Stat label="Max Loss"      value={`$${dailyMaxLoss}`} small />
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

      {/* ── What's the bot thinking ── */}
      {thinking && (
        <div className="bg-terminal-card border border-terminal-border rounded p-3">
          <div className="text-xs text-gray-400 font-semibold uppercase mb-3">
            What's the Bot Thinking — {thinking.session}
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {['MNQ','MES','MGC'].map(sym => {
              const t = thinking.instruments?.[sym]
              if (!t || t.status === 'no_data') return (
                <div key={sym} className="border border-gray-800 rounded p-2 text-xs text-gray-600">{sym}: no data</div>
              )
              return (
                <div key={sym} className={cn('border rounded p-2 text-xs', t.ready ? 'border-green-700 bg-green-950/20' : 'border-terminal-border')}>
                  <div className="flex justify-between items-center mb-1">
                    <span className="font-bold text-white">{sym}</span>
                    <span className="font-mono text-gray-300">${t.price?.toFixed(sym==='MGC'?1:0)}</span>
                    {t.bid && <span className="text-gray-500">{t.bid?.toFixed(2)}/{t.ask?.toFixed(2)}</span>}
                  </div>
                  <div className="flex justify-between mb-1">
                    <span className="text-gray-400">Score</span>
                    <span className={cn('font-bold', t.best_score >= t.min_score ? 'text-green-400' : 'text-yellow-400')}>
                      {t.best_score}/{t.min_score}
                      {t.score_gap > 0 && <span className="text-gray-500 text-xs ml-1">(-{t.score_gap})</span>}
                    </span>
                  </div>
                  <div className="flex justify-between mb-1">
                    <span className="text-gray-400">Direction</span>
                    <span className={t.direction === 'bullish' ? 'text-green-400' : 'text-red-400'}>{t.direction}</span>
                  </div>
                  <div className="flex justify-between mb-1">
                    <span className="text-gray-400">ADX / RSI</span>
                    <span className="text-white">{t.adx} / {t.rsi}</span>
                  </div>
                  {t.vwap && (
                    <div className="flex justify-between mb-1">
                      <span className="text-gray-400">VWAP</span>
                      <span className="text-white">{t.vwap}</span>
                    </div>
                  )}
                  <div className="mt-1 pt-1 border-t border-terminal-border">
                    {t.ready
                      ? <span className="text-green-400 font-bold">✓ SETUP READY</span>
                      : t.blockers?.length > 0
                        ? <span className="text-yellow-600">{t.blockers[0]}</span>
                        : <span className="text-gray-600">{t.status}</span>
                    }
                    {t.scalp_ready && <span className="text-yellow-400 ml-2">⚡ scalp signal</span>}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* ── Account switch ── */}
      {pxStatus.data?.accounts?.length > 1 && (
        <div className="bg-terminal-card border border-blue-900 rounded p-3">
          <div className="text-xs text-blue-400 font-semibold uppercase mb-2">Active Trading Account</div>
          <div className="flex flex-wrap gap-2 items-center">
            {pxStatus.data.accounts.filter(a => a.canTrade).map(a => (
              <button key={a.id}
                onClick={() => switchAccount(a.id)}
                className={cn(
                  'px-3 py-1.5 rounded text-xs font-semibold border transition-colors',
                  a.id === pxStatus.data.account_id
                    ? 'bg-blue-900 border-blue-600 text-blue-300'
                    : 'bg-terminal-bg border-terminal-border text-gray-400 hover:border-blue-700'
                )}
              >
                {a.name.startsWith('PRAC') ? '🧪 ' : '💰 '}
                {a.name.split('-')[0]} ${a.balance.toLocaleString()}
                {a.id === pxStatus.data.account_id && ' ← active'}
              </button>
            ))}
          </div>
          {switchMsg && <div className={cn('text-xs mt-2', switchMsg.startsWith('✓') ? 'text-green-400' : 'text-red-400')}>{switchMsg}</div>}
          <p className="text-xs text-gray-600 mt-2">Switching while bot is running redirects all new trades to the selected account.</p>
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
