import { useEffect, useRef, useState, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { createChart, CrosshairMode, LineStyle } from 'lightweight-charts'
import { apiFetch, fmt } from '../lib/api'

const SYMBOLS = [
  { symbol: 'NQ=F', label: 'MNQ', ictSymbol: 'NQ=F', pxSymbol: 'MNQ' },
  { symbol: 'ES=F', label: 'MES', ictSymbol: 'ES=F', pxSymbol: 'MES' },
  { symbol: 'GC=F', label: 'MGC', ictSymbol: 'GC=F', pxSymbol: 'MGC' },
]

const INTERVAL_PERIODS = {
  '1m':  { label: '1m',  periods: ['1d', '5d'] },
  '5m':  { label: '5m',  periods: ['1d', '5d', '1mo'] },
  '15m': { label: '15m', periods: ['5d', '1mo', '3mo'] },
  '1h':  { label: '1h',  periods: ['1mo', '3mo', '6mo'] },
  '1D':  { label: '1D',  periods: ['3mo', '6mo', '1y', '2y'] },
}

const PERIOD_LABELS = {
  '1d': '1D', '5d': '5D', '1mo': '1M', '3mo': '3M',
  '6mo': '6M', '1y': '1Y', '2y': '2Y',
}

const DEFAULT_OVERLAYS = { fvg: true, ifvg: true, ob: true, eql: true, dol: true, or30: false, pivot: false, round: false }

// Round number chop zones per instrument — ICT: price respects big figures
const ROUND_LEVELS = {
  'NQ=F': [18000,19000,20000,21000,22000,23000,24000,25000,26000,27000,28000,29000,30000,31000,32000],
  'ES=F': [4000,4200,4400,4600,4800,5000,5200,5400,5600,5800,6000,6200],
  'GC=F': [1800,1900,2000,2100,2200,2300,2400,2500,2600,2700,2800,2900,3000,3100,3200,3300,3400],
}

function toUnix(isoTime) {
  return Math.floor(new Date(isoTime).getTime() / 1000)
}

export default function Charts() {
  const [symbolIndex, setSymbolIndex] = useState(0)
  const [interval, setInterval] = useState('5m')
  const [period, setPeriod]   = useState('1d')
  const [hovered, setHovered] = useState(null)
  const [overlays, setOverlays] = useState(DEFAULT_OVERLAYS)
  const [volColor, setVolColor] = useState(false)
  const [showSma200, setShowSma200] = useState(false)
  const [useLive, setUseLive] = useState(true)   // true = ProjectX live, false = Yahoo

  const { symbol, ictSymbol, pxSymbol } = SYMBOLS[symbolIndex]

  const chartContainerRef = useRef(null)
  const chartRef      = useRef(null)
  const candleRef     = useRef(null)
  const volumeRef     = useRef(null)
  const vwapRef       = useRef(null)
  const sma200Ref     = useRef(null)
  const sessionLinesRef = useRef([])
  const ictLinesRef   = useRef([])

  const handleIntervalChange = useCallback((iv) => {
    setInterval(iv)
    const first = INTERVAL_PERIODS[iv]?.periods[0]
    if (first) setPeriod(first)
  }, [])

  const validPeriods = INTERVAL_PERIODS[interval]?.periods || []
  const isIntraday   = ['1m', '5m', '15m', '30m', '1h'].includes(interval)

  // Live (ProjectX) bars — real-time, no delay
  const pxLimitMap = { '1m': 300, '5m': 500, '15m': 400, '30m': 300, '1h': 500, '1d': 90 }
  const pxLimit = pxLimitMap[interval] || 300
  const { data: pxData, isLoading: pxLoading } = useQuery({
    queryKey: ['chart-px', pxSymbol, interval],
    queryFn: () => fetch(`/api/projectx/bars?symbol=${pxSymbol}&interval=${interval}&limit=${pxLimit}`)
      .then(r => r.json())
      .then(d => ({
        // Normalize to same shape as Yahoo chart endpoint
        bars: (d.bars || []).map(b => ({
          time:   b.time,
          open:   b.open,
          high:   b.high,
          low:    b.low,
          close:  b.close,
          volume: b.volume,
        })),
        symbol: pxSymbol,
        source: 'projectx',
      })),
    refetchInterval: 30_000,   // refresh every 30s — near real-time
    staleTime: 15_000,
    enabled: useLive,
  })

  // Yahoo Finance fallback
  const { data: yahooData, isLoading: yahooLoading, isFetching } = useQuery({
    queryKey: ['chart', symbol, interval, period],
    queryFn: () => apiFetch(`/api/market/chart?symbol=${symbol}&interval=${interval}&period=${period}`),
    refetchInterval: 60_000,
    staleTime: 30_000,
    enabled: !useLive,
  })

  const data = useLive ? pxData : yahooData
  const isLoading = useLive ? pxLoading : yahooLoading

  const { data: ictData } = useQuery({
    queryKey: ['chart-ict', ictSymbol],
    queryFn: () => apiFetch(`/api/ict/analysis?symbol=${ictSymbol}`),
    enabled: !!ictSymbol,
    refetchInterval: 60_000,
    staleTime: 30_000,
  })

  // ── Create chart once on mount ───────────────────────────────────────────
  useEffect(() => {
    if (!chartContainerRef.current) return

    const chart = createChart(chartContainerRef.current, {
      width: chartContainerRef.current.clientWidth,
      height: 500,
      layout: { background: { type: 'solid', color: '#0D0F14' }, textColor: '#94A3B8' },
      grid:   { vertLines: { color: '#1E2129' }, horzLines: { color: '#1E2129' } },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: '#1E2129' },
      timeScale: { borderColor: '#1E2129', timeVisible: true, secondsVisible: false },
    })

    const candle = chart.addCandlestickSeries({
      upColor: '#10B981', downColor: '#EF4444',
      borderUpColor: '#10B981', borderDownColor: '#EF4444',
      wickUpColor: '#10B981', wickDownColor: '#EF4444',
    })

    const volume = chart.addHistogramSeries({
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
    })
    volume.priceScale().applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } })

    const vwap = chart.addLineSeries({
      color: '#F59E0B', lineWidth: 2, title: 'VWAP',
      priceLineVisible: false, lastValueVisible: true,
    })

    const sma200 = chart.addLineSeries({
      color: '#FFFFFF', lineWidth: 1, title: '200 SMA',
      priceLineVisible: false, lastValueVisible: true,
      lineStyle: 0,
    })

    chartRef.current   = chart
    candleRef.current  = candle
    volumeRef.current  = volume
    vwapRef.current    = vwap
    sma200Ref.current  = sma200

    chart.subscribeCrosshairMove((param) => {
      if (!param.time || !param.seriesData) { setHovered(null); return }
      const c = param.seriesData.get(candle)
      if (c) {
        const v = param.seriesData.get(volume)
        setHovered({ open: c.open, high: c.high, low: c.low, close: c.close, volume: v?.value ?? null, time: param.time })
      }
    })

    const ro = new ResizeObserver((entries) => {
      for (const e of entries) chart.applyOptions({ width: e.contentRect.width })
    })
    ro.observe(chartContainerRef.current)

    return () => {
      ro.disconnect()
      chart.remove()
      chartRef.current = candleRef.current = volumeRef.current = vwapRef.current = sma200Ref.current = null
    }
  }, [])

  // ── Update candles + VWAP ────────────────────────────────────────────────
  useEffect(() => {
    if (!data || !candleRef.current) return

    const rawBars = (data.bars || [])
      .filter((b) => b.open != null && b.high != null && b.low != null && b.close != null)
      .sort((a, b) => toUnix(a.time) - toUnix(b.time))

    // Volume percentile thresholds for intensity coloring
    const sortedVols = [...rawBars].map((b) => b.volume || 0).filter((v) => v > 0).sort((a, b) => a - b)
    const p25 = sortedVols[Math.floor(sortedVols.length * 0.25)] || 0
    const p75 = sortedVols[Math.floor(sortedVols.length * 0.75)] || 0

    const bars = rawBars.map((b) => {
      const isUp = b.close >= b.open
      const t    = toUnix(b.time)
      if (!volColor) return { time: t, open: b.open, high: b.high, low: b.low, close: b.close }

      // Map volume to opacity suffix: high=ff, mid=aa, low=55
      const vol = b.volume || 0
      const alpha = vol >= p75 ? 'ff' : vol >= p25 ? 'aa' : '55'
      const color = isUp ? `#10B981${alpha}` : `#EF4444${alpha}`
      return { time: t, open: b.open, high: b.high, low: b.low, close: b.close, color, wickColor: color, borderColor: color }
    })

    const vols = rawBars.map((b) => ({
      time: toUnix(b.time), value: b.volume || 0,
      color: b.close >= b.open ? '#10B981cc' : '#EF4444cc',
    }))

    try { candleRef.current.setData(bars) }   catch (e) { console.error(e) }
    try { volumeRef.current.setData(vols) }   catch (e) { console.error(e) }

    const vwapBars = (data.vwap_data || [])
      .map((v) => ({ time: toUnix(v.time), value: v.value }))
      .sort((a, b) => a.time - b.time)
    try { vwapRef.current.setData(vwapBars) } catch (e) { console.error(e) }

    // 200 SMA — simple moving average over last 200 bars' closes
    const smaBars = []
    for (let i = 199; i < bars.length; i++) {
      const slice = bars.slice(i - 199, i + 1)
      const avg = slice.reduce((s, b) => s + b.close, 0) / 200
      smaBars.push({ time: bars[i].time, value: parseFloat(avg.toFixed(4)) })
    }
    try { if (sma200Ref.current) sma200Ref.current.setData(smaBars) } catch (e) { console.error(e) }

    if (chartRef.current) chartRef.current.timeScale().fitContent()
  }, [data, volColor])

  // ── Show / hide 200 SMA ──────────────────────────────────────────────────
  useEffect(() => {
    if (!sma200Ref.current) return
    try {
      sma200Ref.current.applyOptions({ visible: showSma200 })
    } catch (_) {}
  }, [showSma200])

  // ── Draw all price lines: session levels + ICT overlays ─────────────────
  useEffect(() => {
    if (!candleRef.current) return

    // Clear old lines
    ;[...sessionLinesRef.current, ...ictLinesRef.current].forEach((pl) => {
      try { candleRef.current.removePriceLine(pl) } catch (_) {}
    })
    sessionLinesRef.current = []
    ictLinesRef.current     = []

    const addLine = (ref, price, color, label, style, width = 1) => {
      if (price == null) return
      try {
        const pl = candleRef.current.createPriceLine({ price, color, lineWidth: width, lineStyle: style, axisLabelVisible: true, title: label })
        ref.push(pl)
      } catch (_) {}
    }

    // Session levels — always visible and prominent (width 2, labeled clearly)
    const lvl  = data?.session_levels   || {}
    const ilvl = ictData?.session_levels || {}
    const sl   = { ...ilvl, ...lvl }  // chart data wins when present

    const SESSION_DEFS = [
      { key: 'asia_high',     label: 'Asia H',   color: '#60A5FA', style: LineStyle.Dashed, w: 2 },
      { key: 'asia_low',      label: 'Asia L',   color: '#60A5FA', style: LineStyle.Dashed, w: 2 },
      { key: 'london_high',   label: 'London H', color: '#FB923C', style: LineStyle.Dashed, w: 2 },
      { key: 'london_low',    label: 'London L', color: '#FB923C', style: LineStyle.Dashed, w: 2 },
      { key: 'prev_day_high', label: 'PDH',      color: '#94A3B8', style: LineStyle.Solid,  w: 2 },
      { key: 'prev_day_low',  label: 'PDL',      color: '#94A3B8', style: LineStyle.Solid,  w: 2 },
      { key: 'today_high',    label: 'Today H',  color: '#F1F5F9', style: LineStyle.Solid,  w: 1 },
      { key: 'today_low',     label: 'Today L',  color: '#F1F5F9', style: LineStyle.Solid,  w: 1 },
    ]
    SESSION_DEFS.forEach(({ key, label, color, style, w }) =>
      addLine(sessionLinesRef.current, sl[key], color, label, style, w)
    )

    if (!ictData) return

    // ── ICT overlays: only the most signal-rich, fewest lines ────────────────

    // iFVGs first — these are the ENTRY zones, most important (max 2)
    if (overlays.ifvg) {
      ;(ictData.ifvgs || []).slice(0, 2).forEach((f) => {
        addLine(ictLinesRef.current, f.top,    '#F59E0B', 'iFVG ↑', LineStyle.Solid, 2)
        addLine(ictLinesRef.current, f.bottom, '#F59E0B', 'iFVG ↓', LineStyle.Solid, 2)
      })
    }

    // DOL target — single most important line on the chart
    if (overlays.dol) {
      const dol = ictData.draw_on_liquidity
      if (dol?.target && dol.direction !== 'neutral') {
        const c = dol.direction === 'up' ? '#38BDF8' : '#F87171'
        addLine(ictLinesRef.current, dol.target, c, `DOL ${dol.direction === 'up' ? '↑' : '↓'}`, LineStyle.Solid, 2)
      }
    }

    // FVGs — only the most recent unfilled per direction (2 lines per side max)
    if (overlays.fvg) {
      const unfilled = (ictData.fair_value_gaps || []).filter((f) => !f.filled && !f.inverted)
      const recentBull = unfilled.filter((f) => f.base_type === 'bullish_fvg').slice(-1)
      const recentBear = unfilled.filter((f) => f.base_type === 'bearish_fvg').slice(-1)
      recentBull.forEach((f) => {
        addLine(ictLinesRef.current, f.top,    '#10B98188', 'FVG↑', LineStyle.Dashed)
        addLine(ictLinesRef.current, f.bottom, '#10B98188', 'FVG↑', LineStyle.Dashed)
      })
      recentBear.forEach((f) => {
        addLine(ictLinesRef.current, f.top,    '#EF444488', 'FVG↓', LineStyle.Dashed)
        addLine(ictLinesRef.current, f.bottom, '#EF444488', 'FVG↓', LineStyle.Dashed)
      })
    }

    // Order Blocks — 1 bullish (demand) + 1 bearish (supply), closest to price
    if (overlays.ob) {
      const price = data?.bars?.at(-1)?.close
      const allOBs = ictData.order_blocks || []
      const sortByCloseness = (arr) => price
        ? [...arr].sort((a, b) => Math.abs(a.mid - price) - Math.abs(b.mid - price))
        : arr
      const bestBull = sortByCloseness(allOBs.filter((o) => o.type === 'bullish_ob')).slice(0, 1)
      const bestBear = sortByCloseness(allOBs.filter((o) => o.type === 'bearish_ob')).slice(0, 1)
      bestBull.forEach((ob) => {
        addLine(ictLinesRef.current, ob.high, '#10B981', 'Demand H', LineStyle.Solid, 1)
        addLine(ictLinesRef.current, ob.low,  '#10B981', 'Demand L', LineStyle.Solid, 1)
      })
      bestBear.forEach((ob) => {
        addLine(ictLinesRef.current, ob.high, '#EF4444', 'Supply H', LineStyle.Solid, 1)
        addLine(ictLinesRef.current, ob.low,  '#EF4444', 'Supply L', LineStyle.Solid, 1)
      })
    }

    // Equal H/L — only the strongest cluster (highest count) for each side
    if (overlays.eql) {
      const ehl = ictData.equal_highs_lows || {}
      const topH = [...(ehl.equal_highs || [])].sort((a, b) => b.count - a.count).slice(0, 1)
      const topL = [...(ehl.equal_lows  || [])].sort((a, b) => b.count - a.count).slice(0, 1)
      topH.forEach((e) => addLine(ictLinesRef.current, e.level, '#A78BFA', `EQH ×${e.count}`, LineStyle.Dotted, 2))
      topL.forEach((e) => addLine(ictLinesRef.current, e.level, '#A78BFA', `EQL ×${e.count}`, LineStyle.Dotted, 2))
    }

    // 30-min Opening Range — first 30 minutes of NY session (9:30-10:00 ET)
    if (overlays.or30 && data?.bars && isIntraday) {
      // Group by ET date, take the most recent day
      const byDay = {}
      ;(data.bars || []).forEach((b) => {
        const etDate = new Date(b.time).toLocaleDateString('en-US', { timeZone: 'America/New_York' })
        ;(byDay[etDate] = byDay[etDate] || []).push(b)
      })
      const lastDay = Object.values(byDay).pop()
      if (lastDay) {
        const orBars = lastDay.filter((b) => {
          const et   = new Date(new Date(b.time).toLocaleString('en-US', { timeZone: 'America/New_York' }))
          const mins = et.getHours() * 60 + et.getMinutes()
          return mins >= 570 && mins < 600  // 9:30–10:00
        })
        if (orBars.length > 0) {
          const orH = Math.max(...orBars.map((b) => b.high))
          const orL = Math.min(...orBars.map((b) => b.low))
          addLine(ictLinesRef.current, orH, '#9333EA', 'OR High', LineStyle.Dashed, 2)
          addLine(ictLinesRef.current, orL, '#9333EA', 'OR Low',  LineStyle.Dashed, 2)
        }
      }
    }

    // Pivot Points — Standard formula from prior day H/L/C
    if (overlays.pivot) {
      const pdH = sl.prev_day_high
      const pdL = sl.prev_day_low
      const pdC = sl.prev_day_close
      if (pdH && pdL && pdC) {
        const P  = (pdH + pdL + pdC) / 3
        const R1 = 2 * P - pdL
        const R2 = P + (pdH - pdL)
        const S1 = 2 * P - pdH
        const S2 = P - (pdH - pdL)
        addLine(ictLinesRef.current, P,  '#94A3B8', 'PP',  LineStyle.Solid,  2)
        addLine(ictLinesRef.current, R1, '#34D399', 'R1',  LineStyle.Dashed, 1)
        addLine(ictLinesRef.current, R2, '#34D39966', 'R2', LineStyle.Dotted, 1)
        addLine(ictLinesRef.current, S1, '#F87171', 'S1',  LineStyle.Dashed, 1)
        addLine(ictLinesRef.current, S2, '#F8717166', 'S2', LineStyle.Dotted, 1)
      }
    }
    // Round number chop zones — ICT big figure levels (only draw those near current price ±15%)
    if (overlays.round) {
      const currentPrice = data?.bars?.at(-1)?.close
      const levels = ROUND_LEVELS[symbol] || []
      if (currentPrice) {
        const priceRange = currentPrice * 0.15
        levels
          .filter((lvl) => Math.abs(lvl - currentPrice) <= priceRange)
          .forEach((lvl) => {
            addLine(ictLinesRef.current, lvl, '#6B728055', `${(lvl / 1000).toFixed(0)}K`, LineStyle.Dotted, 1)
          })
      }
    }
  }, [data, ictData, overlays, isIntraday])

  const isUp = hovered ? hovered.close >= hovered.open : true

  function toggleOverlay(key) {
    setOverlays((prev) => ({ ...prev, [key]: !prev[key] }))
  }

  return (
    <div className="flex flex-col gap-3">
      {/* Header row 1: symbol · interval · period */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="text-terminal-blue font-bold text-sm">CHARTS</div>

        <div className="flex gap-1">
          {SYMBOLS.map((s, i) => (
            <button
              key={s.symbol}
              onClick={() => setSymbolIndex(i)}
              className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                symbolIndex === i
                  ? 'bg-terminal-blue text-white'
                  : 'bg-terminal-card text-terminal-muted hover:text-terminal-text border border-terminal-border'
              }`}
            >
              {s.label}
            </button>
          ))}
        </div>

        <div className="w-px h-5 bg-terminal-border" />

        <div className="flex gap-1">
          {Object.entries(INTERVAL_PERIODS).map(([iv, { label }]) => (
            <button
              key={iv}
              onClick={() => handleIntervalChange(iv)}
              className={`px-2 py-1 rounded text-xs font-medium transition-colors ${
                interval === iv
                  ? 'bg-terminal-blue text-white'
                  : 'bg-terminal-card text-terminal-muted hover:text-terminal-text border border-terminal-border'
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="w-px h-5 bg-terminal-border" />

        <div className="flex gap-1">
          {validPeriods.map((p) => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={`px-2 py-1 rounded text-xs font-medium transition-colors ${
                period === p
                  ? 'bg-terminal-yellow/20 text-terminal-yellow border border-terminal-yellow/40'
                  : 'bg-terminal-card text-terminal-muted hover:text-terminal-text border border-terminal-border'
              }`}
            >
              {PERIOD_LABELS[p] || p}
            </button>
          ))}
        </div>

        <div className="w-px h-5 bg-terminal-border" />

        {/* Live / Yahoo toggle */}
        <button
          onClick={() => setUseLive(v => !v)}
          className={`px-3 py-1 rounded text-xs font-bold border transition-colors ${
            useLive
              ? 'bg-green-900 border-green-600 text-green-400'
              : 'bg-terminal-card border-terminal-border text-gray-500'
          }`}
        >
          {useLive ? '● LIVE' : '○ Yahoo'}
        </button>

        <div className="ml-auto flex items-center gap-2 text-xs text-terminal-muted">
          {isLoading && <span className="animate-pulse text-terminal-yellow">loading...</span>}
          {data?.bars?.length != null && <span>{data.bars.length} bars</span>}
          {data?.source === 'projectx' && <span className="text-green-500">ProjectX</span>}
        </div>
      </div>

      {/* Header row 2: ICT overlay toggles */}
      {ictSymbol ? (
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-[10px] text-terminal-muted uppercase tracking-wider">ICT Overlays</span>
          {[
            { key: 'fvg',  label: 'FVG',     activeColor: 'border-green-500/50 text-green-400 bg-green-500/10' },
            { key: 'ifvg', label: 'iFVG',    activeColor: 'border-yellow-500/50 text-yellow-400 bg-yellow-500/10' },
            { key: 'ob',   label: 'OB',      activeColor: 'border-blue-500/50 text-blue-400 bg-blue-500/10' },
            { key: 'eql',  label: 'EQL/EQH', activeColor: 'border-purple-500/50 text-purple-400 bg-purple-500/10' },
            { key: 'dol',  label: 'DOL',     activeColor: 'border-cyan-500/50 text-cyan-400 bg-cyan-500/10' },
            { key: 'or30',  label: 'OR 30m',   activeColor: 'border-purple-400/50 text-purple-300 bg-purple-500/10' },
            { key: 'pivot', label: 'Pivots',    activeColor: 'border-slate-400/50 text-slate-300 bg-slate-500/10' },
            { key: 'round', label: 'Big Fig',   activeColor: 'border-slate-500/50 text-slate-400 bg-slate-500/10' },
          ].map(({ key, label, activeColor }) => (
            <button
              key={key}
              onClick={() => toggleOverlay(key)}
              className={`px-2 py-0.5 rounded text-[11px] font-medium border transition-colors ${
                overlays[key]
                  ? activeColor
                  : 'border-terminal-border text-terminal-muted bg-terminal-card'
              }`}
            >
              {overlays[key] ? '✓ ' : ''}{label}
            </button>
          ))}
          <div className="w-px h-4 bg-terminal-border" />
          <button
            onClick={() => setShowSma200((v) => !v)}
            title="200 SMA on 30-min — white line — above = longs only, below = shorts only (Coach Dakota)"
            className={`px-2 py-0.5 rounded text-[11px] font-medium border transition-colors ${
              showSma200
                ? 'border-slate-300/50 text-white bg-slate-500/10'
                : 'border-terminal-border text-terminal-muted bg-terminal-card'
            }`}
          >
            {showSma200 ? '✓ ' : ''}200 SMA
          </button>
          <button
            onClick={() => setVolColor((v) => !v)}
            title="Volume-intensity candle coloring — brighter = more volume"
            className={`px-2 py-0.5 rounded text-[11px] font-medium border transition-colors ${
              volColor
                ? 'border-emerald-500/50 text-emerald-300 bg-emerald-500/10'
                : 'border-terminal-border text-terminal-muted bg-terminal-card'
            }`}
          >
            {volColor ? '✓ ' : ''}Vol Color
          </button>
          {ictData?.draw_on_liquidity?.direction && ictData.draw_on_liquidity.direction !== 'neutral' && (
            <span className="text-[10px] text-terminal-muted ml-2">
              DOL → {ictData.draw_on_liquidity.reason}
            </span>
          )}
        </div>
      ) : null}

      {/* OHLCV hover strip */}
      <div className="flex items-center gap-4 px-3 py-1.5 bg-terminal-card border border-terminal-border rounded text-xs font-mono h-8">
        {hovered ? (
          <>
            <span className="text-terminal-muted">O</span>
            <span className={isUp ? 'text-terminal-green' : 'text-terminal-red'}>{fmt.num(hovered.open)}</span>
            <span className="text-terminal-muted">H</span>
            <span className="text-terminal-green">{fmt.num(hovered.high)}</span>
            <span className="text-terminal-muted">L</span>
            <span className="text-terminal-red">{fmt.num(hovered.low)}</span>
            <span className="text-terminal-muted">C</span>
            <span className={isUp ? 'text-terminal-green font-bold' : 'text-terminal-red font-bold'}>{fmt.num(hovered.close)}</span>
            {hovered.volume != null && (
              <>
                <span className="text-terminal-muted">V</span>
                <span className="text-terminal-text">{fmt.num(Math.round(hovered.volume))}</span>
              </>
            )}
          </>
        ) : (
          <span className="text-terminal-muted">Hover over a candle to see OHLCV data</span>
        )}
      </div>

      {/* Chart */}
      <div className="relative bg-terminal-card border border-terminal-border rounded overflow-hidden">
        {isLoading && (
          <div className="absolute inset-0 flex items-center justify-center bg-terminal-bg/80 z-10">
            <div className="flex flex-col items-center gap-2">
              <div className="w-8 h-8 border-2 border-terminal-blue border-t-transparent rounded-full animate-spin" />
              <span className="text-terminal-muted text-xs">Loading chart data...</span>
            </div>
          </div>
        )}
        <div ref={chartContainerRef} style={{ width: '100%', height: '500px' }} />
      </div>

      {/* Session levels info bar */}
      {(data?.session_levels || ictData?.session_levels) && (
        <div className="flex items-center gap-4 px-3 py-2 bg-terminal-card border border-terminal-border rounded text-xs flex-wrap">
          <span className="text-terminal-muted font-medium shrink-0">Session Levels:</span>
          {(() => {
            const sl = { ...(ictData?.session_levels || {}), ...(data?.session_levels || {}) }
            return (
              <>
                {sl.asia_high   && <span><span className="text-blue-400">Asia</span> <span className="text-terminal-text">{fmt.num(sl.asia_high)} / {fmt.num(sl.asia_low)}</span></span>}
                {sl.london_high && <span><span className="text-orange-400">London</span> <span className="text-terminal-text">{fmt.num(sl.london_high)} / {fmt.num(sl.london_low)}</span></span>}
                {sl.prev_day_high && <span><span className="text-terminal-muted">PDH/PDL</span> <span className="text-terminal-green">{fmt.num(sl.prev_day_high)}</span> / <span className="text-terminal-red">{fmt.num(sl.prev_day_low)}</span></span>}
                {sl.today_high  && <span><span className="text-terminal-text font-medium">Today</span> <span className="text-terminal-green">{fmt.num(sl.today_high)}</span> / <span className="text-terminal-red">{fmt.num(sl.today_low)}</span></span>}
              </>
            )
          })()}
          {isIntraday && data?.vwap_data?.length > 0 && (
            <span><span className="text-yellow-400">VWAP</span> <span className="text-terminal-text">{fmt.num(data.vwap_data[data.vwap_data.length - 1]?.value)}</span></span>
          )}
        </div>
      )}

      {/* ICT signal summary bar */}
      {ictData && (
        <div className="flex items-center gap-4 px-3 py-2 bg-terminal-card border border-terminal-border rounded text-xs flex-wrap">
          <span className="text-terminal-muted font-medium shrink-0">ICT Signals:</span>
          {ictData.summary && (
            <>
              <span><span className="text-green-400">FVG↑</span> <span className="text-terminal-text">{ictData.summary.unfilled_bullish_fvgs ?? 0}</span></span>
              <span><span className="text-red-400">FVG↓</span> <span className="text-terminal-text">{ictData.summary.unfilled_bearish_fvgs ?? 0}</span></span>
              <span><span className="text-yellow-400">iFVG</span> <span className="text-terminal-text">{ictData.summary.ifvg_count ?? 0}</span></span>
              <span><span className="text-blue-400">OB</span> <span className="text-terminal-text">{ictData.summary.total_obs ?? 0}</span></span>
            </>
          )}
          {ictData.discount_premium?.zone && (
            <span>
              <span className="text-terminal-muted">Zone</span>{' '}
              <span className={ictData.discount_premium.zone === 'discount' ? 'text-green-400' : 'text-red-400'}>
                {ictData.discount_premium.zone.toUpperCase()} ({ictData.discount_premium.position_pct?.toFixed(1)}%)
              </span>
            </span>
          )}
          {ictData.draw_on_liquidity?.direction && ictData.draw_on_liquidity.direction !== 'neutral' && (
            <span>
              <span className="text-cyan-400">DOL</span>{' '}
              <span className="text-terminal-text">{ictData.draw_on_liquidity.direction === 'up' ? '↑' : '↓'} {fmt.num(ictData.draw_on_liquidity.target)}</span>
              <span className="text-terminal-muted ml-1">— {ictData.draw_on_liquidity.reason}</span>
            </span>
          )}
          <span>
            <span className={ictData.long_setup?.grade === 'A+' || ictData.long_setup?.grade === 'A' ? 'text-green-400' : 'text-terminal-muted'}>
              Long {ictData.long_setup?.grade ?? '--'}
            </span>
            {' / '}
            <span className={ictData.short_setup?.grade === 'A+' || ictData.short_setup?.grade === 'A' ? 'text-red-400' : 'text-terminal-muted'}>
              Short {ictData.short_setup?.grade ?? '--'}
            </span>
          </span>
        </div>
      )}
    </div>
  )
}
