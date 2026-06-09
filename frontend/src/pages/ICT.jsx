import { useQuery } from '@tanstack/react-query'
import { apiFetch, fmt } from '../lib/api'
import { clsx } from 'clsx'
import {
  Clock, Target, TrendingUp, TrendingDown, Minus,
  AlertTriangle, CheckCircle, XCircle, Zap, BarChart2,
  RefreshCw, ChevronDown, ChevronUp, Activity, Layers,
  ArrowUpCircle, ArrowDownCircle, Radio, Ban, Crosshair,
  Calculator, ShieldAlert
} from 'lucide-react'
import { useState } from 'react'

// ---------------------------------------------------------------------------
// Small reusable components
// ---------------------------------------------------------------------------

function SessionBadge({ session, inKillzone, timeEt }) {
  return (
    <div className={clsx(
      'flex items-center gap-2 px-3 py-2 rounded border text-sm font-mono',
      inKillzone
        ? 'border-terminal-green/40 bg-terminal-green/10 text-terminal-green'
        : 'border-terminal-border bg-terminal-card text-terminal-muted'
    )}>
      <Clock size={14} />
      <span className="font-semibold">{timeEt}</span>
      <span className="text-terminal-muted">·</span>
      <span>{session}</span>
      {inKillzone && <span className="ml-auto badge badge-green animate-pulse text-xs">KILLZONE</span>}
    </div>
  )
}

function PhaseBadge({ phase, label, description, minutesSinceOpen }) {
  const colors = {
    accumulation:         'border-terminal-muted/40 bg-terminal-card text-terminal-muted',
    manipulation:         'border-terminal-yellow/40 bg-terminal-yellow/10 text-terminal-yellow',
    distribution_bullish: 'border-terminal-green/40 bg-terminal-green/10 text-terminal-green',
    distribution_bearish: 'border-terminal-red/40 bg-terminal-red/10 text-terminal-red',
    late_session:         'border-terminal-muted/30 bg-terminal-card text-terminal-muted',
    pre_market:           'border-terminal-blue/30 bg-terminal-blue/5 text-terminal-blue',
  }
  const icons = {
    accumulation: <Activity size={13}/>,
    manipulation: <AlertTriangle size={13}/>,
    distribution_bullish: <TrendingUp size={13}/>,
    distribution_bearish: <TrendingDown size={13}/>,
    late_session: <Clock size={13}/>,
    pre_market: <Clock size={13}/>,
  }
  return (
    <div className={clsx('flex flex-col px-3 py-2 rounded border text-sm', colors[phase] || colors.accumulation)}>
      <div className="flex items-center gap-2 font-semibold">
        {icons[phase] || <Activity size={13}/>}
        <span>PO3: {label}</span>
        {minutesSinceOpen != null && minutesSinceOpen >= 0 && (
          <span className="ml-auto text-xs opacity-70">{minutesSinceOpen}m in</span>
        )}
      </div>
      {description && <p className="text-xs opacity-80 mt-0.5 leading-relaxed">{description}</p>}
    </div>
  )
}

function ZonePill({ zone, pct }) {
  const isPremium = zone === 'premium', isDiscount = zone === 'discount'
  return (
    <div className={clsx('inline-flex items-center gap-1.5 px-2 py-1 rounded text-xs font-semibold',
      isPremium ? 'bg-terminal-red/20 text-terminal-red border border-terminal-red/30' :
      isDiscount ? 'bg-terminal-green/20 text-terminal-green border border-terminal-green/30' :
      'bg-terminal-border text-terminal-muted border border-terminal-border')}>
      {isPremium ? <TrendingDown size={11}/> : isDiscount ? <TrendingUp size={11}/> : <Minus size={11}/>}
      {zone === 'premium' ? 'PREMIUM' : zone === 'discount' ? 'DISCOUNT' : 'UNKNOWN'}
      {pct != null && <span className="opacity-70">({pct}%)</span>}
    </div>
  )
}

function DrawArrow({ direction, target, reason }) {
  if (!direction || direction === 'neutral')
    return <div className="text-terminal-muted text-xs italic">No clear draw — neutral</div>
  const up = direction === 'up'
  return (
    <div className={clsx('flex items-center gap-2 text-sm', up ? 'text-terminal-green' : 'text-terminal-red')}>
      {up ? <TrendingUp size={16}/> : <TrendingDown size={16}/>}
      <span className="font-mono font-semibold">{target ? fmt.price(target) : '—'}</span>
      <span className="text-terminal-muted text-xs truncate">{reason}</span>
    </div>
  )
}

function SetupGrade({ grade, score, checklist, title }) {
  const color = grade === 'A+' ? 'text-terminal-green' : grade === 'A' ? 'text-terminal-yellow'
    : grade === 'B' ? 'text-terminal-blue' : 'text-terminal-muted'
  const [open, setOpen] = useState(false)
  return (
    <div className="card border border-terminal-border/50">
      <div className="flex items-center justify-between cursor-pointer" onClick={() => setOpen(o => !o)}>
        <div className="flex items-center gap-2">
          <span className={clsx('text-2xl font-bold font-mono', color)}>{grade}</span>
          <div>
            <div className="text-terminal-text text-sm font-semibold">{title}</div>
            <div className="text-terminal-muted text-xs">{score}/100</div>
          </div>
        </div>
        {open ? <ChevronUp size={14} className="text-terminal-muted"/> : <ChevronDown size={14} className="text-terminal-muted"/>}
      </div>
      {open && (
        <div className="mt-3 space-y-1 border-t border-terminal-border pt-3">
          {checklist?.map((c, i) => (
            <div key={i} className="flex items-center gap-2 text-xs">
              {c.met ? <CheckCircle size={12} className="text-terminal-green shrink-0"/>
                     : <XCircle size={12} className="text-terminal-muted shrink-0"/>}
              <span className={c.met ? 'text-terminal-text' : 'text-terminal-muted'}>{c.item}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function FVGRow({ fvg }) {
  const isBull = fvg.base_type === 'bullish_fvg', isInverted = fvg.inverted
  return (
    <div className={clsx('flex items-center gap-2 text-xs py-1.5 px-2 rounded border',
      isInverted ? (isBull ? 'border-terminal-green/30 bg-terminal-green/5' : 'border-terminal-red/30 bg-terminal-red/5')
                 : 'border-terminal-border/30')}>
      <span className={clsx('font-semibold shrink-0',
        isInverted ? (isBull ? 'text-terminal-green' : 'text-terminal-red') : 'text-terminal-muted')}>
        {isInverted ? 'iFVG' : isBull ? 'FVG↑' : 'FVG↓'}
      </span>
      {fvg.displacement && <span title="Displacement candle">⚡</span>}
      <span className="font-mono text-terminal-text">{fmt.price(fvg.bottom)} – {fmt.price(fvg.top)}</span>
      <span className="text-terminal-muted ml-auto shrink-0">Δ{fvg.size?.toFixed(2)}</span>
      {fvg.filled && <span className="text-terminal-muted shrink-0">[filled]</span>}
    </div>
  )
}

function HTFBiasPanel({ htf, dayQ }) {
  if (!htf || !htf.bias) return null
  const bias = htf.bias
  const isBull = bias === 'bullish' || bias === 'bullish_lean'
  const isBear = bias === 'bearish' || bias === 'bearish_lean'
  const isStrong = htf.strength === 'strong_bullish' || htf.strength === 'strong_bearish'
  const color = isBull
    ? 'border-terminal-green/50 bg-terminal-green/10'
    : isBear
    ? 'border-terminal-red/50 bg-terminal-red/10'
    : 'border-terminal-border bg-terminal-card'
  const textColor = isBull ? 'text-terminal-green' : isBear ? 'text-terminal-red' : 'text-terminal-muted'
  const biasLabel = {
    bullish: 'BULLISH', bullish_lean: 'BULLISH LEAN',
    bearish: 'BEARISH', bearish_lean: 'BEARISH LEAN', neutral: 'NEUTRAL',
  }[bias] || bias.toUpperCase()

  const dayFactor = dayQ?.factor ?? 1
  const dayColor = dayFactor >= 1.0 ? 'text-terminal-green' : dayFactor >= 0.85 ? 'text-terminal-yellow' : 'text-terminal-red'

  return (
    <div className={clsx('rounded border px-4 py-3 space-y-2', color)}>
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-3">
          {isBull ? <TrendingUp size={16} className="text-terminal-green"/> : isBear ? <TrendingDown size={16} className="text-terminal-red"/> : <Minus size={16} className="text-terminal-muted"/>}
          <div>
            <div className={clsx('font-bold text-sm', textColor)}>
              HTF Daily: {biasLabel} {isStrong && <span className="text-xs font-normal opacity-80">— STRONG</span>}
            </div>
            <div className="text-xs text-terminal-muted">{htf.structure}</div>
          </div>
        </div>
        <div className="flex items-center gap-3 text-xs">
          <div className="text-terminal-muted">
            EMA20: <span className={htf.above_ema20 ? 'text-terminal-green font-mono' : 'text-terminal-red font-mono'}>{htf.ema20}</span>
            {' '}
            EMA50: <span className={htf.above_ema50 ? 'text-terminal-green font-mono' : 'text-terminal-red font-mono'}>{htf.ema50}</span>
          </div>
          {dayQ && (
            <div className={clsx('px-2 py-0.5 rounded border text-xs font-semibold', dayColor,
              dayFactor >= 1.0 ? 'border-terminal-green/40 bg-terminal-green/10' :
              dayFactor >= 0.85 ? 'border-terminal-yellow/40 bg-terminal-yellow/10' :
              'border-terminal-red/40 bg-terminal-red/10')}>
              {dayQ.day} ×{dayFactor}
            </div>
          )}
        </div>
      </div>
      {htf.note && <p className="text-xs text-terminal-muted leading-relaxed">{htf.note}</p>}
    </div>
  )
}

function CalendarWarning({ calData }) {
  if (!calData) return null
  const hasToday = calData.has_high_impact_today
  const hasTomorrow = calData.has_high_impact_tomorrow
  if (!hasToday && !hasTomorrow) return null
  return (
    <div className="space-y-1">
      {hasToday && (
        <div className="flex items-start gap-2 px-3 py-2 rounded border border-terminal-red/60 bg-terminal-red/10 text-xs">
          <AlertTriangle size={13} className="text-terminal-red shrink-0 mt-0.5"/>
          <div>
            <span className="font-bold text-terminal-red">HIGH IMPACT TODAY: </span>
            <span className="text-terminal-text">{calData.today?.map(e => e.title).join(' · ')}</span>
          </div>
        </div>
      )}
      {hasTomorrow && !hasToday && (
        <div className="flex items-start gap-2 px-3 py-2 rounded border border-terminal-yellow/40 bg-terminal-yellow/5 text-xs">
          <AlertTriangle size={13} className="text-terminal-yellow shrink-0 mt-0.5"/>
          <div>
            <span className="font-bold text-terminal-yellow">HIGH IMPACT TOMORROW: </span>
            <span className="text-terminal-muted">{calData.tomorrow?.map(e => e.title).join(' · ')}</span>
          </div>
        </div>
      )}
    </div>
  )
}

function DayQualityBadge({ dayQ }) {
  if (!dayQ) return null
  const factor = dayQ.factor ?? 1
  const color = factor >= 1.0
    ? 'border-terminal-green/40 bg-terminal-green/10 text-terminal-green'
    : factor >= 0.85
    ? 'border-terminal-yellow/40 bg-terminal-yellow/10 text-terminal-yellow'
    : 'border-terminal-red/40 bg-terminal-red/10 text-terminal-red'
  return (
    <div className={clsx('flex items-center gap-1.5 px-2 py-1 rounded border text-xs font-semibold', color)}
         title={dayQ.note}>
      {dayQ.day} <span className="opacity-70">×{factor}</span>
    </div>
  )
}

function LevelRow({ label, value, variant = 'default' }) {
  if (!value) return null
  const c = {
    default: 'text-terminal-text', green: 'text-terminal-green', red: 'text-terminal-red',
    yellow: 'text-terminal-yellow', blue: 'text-terminal-blue', muted: 'text-terminal-muted',
  }
  return (
    <div className="flex items-center justify-between text-xs py-1 border-b border-terminal-border/20">
      <span className="text-terminal-muted">{label}</span>
      <span className={clsx('font-mono font-semibold', c[variant])}>{fmt.price(value)}</span>
    </div>
  )
}

function EqualHL({ data }) {
  const all = [
    ...data.equal_highs.map(e => ({ ...e, is_high: true })),
    ...data.equal_lows.map(e => ({ ...e, is_high: false })),
  ].sort((a, b) => b.level - a.level)
  if (!all.length) return <div className="text-terminal-muted text-xs italic">None detected</div>
  return (
    <div className="space-y-1">
      {all.map((e, i) => (
        <div key={i} className={clsx('flex items-center gap-2 text-xs px-2 py-1.5 rounded border',
          e.is_high ? 'border-terminal-red/30 bg-terminal-red/5' : 'border-terminal-green/30 bg-terminal-green/5')}>
          <AlertTriangle size={11} className={e.is_high ? 'text-terminal-red' : 'text-terminal-green'}/>
          <span className={clsx('font-semibold shrink-0', e.is_high ? 'text-terminal-red' : 'text-terminal-green')}>
            {e.is_high ? 'EQH' : 'EQL'}
          </span>
          <span className="font-mono text-terminal-text">{fmt.price(e.level)}</span>
          <span className="text-terminal-muted ml-auto">×{e.count}</span>
        </div>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Advanced signal components
// ---------------------------------------------------------------------------

function SweepAlert({ sweeps }) {
  if (!sweeps?.length)
    return <div className="text-terminal-muted text-xs italic">No sweeps detected yet — waiting</div>

  return (
    <div className="space-y-1.5">
      {sweeps.slice(-5).reverse().map((s, i) => {
        const isBull = s.direction === 'bullish'
        const isFresh = s.is_fresh !== false
        return (
          <div key={i} className={clsx(
            'px-3 py-2 rounded border text-xs',
            isBull ? 'border-terminal-green/40 bg-terminal-green/10' : 'border-terminal-red/40 bg-terminal-red/10'
          )}>
            <div className="flex items-center gap-2 mb-0.5">
              {isBull ? <ArrowUpCircle size={12} className="text-terminal-green shrink-0"/>
                      : <ArrowDownCircle size={12} className="text-terminal-red shrink-0"/>}
              <span className={clsx('font-semibold', isBull ? 'text-terminal-green' : 'text-terminal-red')}>
                {s.label}
              </span>
              <span className={clsx('text-[10px] px-1 py-0.5 rounded font-semibold shrink-0',
                isFresh
                  ? 'bg-terminal-green/20 text-terminal-green border border-terminal-green/30'
                  : 'bg-terminal-muted/10 text-terminal-muted border border-terminal-border/30')}>
                {isFresh ? 'FRESH' : `STALE ${s.minutes_ago}m`}
              </span>
              <span className="font-mono text-terminal-muted ml-auto">{fmt.price(s.level)}</span>
            </div>
            <p className="text-terminal-muted leading-relaxed">{s.description}</p>
          </div>
        )
      })}
    </div>
  )
}

function MSSEvents({ events, structure }) {
  const structureColor = structure === 'bullish' ? 'text-terminal-green'
    : structure === 'bearish' ? 'text-terminal-red'
    : structure?.includes('lean') ? 'text-terminal-yellow'
    : 'text-terminal-muted'

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 text-xs">
        <span className="text-terminal-muted">HTF Structure:</span>
        <span className={clsx('font-semibold capitalize', structureColor)}>{structure || 'Unknown'}</span>
      </div>
      {!events?.length
        ? <div className="text-terminal-muted text-xs italic">No MSS / CHoCH detected</div>
        : events.slice(-4).reverse().map((e, i) => (
          <div key={i} className={clsx('flex items-start gap-2 text-xs px-2 py-1.5 rounded border',
            e.color === 'green' ? 'border-terminal-green/30 bg-terminal-green/5' : 'border-terminal-red/30 bg-terminal-red/5')}>
            <span className={clsx('font-bold shrink-0 mt-px', e.color === 'green' ? 'text-terminal-green' : 'text-terminal-red')}>
              {e.label}
            </span>
            <span className="text-terminal-muted leading-relaxed">{e.description}</span>
          </div>
        ))}
    </div>
  )
}

function OTEZone({ ote, currentPrice, inOte }) {
  if (!ote) return <div className="text-terminal-muted text-xs italic">Insufficient swing data for OTE</div>
  const isBull = ote.direction === 'bullish'
  return (
    <div className={clsx('space-y-2 p-3 rounded border',
      inOte ? (isBull ? 'border-terminal-green/50 bg-terminal-green/10' : 'border-terminal-red/50 bg-terminal-red/10')
             : 'border-terminal-border bg-terminal-card')}>
      {inOte && (
        <div className={clsx('flex items-center gap-1.5 text-xs font-bold',
          isBull ? 'text-terminal-green' : 'text-terminal-red')}>
          <Radio size={11} className="animate-pulse"/>
          PRICE IN OTE ZONE — {isBull ? 'LONG ENTRY AREA' : 'SHORT ENTRY AREA'}
        </div>
      )}
      <div className="text-xs space-y-1">
        <div className="flex justify-between">
          <span className="text-terminal-muted">Direction</span>
          <span className={clsx('font-semibold capitalize', isBull ? 'text-terminal-green' : 'text-terminal-red')}>
            {ote.direction}
          </span>
        </div>
        <div className="flex justify-between">
          <span className="text-terminal-muted">OTE Zone</span>
          <span className="font-mono text-terminal-text">
            {fmt.price(ote.ote_bottom)} – {fmt.price(ote.ote_top)}
          </span>
        </div>
        <div className="flex justify-between">
          <span className="text-terminal-muted">Equilibrium (0.5)</span>
          <span className="font-mono text-terminal-yellow">{fmt.price(ote.equilibrium)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-terminal-muted">Leg Range</span>
          <span className="font-mono text-terminal-muted">
            {fmt.price(ote.leg_low)} → {fmt.price(ote.leg_high)}
          </span>
        </div>
      </div>
      {currentPrice && (
        <div className="text-xs text-terminal-muted">{ote.description}</div>
      )}
    </div>
  )
}

function IPDALevels({ levels }) {
  if (!levels || !Object.keys(levels).length)
    return <div className="text-terminal-muted text-xs italic">Need more historical bars for IPDA</div>

  const periods = [20, 40, 60].filter(p => levels[`ipda_${p}d_high`])
  return (
    <div className="space-y-1">
      {periods.map(p => (
        <div key={p} className="text-xs">
          <div className="text-terminal-muted font-semibold mb-0.5">{p}-Day IPDA</div>
          <div className="flex gap-3">
            <div className="flex justify-between flex-1 border-b border-terminal-border/20 py-0.5">
              <span className="text-terminal-muted">High</span>
              <span className="font-mono text-terminal-red">{fmt.price(levels[`ipda_${p}d_high`])}</span>
            </div>
            <div className="flex justify-between flex-1 border-b border-terminal-border/20 py-0.5">
              <span className="text-terminal-muted">Low</span>
              <span className="font-mono text-terminal-green">{fmt.price(levels[`ipda_${p}d_low`])}</span>
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

function SMTCard({ smt }) {
  if (!smt?.detected)
    return <div className="text-terminal-muted text-xs italic">No SMT divergence detected</div>
  const isBull = smt.type === 'bullish_smt'
  return (
    <div className={clsx('px-3 py-2 rounded border text-xs',
      isBull ? 'border-terminal-green/40 bg-terminal-green/10' : 'border-terminal-red/40 bg-terminal-red/10')}>
      <div className={clsx('font-bold mb-1', isBull ? 'text-terminal-green' : 'text-terminal-red')}>
        {smt.label}
      </div>
      <p className="text-terminal-muted leading-relaxed">{smt.description}</p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Confluence Decision — the "what's the play" synthesizer
// ---------------------------------------------------------------------------

function ConfluenceDecision({ session, dp, draw, ifvgs, adv, data }) {
  if (!session || !adv) return null

  const inKillzone = session?.in_killzone
  const zone = dp?.zone
  const drawDir = draw?.direction
  const drawTarget = draw?.target
  const sweeps = adv?.liquidity_sweeps || []
  const recentSweep = adv?.recent_sweep
  const po3Phase = adv?.po3_phase?.phase
  const inOte = adv?.in_ote
  const structure = adv?.mss_choch?.last_structure
  const smt = adv?.smt_divergence
  const longScore = data?.long_setup?.score || 0
  const shortScore = data?.short_setup?.score || 0

  const bullishIFVGs = ifvgs.filter(f => f.base_type === 'bullish_fvg')
  const bearishIFVGs = ifvgs.filter(f => f.base_type === 'bearish_fvg')

  // Score each direction
  let longPoints = 0, shortPoints = 0
  const longChecks = [], shortChecks = []

  const check = (condition, label, pts, side) => {
    if (side === 'long' || side === 'both') {
      longChecks.push({ label, met: condition })
      if (condition) longPoints += pts
    }
    if (side === 'short' || side === 'both') {
      shortChecks.push({ label, met: condition })
      if (condition) shortPoints += pts
    }
  }

  check(inKillzone, 'NY Killzone active (9:30–11:30 AM)', 25, 'both')
  check(recentSweep?.direction === 'bullish', 'Bullish sweep of key level detected', 25, 'long')
  check(recentSweep?.direction === 'bearish', 'Bearish sweep of key level detected', 25, 'short')
  check(zone === 'discount', 'Price in discount zone (<50% range)', 15, 'long')
  check(zone === 'premium', 'Price in premium zone (>50% range)', 15, 'short')
  check(drawDir === 'up', 'Draw on liquidity is above price', 15, 'long')
  check(drawDir === 'down', 'Draw on liquidity is below price', 15, 'short')
  check(bullishIFVGs.length > 0, `Bullish iFVG present (${bullishIFVGs.length})`, 10, 'long')
  check(bearishIFVGs.length > 0, `Bearish iFVG present (${bearishIFVGs.length})`, 10, 'short')
  check(inOte && adv?.ote_zone?.direction === 'bullish', 'Price inside bullish OTE zone', 5, 'long')
  check(inOte && adv?.ote_zone?.direction === 'bearish', 'Price inside bearish OTE zone', 5, 'short')
  check(structure === 'bullish' || structure === 'bullish_lean', 'Market structure bullish', 5, 'long')
  check(structure === 'bearish' || structure === 'bearish_lean', 'Market structure bearish', 5, 'short')
  check(smt?.type === 'bullish_smt', 'Bullish SMT divergence', 5, 'long')
  check(smt?.type === 'bearish_smt', 'Bearish SMT divergence', 5, 'short')

  const maxPts = 100
  const longPct = Math.round((longPoints / maxPts) * 100)
  const shortPct = Math.round((shortPoints / maxPts) * 100)

  // Decision logic
  let decision, color, icon, subtitle, action, invalidation
  const noSweep = !recentSweep
  const outsideKZ = !inKillzone

  if (outsideKZ) {
    decision = 'NO TRADE — Outside Killzone'
    color = 'border-terminal-muted/40 bg-terminal-card'
    icon = <Ban size={18} className="text-terminal-muted"/>
    subtitle = `Wait for NY Killzone: 9:30–11:30 AM ET. Current session: ${session.session}.`
    action = 'Stand down. No trading outside the killzone — the edge disappears.'
    invalidation = null
  } else if (noSweep && po3Phase === 'accumulation') {
    decision = 'WAIT — No Sweep Yet'
    color = 'border-terminal-yellow/40 bg-terminal-yellow/5'
    icon = <Clock size={18} className="text-terminal-yellow"/>
    subtitle = 'Killzone is active but no key level has been swept. Sit on your hands.'
    action = `Watch: ${draw.reason || 'session levels'}. Wait for price to sweep a level before doing anything.`
    invalidation = 'If 11:30 AM passes with no setup, session is done — close charts.'
  } else if (longPoints > shortPoints && longPoints >= 50) {
    const conf = longPoints >= 75 ? 'HIGH' : longPoints >= 55 ? 'MEDIUM' : 'LOW'
    decision = `POTENTIAL LONG`
    color = 'border-terminal-green/50 bg-terminal-green/10'
    icon = <ArrowUpCircle size={18} className="text-terminal-green"/>
    subtitle = `Confidence: ${conf} (${longPoints}/${maxPts})`
    action = bullishIFVGs.length
      ? `Wait for price to pull back to bullish iFVG ${bullishIFVGs.map(f => `${f.bottom?.toFixed(2)}–${f.top?.toFixed(2)}`).join(', ')}. Enter on the touch. Target: ${drawTarget ? `$${drawTarget?.toFixed(2)}` : 'draw on liquidity above'}.`
      : `Bullish sweep detected. Look for a 30s/1m/2m FVG to form and invert (iFVG). Then enter on the iFVG retest.`
    invalidation = `Invalid if price closes below the sweep low or put pressure expands sharply.`
  } else if (shortPoints > longPoints && shortPoints >= 50) {
    const conf = shortPoints >= 75 ? 'HIGH' : shortPoints >= 55 ? 'MEDIUM' : 'LOW'
    decision = `POTENTIAL SHORT`
    color = 'border-terminal-red/50 bg-terminal-red/10'
    icon = <ArrowDownCircle size={18} className="text-terminal-red"/>
    subtitle = `Confidence: ${conf} (${shortPoints}/${maxPts})`
    action = bearishIFVGs.length
      ? `Wait for price to retrace to bearish iFVG ${bearishIFVGs.map(f => `${f.bottom?.toFixed(2)}–${f.top?.toFixed(2)}`).join(', ')}. Enter on the touch. Target: ${drawTarget ? `$${drawTarget?.toFixed(2)}` : 'draw on liquidity below'}.`
      : `Bearish sweep detected. Look for a 30s/1m/2m FVG to form and invert (iFVG). Then enter on the iFVG retest.`
    invalidation = `Invalid if price closes above the sweep high or call pressure expands sharply.`
  } else {
    decision = 'NO CLEAR EDGE — Wait'
    color = 'border-terminal-muted/40 bg-terminal-card'
    icon = <Minus size={18} className="text-terminal-muted"/>
    subtitle = `Long: ${longPoints}pts  ·  Short: ${shortPoints}pts — signals mixed or balanced`
    action = 'Mixed signals. Do not force a trade. Wait for one side to dominate cleanly.'
    invalidation = null
  }

  const isGreen = color.includes('green'), isRed = color.includes('red')
  const activeChecks = isGreen ? longChecks : isRed ? shortChecks : longChecks

  return (
    <div className={clsx('rounded border-2 p-4 space-y-3', color)}>
      {/* Header */}
      <div className="flex items-center gap-3">
        {icon}
        <div className="flex-1">
          <div className={clsx('text-base font-bold', isGreen ? 'text-terminal-green' : isRed ? 'text-terminal-red' : 'text-terminal-muted')}>
            {decision}
          </div>
          <div className="text-xs text-terminal-muted">{subtitle}</div>
        </div>
        <div className="text-right">
          <div className="text-xs text-terminal-muted">Confluence</div>
          <div className={clsx('font-mono font-bold text-lg', isGreen ? 'text-terminal-green' : isRed ? 'text-terminal-red' : 'text-terminal-muted')}>
            {isGreen ? longPct : isRed ? shortPct : Math.max(longPct, shortPct)}%
          </div>
        </div>
      </div>

      {/* Action */}
      {action && (
        <div className={clsx('text-sm px-3 py-2 rounded', isGreen ? 'bg-terminal-green/10 text-terminal-green' : isRed ? 'bg-terminal-red/10 text-terminal-red' : 'bg-terminal-border/30 text-terminal-muted')}>
          <span className="font-semibold">Action: </span>{action}
        </div>
      )}

      {/* Invalidation */}
      {invalidation && (
        <div className="text-xs text-terminal-muted px-3 py-1.5 rounded bg-terminal-border/20 border border-terminal-border/30">
          <span className="text-terminal-yellow font-semibold">⚠ Invalidated if: </span>{invalidation}
        </div>
      )}

      {/* Checklist */}
      <div className="grid grid-cols-2 gap-x-4 gap-y-0.5">
        {activeChecks.map((c, i) => (
          <div key={i} className="flex items-center gap-1.5 text-xs">
            {c.met
              ? <CheckCircle size={11} className="text-terminal-green shrink-0"/>
              : <XCircle size={11} className="text-terminal-muted shrink-0"/>}
            <span className={c.met ? 'text-terminal-text' : 'text-terminal-muted'}>{c.label}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Auto Trade Setup Card
// ---------------------------------------------------------------------------

function TradeSetupCard({ setup, symbol, instrument, isLoading, balance, setBalance, prevClose, setPrevClose, onRecalc }) {
  const [showInputs, setShowInputs] = useState(false)

  if (isLoading) {
    return (
      <div className="card border border-terminal-border animate-pulse">
        <div className="h-24 bg-terminal-border/20 rounded"/>
      </div>
    )
  }

  const hasSetup = setup && !setup.error && setup.entry_inst != null

  if (!hasSetup) {
    return (
      <div className="card border border-terminal-border/40">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <Calculator size={14} className="text-terminal-blue"/>
            <span className="text-xs font-semibold text-terminal-muted uppercase">Auto Trade Setup</span>
          </div>
          <button onClick={() => setShowInputs(s => !s)} className="text-xs text-terminal-muted hover:text-terminal-blue">
            {showInputs ? 'hide' : 'set account'}
          </button>
        </div>
        {showInputs && <AccountInputs balance={balance} setBalance={setBalance} prevClose={prevClose} setPrevClose={setPrevClose} onRecalc={onRecalc}/>}
        <div className="text-terminal-muted text-xs italic mt-1">
          {setup?.note || setup?.error || 'No trade setup — need sweep + iFVG first'}
        </div>
      </div>
    )
  }

  const isLong = setup.direction === 'bullish'
  const dirColor = isLong ? 'text-terminal-green' : 'text-terminal-red'
  const dirBorder = isLong ? 'border-terminal-green/50 bg-terminal-green/5' : 'border-terminal-red/50 bg-terminal-red/5'

  return (
    <div className={clsx('card border-2 space-y-3', dirBorder)}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          {isLong
            ? <ArrowUpCircle size={20} className="text-terminal-green"/>
            : <ArrowDownCircle size={20} className="text-terminal-red"/>}
          <div>
            <div className={clsx('text-base font-bold', dirColor)}>
              {isLong ? 'LONG' : 'SHORT'} {instrument}
            </div>
            <div className="text-xs text-terminal-muted">{setup.instrument_name} · ${setup.usd_per_point}/pt</div>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <div className="text-right">
            <div className="text-xs text-terminal-muted">R:R</div>
            <div className="font-mono font-bold text-terminal-yellow text-lg">{setup.rr_ratio}R</div>
          </div>
          <button onClick={() => setShowInputs(s => !s)} className="text-xs text-terminal-muted hover:text-terminal-blue px-2 py-1 rounded border border-terminal-border/50">
            {showInputs ? '▲' : '⚙'}
          </button>
        </div>
      </div>

      {/* Account inputs (collapsible) */}
      {showInputs && (
        <AccountInputs balance={balance} setBalance={setBalance} prevClose={prevClose} setPrevClose={setPrevClose} onRecalc={onRecalc}/>
      )}

      {/* Current price + distance to entry */}
      {setup.current_inst != null && (
        <div className="flex items-center justify-between px-3 py-2 rounded bg-terminal-bg border border-terminal-border/50 text-xs">
          <div className="flex items-center gap-2">
            <span className="text-terminal-muted">Current {instrument}</span>
            <span className="font-mono font-bold text-terminal-text text-base">{setup.current_inst}</span>
          </div>
          {setup.pts_to_entry != null && (
            <div className={clsx('font-mono text-xs px-2 py-0.5 rounded', Math.abs(setup.pts_to_entry) < 5 ? 'text-terminal-yellow bg-terminal-yellow/10' : 'text-terminal-muted')}>
              {isLong
                ? setup.pts_to_entry < 0
                  ? `↓ ${Math.abs(setup.pts_to_entry)} pts pullback to entry`
                  : `↑ ${setup.pts_to_entry} pts rally needed (wait)`
                : setup.pts_to_entry > 0
                  ? `↑ ${setup.pts_to_entry} pts rally to entry`
                  : `↓ ${Math.abs(setup.pts_to_entry)} pts drop needed (wait)`
              }
            </div>
          )}
        </div>
      )}

      {/* Entry / Stop / Target — big numbers */}
      <div className="grid grid-cols-3 gap-2 text-center">
        <div className="bg-terminal-bg rounded-lg p-3 border border-terminal-border/50">
          <div className="text-xs text-terminal-muted mb-1">ENTRY</div>
          <div className="font-mono font-bold text-terminal-blue text-xl">{setup.entry_inst}</div>
          <div className="text-xs text-terminal-muted mt-0.5">{instrument} pts</div>
        </div>
        <div className="bg-terminal-bg rounded-lg p-3 border border-terminal-red/30">
          <div className="text-xs text-terminal-red mb-1">STOP</div>
          <div className="font-mono font-bold text-terminal-red text-xl">{setup.stop_inst}</div>
          <div className="text-xs text-terminal-muted mt-0.5">{setup.stop_dist_inst} pts risk</div>
        </div>
        <div className="bg-terminal-bg rounded-lg p-3 border border-terminal-green/30">
          <div className="text-xs text-terminal-green mb-1">TARGET</div>
          <div className="font-mono font-bold text-terminal-green text-xl">{setup.target_inst}</div>
          <div className="text-xs text-terminal-muted mt-0.5">{setup.target_dist_inst} pts gain</div>
        </div>
      </div>

      {/* Sizing strip */}
      <div className="flex items-center gap-3 px-3 py-2 rounded bg-terminal-bg border border-terminal-border/50 text-sm">
        <ShieldAlert size={14} className="text-terminal-yellow shrink-0"/>
        <span className="font-mono font-semibold text-terminal-text">{setup.contracts} contract{setup.contracts !== 1 ? 's' : ''}</span>
        <span className="text-terminal-muted">·</span>
        <span className="font-mono text-terminal-red">${setup.risk_amount} risk</span>
        <span className="text-terminal-muted">·</span>
        <span className="text-xs text-terminal-muted truncate">{setup.entry_note}</span>
      </div>

      {/* Breakeven */}
      <div className="px-3 py-2 rounded bg-terminal-yellow/10 border border-terminal-yellow/30 text-xs">
        <span className="font-semibold text-terminal-yellow">Breakeven: </span>
        <span className="text-terminal-text">
          Move SL to <span className="font-mono">{setup.entry_inst}</span> when price reaches{' '}
          <span className="font-mono font-bold">{setup.breakeven_trigger_inst}</span>
        </span>
      </div>

      {/* TP levels */}
      <div>
        <div className="text-xs text-terminal-muted mb-2">Take Profit Levels</div>
        <div className="grid grid-cols-4 gap-1.5">
          {Object.entries(setup.tp_levels || {}).map(([label, tp]) => (
            <div key={label} className="bg-terminal-bg rounded p-2 border border-terminal-border/50 text-center">
              <div className="text-xs text-terminal-muted">{label}</div>
              <div className="font-mono font-bold text-terminal-green text-sm">{tp.price_inst}</div>
              <div className="text-xs text-terminal-muted">+{tp.pts}pts</div>
              <div className="text-xs text-terminal-green">+${tp.total_gain}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Context note */}
      {setup.target_note && (
        <div className="text-xs text-terminal-muted italic">{setup.target_note}</div>
      )}
    </div>
  )
}

function AccountInputs({ balance, setBalance, prevClose, setPrevClose, onRecalc }) {
  return (
    <div className="flex gap-2 flex-wrap items-end p-2 bg-terminal-bg rounded border border-terminal-border/50">
      <div>
        <label className="text-xs text-terminal-muted block mb-1">Balance ($)</label>
        <input type="number" value={balance} onChange={e => setBalance(e.target.value)}
          className="w-28 bg-terminal-card border border-terminal-border rounded px-2 py-1 text-xs font-mono text-terminal-text focus:outline-none focus:border-terminal-blue"
          placeholder="25000"/>
      </div>
      <div>
        <label className="text-xs text-terminal-muted block mb-1">Yesterday's Close ($)</label>
        <input type="number" value={prevClose} onChange={e => setPrevClose(e.target.value)}
          className="w-28 bg-terminal-card border border-terminal-border rounded px-2 py-1 text-xs font-mono text-terminal-text focus:outline-none focus:border-terminal-blue"
          placeholder="same as balance"/>
      </div>
      <button onClick={onRecalc} className="px-3 py-1 text-xs bg-terminal-blue/20 text-terminal-blue border border-terminal-blue/40 rounded font-semibold hover:bg-terminal-blue/30">
        Recalculate
      </button>
    </div>
  )
}

const SYMBOLS = [
  { value: 'NQ=F', label: 'MNQ', secondary: 'ES=F', instrument: 'MNQ' },
  { value: 'ES=F', label: 'MES', secondary: 'NQ=F', instrument: 'MES' },
  { value: 'GC=F', label: 'MGC', secondary: 'GLD', instrument: 'MGC' },
]

// ── Multi-Timeframe Confluence Panel ─────────────────────────────────────────
function ConfluencePanel({ data, isLoading, symbol }) {
  if (isLoading) return (
    <div className="flex items-center justify-center h-40 text-terminal-muted text-sm animate-pulse">
      Fetching 1H → 15m → 5m data…
    </div>
  )
  if (!data) return (
    <div className="flex items-center justify-center h-40 text-terminal-muted text-sm">
      Click Multi-TF to load confluence
    </div>
  )

  const TF_ORDER = ['1h', '15m', '5m']
  const TF_ROLE  = { '1h': 'Macro Bias', '15m': 'Zone / FVG', '5m': 'Entry Signal' }

  const alignColor = data.align_dir === 'bullish' ? 'border-terminal-green/40 bg-terminal-green/5 text-terminal-green'
                   : data.align_dir === 'bearish' ? 'border-terminal-red/40 bg-terminal-red/5 text-terminal-red'
                   : 'border-terminal-border bg-terminal-card text-terminal-muted'

  return (
    <div className="flex flex-col gap-3">
      {/* Alignment verdict */}
      <div className={`flex items-center gap-3 px-4 py-3 rounded-lg border font-bold text-sm ${alignColor}`}>
        <span className="text-xl">{data.align_dir === 'bullish' ? '▲' : data.align_dir === 'bearish' ? '▼' : '◆'}</span>
        <span>{data.alignment}</span>
      </div>

      {/* Timeframe matrix */}
      <div className="grid gap-2" style={{ gridTemplateColumns: 'repeat(3, 1fr)' }}>
        {TF_ORDER.map(tf => {
          const d = (data.timeframes || {})[tf]
          if (!d || d.error) return (
            <div key={tf} className="bg-terminal-card border border-terminal-border rounded-lg p-3">
              <div className="text-xs text-terminal-muted">{tf.toUpperCase()} — no data</div>
            </div>
          )

          const biasColor = d.bias === 'bullish' ? 'text-terminal-green' : d.bias === 'bearish' ? 'text-terminal-red' : 'text-terminal-muted'
          const biasArrow = d.bias === 'bullish' ? '▲' : d.bias === 'bearish' ? '▼' : '◆'
          const gradeColor = d.grade === 'A+' ? 'text-green-400' : d.grade === 'A' ? 'text-blue-400' : 'text-terminal-muted'
          const borderColor = d.bias === 'bullish' ? 'border-terminal-green/30' : d.bias === 'bearish' ? 'border-terminal-red/30' : 'border-terminal-border'

          return (
            <div key={tf} className={`bg-terminal-card border rounded-lg p-3 flex flex-col gap-2 ${borderColor}`}>
              {/* TF header */}
              <div className="flex items-center justify-between">
                <div>
                  <span className="font-bold text-terminal-text text-sm">{tf.toUpperCase()}</span>
                  <span className="text-[10px] text-terminal-muted ml-2">{TF_ROLE[tf]}</span>
                </div>
                <span className={`font-mono font-bold text-lg ${biasColor}`}>{biasArrow}</span>
              </div>

              {/* Bias + Grade */}
              <div className="flex items-center gap-2 flex-wrap">
                <span className={`text-xs font-bold uppercase ${biasColor}`}>{d.bias}</span>
                <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded border ${
                  d.grade === 'A+' ? 'border-green-500/40 bg-green-500/10 text-green-400' :
                  d.grade === 'A'  ? 'border-blue-500/40 bg-blue-500/10 text-blue-400' :
                  'border-terminal-border bg-terminal-card text-terminal-muted'
                }`}>{d.grade}</span>
                {d.in_ote && <span className="text-[10px] text-yellow-400 border border-yellow-500/30 bg-yellow-500/10 px-1.5 py-0.5 rounded">IN OTE</span>}
              </div>

              {/* Structure */}
              {d.structure && d.structure !== 'unknown' && (
                <div className="text-[10px] text-terminal-muted">
                  Structure: <span className="text-terminal-text">{d.structure.replace(/_/g,' ').toUpperCase()}</span>
                </div>
              )}

              {/* PO3 phase */}
              {d.po3_phase && (
                <div className="text-[10px] text-terminal-muted">
                  PO3: <span className={
                    d.po3_phase === 'Manipulation' ? 'text-terminal-yellow' :
                    d.po3_phase === 'Distribution'  ? 'text-terminal-green' : 'text-terminal-text'
                  }>{d.po3_phase}</span>
                </div>
              )}

              {/* Zone */}
              {d.zone && (
                <div className="text-[10px] text-terminal-muted">
                  Zone: <span className={d.zone === 'discount' ? 'text-terminal-green' : 'text-terminal-red'}>
                    {d.zone.toUpperCase()}
                  </span>
                  {d.zone_pct != null && <span className="text-terminal-muted ml-1">({d.zone_pct?.toFixed(0)}%)</span>}
                </div>
              )}

              {/* DOL */}
              {d.dol_direction && d.dol_direction !== 'neutral' && (
                <div className="text-[10px] text-terminal-muted">
                  DOL: <span className={d.dol_direction === 'up' ? 'text-terminal-green' : 'text-terminal-red'}>
                    {d.dol_direction === 'up' ? '↑' : '↓'} {d.dol_target?.toFixed(2)}
                  </span>
                  <span className="text-terminal-muted ml-1 text-[9px] truncate"> — {d.dol_reason}</span>
                </div>
              )}

              {/* Sweeps + iFVGs */}
              <div className="flex gap-3 text-[10px] text-terminal-muted">
                {d.sweep_count > 0 && (
                  <span>Sweeps: <span className="text-terminal-yellow">{d.sweep_count}</span></span>
                )}
                {d.ifvg_count > 0 && (
                  <span>iFVG: <span className="text-terminal-yellow">{d.ifvg_count}</span></span>
                )}
              </div>

              {/* Most recent sweep label */}
              {d.recent_sweep && (
                <div className="text-[9px] text-terminal-muted border-t border-terminal-border/50 pt-1 mt-0.5 truncate">
                  {d.recent_sweep.label}
                </div>
              )}

              {/* Current price */}
              {d.current_price != null && (
                <div className="text-[10px] font-mono text-terminal-muted border-t border-terminal-border/50 pt-1 mt-0.5">
                  Price: <span className="text-terminal-text">{d.current_price?.toFixed(2)}</span>
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Session levels summary */}
      {data.timeframes?.['5m']?.session_levels && (() => {
        const sl = data.timeframes['5m'].session_levels
        return (
          <div className="flex items-center gap-4 px-3 py-2 bg-terminal-card border border-terminal-border rounded text-xs flex-wrap">
            <span className="text-terminal-muted font-medium">Session Levels (5m):</span>
            {sl.asia_high   && <span><span className="text-blue-400">Asia</span> <span className="font-mono">{sl.asia_high?.toFixed(2)} / {sl.asia_low?.toFixed(2)}</span></span>}
            {sl.london_high && <span><span className="text-orange-400">London</span> <span className="font-mono">{sl.london_high?.toFixed(2)} / {sl.london_low?.toFixed(2)}</span></span>}
            {sl.prev_day_high && <span><span className="text-terminal-muted">PDH/PDL</span> <span className="font-mono text-terminal-green">{sl.prev_day_high?.toFixed(2)}</span> / <span className="font-mono text-terminal-red">{sl.prev_day_low?.toFixed(2)}</span></span>}
          </div>
        )
      })()}

      {/* Go/No-Go checklist */}
      <div className="bg-terminal-card border border-terminal-border rounded-lg p-3">
        <div className="text-[10px] text-terminal-muted uppercase tracking-wider mb-2">Go / No-Go Decision</div>
        {(() => {
          const h1 = data.timeframes?.['1h'] || {}
          const m15 = data.timeframes?.['15m'] || {}
          const m5  = data.timeframes?.['5m']  || {}
          const checks = [
            { label: '1H bias aligned with trade direction',   met: h1.bias !== 'neutral' },
            { label: '15m structure confirms (CHoCH / MSS)',   met: m15.structure && !['unknown','bullish_structure','bearish_structure'].includes(m15.structure) },
            { label: 'Price in correct zone (discount=long, premium=short)', met: (h1.bias === 'bullish' && m15.zone === 'discount') || (h1.bias === 'bearish' && m15.zone === 'premium') },
            { label: 'Sweep detected on 15m or 5m',            met: (m15.sweep_count > 0) || (m5.sweep_count > 0) },
            { label: 'iFVG entry zone present on 5m',          met: m5.ifvg_count > 0 },
            { label: '5m setup grade A or A+',                 met: ['A+','A'].includes(m5.grade) },
            { label: 'DOL target identified',                  met: m5.dol_direction && m5.dol_direction !== 'neutral' },
          ]
          const metCount = checks.filter(c => c.met).length
          const go = metCount >= 5
          return (
            <>
              <div className="space-y-1 mb-2">
                {checks.map((c, i) => (
                  <div key={i} className="flex items-center gap-2 text-xs">
                    <span className={c.met ? 'text-terminal-green' : 'text-terminal-muted'}>
                      {c.met ? '✓' : '○'}
                    </span>
                    <span className={c.met ? 'text-terminal-text' : 'text-terminal-muted'}>{c.label}</span>
                  </div>
                ))}
              </div>
              <div className={`text-xs font-bold px-2 py-1 rounded border inline-block ${
                go ? 'text-terminal-green border-terminal-green/40 bg-terminal-green/10'
                   : 'text-terminal-red border-terminal-red/40 bg-terminal-red/10'
              }`}>
                {go ? `✓ ${metCount}/7 — CONDITIONS MET, look for entry` : `${metCount}/7 — NOT READY, wait for more confluence`}
              </div>
            </>
          )
        })()}
      </div>
    </div>
  )
}

export default function ICT() {
  const [symbolIdx, setSymbolIdx] = useState(0)
  const [activeTab, setActiveTab] = useState('signals')   // 'signals' | 'confluence'
  const [tradeBalance, setTradeBalance] = useState('25000')
  const [tradePrevClose, setTradePrevClose] = useState('')
  const [tradeKey, setTradeKey] = useState(0)
  const [useLive, setUseLive] = useState(true)  // true = ProjectX live data
  const sym = SYMBOLS[symbolIdx]

  // Live ICT — runs on real ProjectX MNQ/MES/MGC bars (no Yahoo delay)
  const { data: liveData, isLoading: liveLoading, refetch: liveRefetch, dataUpdatedAt: liveUpdatedAt } = useQuery({
    queryKey: ['ict-live', sym.instrument],
    queryFn: () => fetch(`/api/projectx/ict?symbol=${sym.instrument}&interval=5m`).then(r => r.json()),
    refetchInterval: 30_000,
    staleTime: 15_000,
    enabled: useLive,
  })

  // Yahoo Finance fallback
  const { data: yahooData, isLoading: yahooLoading, refetch: yahooRefetch, dataUpdatedAt: yahooUpdatedAt } = useQuery({
    queryKey: ['ict-analysis', sym.value],
    queryFn: () => apiFetch(`/api/ict/analysis?symbol=${sym.value}`),
    refetchInterval: 60_000,
    staleTime: 30_000,
    enabled: !useLive,
  })

  const data        = useLive ? liveData    : yahooData
  const isLoading   = useLive ? liveLoading : yahooLoading
  const refetch     = useLive ? liveRefetch : yahooRefetch
  const dataUpdatedAt = useLive ? liveUpdatedAt : yahooUpdatedAt

  const { data: adv, isLoading: advLoading } = useQuery({
    queryKey: ['ict-advanced', sym.value, sym.secondary],
    queryFn: () => apiFetch(`/api/ict/advanced?symbol=${sym.value}&secondary=${sym.secondary}`),
    refetchInterval: 60_000,
    staleTime: 30_000,
  })

  const { data: confluence, isLoading: confLoading } = useQuery({
    queryKey: ['ict-confluence', sym.value],
    queryFn: () => apiFetch(`/api/ict/confluence?symbol=${sym.value}`),
    enabled: activeTab === 'confluence',
    refetchInterval: 60_000,
    staleTime: 30_000,
  })

  const { data: tradeSetupData, isLoading: tradeLoading } = useQuery({
    queryKey: ['ict-trade-setup', sym.value, sym.instrument, tradeBalance, tradePrevClose, tradeKey],
    queryFn: () => {
      const params = new URLSearchParams({
        symbol: sym.value,
        instrument: sym.instrument,
        balance: tradeBalance || '25000',
      })
      if (tradePrevClose) params.set('prev_close', tradePrevClose)
      return apiFetch(`/api/ict/trade-setup?${params}`)
    },
    refetchInterval: 60_000,
    staleTime: 30_000,
  })

  const { data: calData } = useQuery({
    queryKey: ['econ-calendar'],
    queryFn: () => apiFetch('/api/market/calendar'),
    refetchInterval: 300_000,
    staleTime: 240_000,
  })

  const session = data?.session
  const levels = data?.session_levels || {}
  const dp = data?.discount_premium || {}
  const draw = data?.draw_on_liquidity || {}
  const fvgs = data?.fair_value_gaps || []
  const ifvgs = data?.ifvgs || []
  const obs = data?.order_blocks || []
  const ehl = data?.equal_highs_lows || { equal_highs: [], equal_lows: [] }
  const summary = data?.summary || {}
  const sortedFvgs = [...fvgs].sort((a, b) => (b.inverted ? 1 : 0) - (a.inverted ? 1 : 0))
  const htf = data?.htf_bias || {}
  const dayQ = data?.day_quality || {}

  const po3 = adv?.po3_phase
  const sweeps = adv?.liquidity_sweeps || []
  const mss = adv?.mss_choch || {}
  const ote = adv?.ote_zone
  const inOte = adv?.in_ote || false
  const ipda = adv?.ipda_levels || {}
  const smt = adv?.smt_divergence || {}
  const recentSweep = adv?.recent_sweep
  const advBonus = adv?.advanced_score_bonus || 0

  return (
    <div className="space-y-4">
      {/* Calendar Warning — very top */}
      <CalendarWarning calData={calData}/>

      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-bold text-terminal-text">ICT / Smart Money</h1>
          <div className="flex gap-1">
            {SYMBOLS.map((s, i) => (
              <button key={s.value} onClick={() => setSymbolIdx(i)}
                className={clsx('px-2.5 py-1 rounded text-xs font-semibold border transition-colors',
                  symbolIdx === i
                    ? 'bg-terminal-blue/20 text-terminal-blue border-terminal-blue/40'
                    : 'bg-terminal-card text-terminal-muted border-terminal-border hover:border-terminal-blue/30'
                )}>
                {s.label}
              </button>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {/* Tab switcher */}
          <div className="flex gap-1 border border-terminal-border rounded overflow-hidden">
            {[['signals','Signals'],['confluence','Multi-TF']].map(([v,l]) => (
              <button key={v} onClick={() => setActiveTab(v)}
                className={`px-3 py-1 text-xs font-medium transition-colors ${
                  activeTab === v ? 'bg-terminal-blue text-white' : 'bg-terminal-card text-terminal-muted hover:text-terminal-text'
                }`}>{l}</button>
            ))}
          </div>
          {dataUpdatedAt && <span className="text-xs text-terminal-muted">{fmt.timeAgo(new Date(dataUpdatedAt).toISOString())}</span>}
          <button
            onClick={() => setUseLive(v => !v)}
            className={`px-2 py-0.5 rounded text-xs font-bold border ${useLive ? 'bg-green-900 border-green-600 text-green-400' : 'bg-terminal-card border-terminal-border text-gray-500'}`}
          >
            {useLive ? '● LIVE' : '○ Yahoo'}
          </button>
          <button onClick={() => refetch()} className="flex items-center gap-1 text-xs text-terminal-blue hover:underline">
            <RefreshCw size={11}/> Refresh
          </button>
        </div>
      </div>

      {/* ── Multi-TF Confluence Tab ──────────────────────────────────────────── */}
      {activeTab === 'confluence' && (
        <ConfluencePanel data={confluence} isLoading={confLoading} symbol={sym.value} />
      )}

      {/* Status row */}
      {!isLoading && session && (
        <div className="flex items-start gap-3 flex-wrap">
          <SessionBadge session={session.session} inKillzone={session.in_killzone} timeEt={session.time_et}/>
          <DayQualityBadge dayQ={dayQ}/>
          {dp.zone && <ZonePill zone={dp.zone} pct={dp.position_pct}/>}
          {advBonus > 0 && (
            <div className="inline-flex items-center gap-1.5 px-2 py-1 rounded text-xs font-semibold bg-terminal-purple/20 text-terminal-purple border border-terminal-purple/30">
              <Zap size={11}/> +{advBonus} advanced signal bonus
            </div>
          )}
        </div>
      )}

      {/* PO3 Phase — most important context */}
      {!advLoading && po3 && (
        <PhaseBadge
          phase={po3.phase}
          label={po3.phase_label}
          description={po3.description}
          minutesSinceOpen={po3.minutes_since_open}
        />
      )}

      {/* ── HTF BIAS — daily context above confluence ── */}
      {!isLoading && htf.bias && (
        <HTFBiasPanel htf={htf} dayQ={dayQ}/>
      )}

      {/* ── CONFLUENCE DECISION — the play ── */}
      {!isLoading && !advLoading && (
        <ConfluenceDecision
          session={session}
          dp={dp}
          draw={draw}
          ifvgs={ifvgs}
          adv={adv}
          data={data}
        />
      )}

      {/* ── AUTO TRADE SETUP — entry/stop/target/sizing ── */}
      <TradeSetupCard
        setup={tradeSetupData?.setup}
        symbol={sym.value}
        instrument={sym.instrument}
        isLoading={tradeLoading}
        balance={tradeBalance}
        setBalance={setTradeBalance}
        prevClose={tradePrevClose}
        setPrevClose={setTradePrevClose}
        onRecalc={() => setTradeKey(k => k + 1)}
      />

      {/* ── SWEEP ALERT — the main trigger ── */}
      {recentSweep && (
        <div className={clsx(
          'px-4 py-3 rounded border-2 font-semibold text-sm flex items-center gap-3',
          recentSweep.direction === 'bullish'
            ? 'border-terminal-green bg-terminal-green/10 text-terminal-green'
            : 'border-terminal-red bg-terminal-red/10 text-terminal-red'
        )}>
          <Radio size={16} className="animate-pulse shrink-0"/>
          <div>
            <div>SWEEP DETECTED — {recentSweep.label}</div>
            <div className="text-xs font-normal opacity-80 mt-0.5">{recentSweep.description}</div>
          </div>
        </div>
      )}

      {/* Main 3-column grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">

        {/* ── LEFT: Levels + IPDA + DOL + EHL ── */}
        <div className="space-y-4">
          <div className="card">
            <div className="text-xs font-semibold text-terminal-muted uppercase mb-3">Session Levels</div>
            {isLoading
              ? <div className="space-y-2">{Array.from({length:8}).map((_,i)=><div key={i} className="h-5 bg-terminal-border/20 rounded animate-pulse"/>)}</div>
              : <div className="space-y-0">
                  <LevelRow label="Today High" value={levels.today_high} variant="green"/>
                  <LevelRow label="Today Low" value={levels.today_low} variant="red"/>
                  <LevelRow label="London High" value={levels.london_high} variant="yellow"/>
                  <LevelRow label="London Low" value={levels.london_low} variant="yellow"/>
                  <LevelRow label="Asia High" value={levels.asia_high} variant="blue"/>
                  <LevelRow label="Asia Low" value={levels.asia_low} variant="blue"/>
                  <LevelRow label="Pre-mkt High" value={levels.premarket_high} variant="muted"/>
                  <LevelRow label="Pre-mkt Low" value={levels.premarket_low} variant="muted"/>
                  <LevelRow label="Prev Day High" value={levels.prev_day_high} variant="muted"/>
                  <LevelRow label="Prev Day Low" value={levels.prev_day_low} variant="muted"/>
                  <LevelRow label="Equilibrium" value={dp.equilibrium} variant="default"/>
                </div>}
          </div>

          <div className="card">
            <div className="text-xs font-semibold text-terminal-muted uppercase mb-3 flex items-center gap-2">
              <Layers size={12}/> IPDA Levels
            </div>
            {advLoading
              ? <div className="h-16 bg-terminal-border/20 rounded animate-pulse"/>
              : <IPDALevels levels={ipda}/>}
          </div>

          <div className="card">
            <div className="text-xs font-semibold text-terminal-muted uppercase mb-3 flex items-center gap-2">
              <Target size={12}/> Draw on Liquidity
            </div>
            {isLoading ? <div className="h-8 bg-terminal-border/20 rounded animate-pulse"/>
            : <DrawArrow direction={draw.direction} target={draw.target} reason={draw.reason}/>}
          </div>

          <div className="card">
            <div className="text-xs font-semibold text-terminal-muted uppercase mb-3 flex items-center gap-2">
              <AlertTriangle size={12}/> Equal Highs / Lows
            </div>
            {isLoading ? <div className="h-16 bg-terminal-border/20 rounded animate-pulse"/> : <EqualHL data={ehl}/>}
          </div>
        </div>

        {/* ── MIDDLE: Grades + Sweeps + MSS + iFVGs + FVGs ── */}
        <div className="space-y-4">

          {!isLoading && data?.long_setup && data?.short_setup && (
            <div className="grid grid-cols-2 gap-2">
              <SetupGrade grade={data.long_setup.grade} score={data.long_setup.score} checklist={data.long_setup.checklist} title="Long Setup"/>
              <SetupGrade grade={data.short_setup.grade} score={data.short_setup.score} checklist={data.short_setup.checklist} title="Short Setup"/>
            </div>
          )}

          {/* Liquidity Sweeps — THE trigger */}
          <div className="card">
            <div className="text-xs font-semibold text-terminal-muted uppercase mb-3 flex items-center gap-2">
              <Radio size={12} className={sweeps.length ? 'text-terminal-yellow animate-pulse' : ''}/>
              Liquidity Sweeps ({sweeps.length})
            </div>
            {advLoading
              ? <div className="h-10 bg-terminal-border/20 rounded animate-pulse"/>
              : <SweepAlert sweeps={sweeps}/>}
          </div>

          {/* MSS / CHoCH */}
          <div className="card">
            <div className="text-xs font-semibold text-terminal-muted uppercase mb-3 flex items-center gap-2">
              <Activity size={12}/> MSS / CHoCH
            </div>
            {advLoading
              ? <div className="h-10 bg-terminal-border/20 rounded animate-pulse"/>
              : <MSSEvents events={mss.events} structure={mss.last_structure}/>}
          </div>

          {/* iFVGs */}
          {ifvgs.length > 0 && (
            <div className="card border border-terminal-purple/30">
              <div className="text-xs font-semibold text-terminal-purple uppercase mb-2 flex items-center gap-2">
                <Zap size={12}/> iFVGs — Entry Zones ({ifvgs.length})
              </div>
              <div className="space-y-1">{ifvgs.map((f,i) => <FVGRow key={i} fvg={f}/>)}</div>
            </div>
          )}

          {/* All FVGs */}
          <div className="card">
            <div className="text-xs font-semibold text-terminal-muted uppercase mb-3 flex items-center justify-between">
              <span>Fair Value Gaps</span>
              <span className="font-normal text-terminal-muted">
                ↑{summary.unfilled_bullish_fvgs||0} ↓{summary.unfilled_bearish_fvgs||0} total:{summary.total_fvgs||0}
              </span>
            </div>
            {isLoading
              ? <div className="space-y-2">{Array.from({length:4}).map((_,i)=><div key={i} className="h-7 bg-terminal-border/20 rounded animate-pulse"/>)}</div>
              : sortedFvgs.length === 0
                ? <div className="text-terminal-muted text-xs italic">No FVGs detected</div>
                : <div className="space-y-1 max-h-48 overflow-y-auto">
                    {sortedFvgs.slice(-12).reverse().map((f,i) => <FVGRow key={i} fvg={f}/>)}
                  </div>}
          </div>
        </div>

        {/* ── RIGHT: OTE + SMT + OBs + Reference ── */}
        <div className="space-y-4">

          {/* OTE Zone */}
          <div className="card">
            <div className="text-xs font-semibold text-terminal-muted uppercase mb-3 flex items-center gap-2">
              <Target size={12}/> OTE Zone (0.618 – 0.786)
            </div>
            {advLoading
              ? <div className="h-24 bg-terminal-border/20 rounded animate-pulse"/>
              : <OTEZone ote={ote} currentPrice={adv?.current_price} inOte={inOte}/>}
          </div>

          {/* SMT Divergence */}
          <div className="card">
            <div className="text-xs font-semibold text-terminal-muted uppercase mb-3 flex items-center gap-2">
              <Activity size={12}/> SMT Divergence ({sym.value} vs {sym.secondary})
            </div>
            {advLoading
              ? <div className="h-10 bg-terminal-border/20 rounded animate-pulse"/>
              : <SMTCard smt={smt}/>}
          </div>

          {/* Order Blocks */}
          <div className="card">
            <div className="text-xs font-semibold text-terminal-muted uppercase mb-3 flex items-center gap-2">
              <BarChart2 size={12}/> Order Blocks ({obs.length})
            </div>
            {isLoading
              ? <div className="space-y-2">{Array.from({length:3}).map((_,i)=><div key={i} className="h-7 bg-terminal-border/20 rounded animate-pulse"/>)}</div>
              : obs.length === 0
                ? <div className="text-terminal-muted text-xs italic">No OBs detected</div>
                : <div className="space-y-1">
                    {[...obs].reverse().map((ob, i) => {
                      const isBull = ob.type === 'bullish_ob'
                      return (
                        <div key={i} className={clsx('flex items-center gap-2 text-xs px-2 py-1.5 rounded border',
                          isBull ? 'border-terminal-green/30 bg-terminal-green/5' : 'border-terminal-red/30 bg-terminal-red/5')}>
                          <span className={clsx('font-semibold shrink-0', isBull ? 'text-terminal-green' : 'text-terminal-red')}>
                            {isBull ? 'BOB' : 'SOB'}
                          </span>
                          <span className="font-mono text-terminal-text">{fmt.price(ob.low)} – {fmt.price(ob.high)}</span>
                          <span className="text-terminal-muted ml-auto">{isBull ? 'demand' : 'supply'}</span>
                        </div>
                      )
                    })}
                  </div>}
          </div>

          {/* Strategy reference */}
          <div className="card bg-terminal-card2 text-xs space-y-3">
            <div className="text-terminal-text font-semibold">A+ Setup Checklist</div>
            <div>
              <div className="text-terminal-green font-semibold mb-1">Long Entry</div>
              <div className="text-terminal-muted space-y-0.5">
                <div>1. Sweep EQL / Asia Low / London Low</div>
                <div>2. Strong bullish displacement (V-shape)</div>
                <div>3. Mark iFVG on 30s / 1m / 2m / 3m</div>
                <div>4. Enter when price returns to iFVG</div>
                <div>5. Price in discount (&lt;50% daily range)</div>
                <div>6. Target: EQH / session high / DOL</div>
                <div>7. Stop: swing low of sweep</div>
              </div>
            </div>
            <div>
              <div className="text-terminal-red font-semibold mb-1">Short Entry</div>
              <div className="text-terminal-muted space-y-0.5">
                <div>1. Sweep EQH / Asia High / London High</div>
                <div>2. Strong bearish displacement (V-shape)</div>
                <div>3. Mark iFVG on 30s / 1m / 2m / 3m</div>
                <div>4. Enter when price returns to iFVG</div>
                <div>5. Price in premium (&gt;50% daily range)</div>
                <div>6. Target: EQL / session low / DOL</div>
                <div>7. Stop: swing high of sweep</div>
              </div>
            </div>
            <div className="border-t border-terminal-border pt-2 text-terminal-yellow">
              <div className="font-semibold mb-1">No Trade</div>
              <div className="text-terminal-muted space-y-0.5">
                <div>• Outside NY Killzone (9:30–11:30 AM ET)</div>
                <div>• No sweep of a key level</div>
                <div>• No clear opposing draw on liquidity</div>
                <div>• Setup looks "okay" but not obvious</div>
              </div>
            </div>
          </div>
        </div>

      </div>
    </div>
  )
}
