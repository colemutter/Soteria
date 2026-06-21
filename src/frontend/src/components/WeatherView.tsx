import { useEffect, useState } from 'react'
import { simClock } from '../lib/simClock'
import {
  getSolarDataset,
  conditionsAt,
  type SolarDataset,
} from '../lib/solarData'

/**
 * "Space Weather" screen: time-series charts of the geomagnetic Kp index and the
 * interplanetary magnetic field (Bz/Bt) — the same data driving the solar-wind
 * and auroral layers (and the demo storm when demo mode is on). A vertical "now"
 * marker separates observed history from forecast.
 *
 * Each chart sets its own time window: Kp reaches into the 2-day forecast; the
 * IMF is observation-only, so it shows just the recent past.
 */

const HOUR = 3600 * 1000

// Chart geometry (drawn in a 1000×240 viewBox, scaled to fit via CSS).
const CW = 1000
const CH = 240
const M = { l: 46, r: 16, t: 16, b: 26 }
const IW = CW - M.l - M.r
const IH = CH - M.t - M.b

const clamp01 = (x: number) => Math.min(1, Math.max(0, x))

interface GLevel {
  label: string
  color: string
}
function gLevel(kp: number): GLevel {
  if (kp >= 9) return { label: 'G5 · Extreme', color: '#ff2d6e' }
  if (kp >= 8) return { label: 'G4 · Severe', color: '#ff4d4d' }
  if (kp >= 7) return { label: 'G3 · Strong', color: '#ff6b3d' }
  if (kp >= 6) return { label: 'G2 · Moderate', color: '#ff9b3d' }
  if (kp >= 5) return { label: 'G1 · Minor', color: '#ffd24f' }
  return { label: 'G0 · Quiet', color: '#46e08a' }
}

type Pt = { t: number; v: number }
interface Tick {
  t: number
  label: string
}

/** Cap a series to ~`max` evenly-strided points (keeps charts readable). */
function downsample(pts: Pt[], max: number): Pt[] {
  if (pts.length <= max) return pts
  const stride = Math.ceil(pts.length / max)
  return pts.filter((_, i) => i % stride === 0)
}

/** Relative-time label, e.g. "−1d", "−6h", "now", "+12h", "+2d". */
function relLabel(deltaMs: number): string {
  if (Math.abs(deltaMs) < HOUR / 2) return 'now'
  const h = Math.round(deltaMs / HOUR)
  const sign = h > 0 ? '+' : '−'
  const a = Math.abs(h)
  return a % 24 === 0 ? `${sign}${a / 24}d` : `${sign}${a}h`
}

/** `n+1` evenly-spaced relative ticks across [t0, t1]. */
function relTicks(t0: number, t1: number, now: number, n = 4): Tick[] {
  return Array.from({ length: n + 1 }, (_, i) => {
    const t = t0 + ((t1 - t0) * i) / n
    return { t, label: relLabel(t - now) }
  })
}

export function WeatherView({ demo }: { demo: boolean }) {
  const [ds, setDs] = useState<SolarDataset | null>(null)
  const [, force] = useState(0)

  useEffect(() => {
    let active = true
    const load = async () => {
      const d = await getSolarDataset(demo, true) // full history for the charts
      if (active && d) setDs(d)
    }
    void load()
    const id = setInterval(() => void load(), 60_000)
    return () => {
      active = false
      clearInterval(id)
    }
  }, [demo])

  // Re-render with the clock so the "now" marker and current values track time.
  useEffect(() => {
    const id = setInterval(() => force((n) => n + 1), 1000)
    const unsub = simClock.subscribe(() => force((n) => n + 1))
    return () => {
      clearInterval(id)
      unsub()
    }
  }, [])

  const now = simClock.date.getTime()
  const cur = ds ? conditionsAt(ds, simClock.date) : null
  const g = cur ? gLevel(cur.kp) : null

  // One shared window for both charts, capped to the hours of data that exist.
  // The high-cadence IMF is the binding series, so the window spans its range
  // (ending at "now" for the live feed; the demo data runs now → +2 days).
  const magAll = ds ? [...ds.bzSeries, ...ds.btSeries] : []
  const allT = ds ? [...magAll, ...ds.kpSeries].map((p) => p.t) : []
  let t0 = now - 24 * HOUR
  let t1 = now
  if (magAll.length) {
    t0 = Math.min(...magAll.map((p) => p.t))
    t1 = Math.max(now, ...magAll.map((p) => p.t))
  } else if (allT.length) {
    t0 = Math.min(...allT)
    t1 = Math.max(now, ...allT)
  }
  if (t1 - t0 < HOUR) {
    t0 -= HOUR
    t1 += HOUR
  }
  const xs = (t: number) => M.l + clamp01((t - t0) / (t1 - t0)) * IW
  const ticks = relTicks(t0, t1, now)
  // Both charts use the same window.
  const xsk = xs
  const xsi = xs
  const kpTicks: Tick[] = ticks
  const imfTicks: Tick[] = ticks
  const inWin = (p: Pt) => p.t >= t0 && p.t <= t1

  // ---- Kp ----
  const ysk = (v: number) => M.t + (1 - Math.min(9, Math.max(0, v)) / 9) * IH
  const kpPts = ds ? downsample(ds.kpSeries.filter(inWin), 80) : []
  const barW = kpPts.length
    ? Math.max(2, Math.min(18, (IW / kpPts.length) * 0.8))
    : 4

  // ---- IMF ----
  const bz = ds ? downsample(ds.bzSeries.filter(inWin), 500) : []
  const bt = ds ? downsample(ds.btSeries.filter(inWin), 500) : []
  const imfVals = [...bz, ...bt].map((p) => p.v)
  const vMin = Math.min(-5, ...imfVals)
  const vMax = Math.max(12, ...imfVals)
  const ysi = (v: number) => M.t + (1 - (v - vMin) / (vMax - vMin)) * IH
  const poly = (pts: Pt[]) =>
    pts.map((p) => `${xsi(p.t).toFixed(1)},${ysi(p.v).toFixed(1)}`).join(' ')

  const nowLine = (xs: (t: number) => number) => (
    <line
      x1={xs(now)}
      x2={xs(now)}
      y1={M.t}
      y2={M.t + IH}
      className="chart-now"
    />
  )
  const axis = (ticks: Tick[], xs: (t: number) => number) =>
    ticks.map((tk) => (
      <text
        key={tk.label}
        x={xs(tk.t)}
        y={CH - 8}
        className="chart-xlabel"
      >
        {tk.label}
      </text>
    ))

  return (
    <div className="weather-view">
      <div className="weather-inner">
        <header className="weather-header">
          <div>
            <h1 className="weather-title">Space Weather</h1>
            <p className="weather-sub">
              {demo ? 'Demo storm scenario' : 'Live SWPC feed'} · Kp +
              interplanetary magnetic field · times UTC
            </p>
          </div>
          {cur && g && (
            <div className="weather-stats">
              <div className="wstat" style={{ borderColor: g.color }}>
                <span className="wstat-label">Kp</span>
                <span className="wstat-value" style={{ color: g.color }}>
                  {cur.kp.toFixed(1)}
                </span>
                <span className="wstat-sub" style={{ color: g.color }}>
                  {g.label}
                </span>
              </div>
              <div className="wstat">
                <span className="wstat-label">Bz</span>
                <span
                  className="wstat-value"
                  style={{ color: cur.bzNt < 0 ? '#ff7a7a' : '#cdd5e6' }}
                >
                  {cur.bzNt.toFixed(1)}
                </span>
                <span className="wstat-sub">
                  nT {cur.bzNt < 0 ? '· south' : ''}
                </span>
              </div>
              <div className="wstat">
                <span className="wstat-label">Bt</span>
                <span className="wstat-value">{cur.btNt.toFixed(1)}</span>
                <span className="wstat-sub">nT</span>
              </div>
            </div>
          )}
        </header>

        {!ds && <p className="weather-empty">Loading space-weather data…</p>}

        {ds && (
          <>
            {/* Kp index */}
            <section className="chart-card">
              <div className="chart-head">
                <h2>Geomagnetic activity · Kp index</h2>
                <span className="chart-note">storm onset at Kp 5 (G1)</span>
              </div>
              <svg viewBox={`0 0 ${CW} ${CH}`} className="chart">
                {[0, 3, 6, 9].map((v) => (
                  <g key={v}>
                    <line
                      x1={M.l}
                      x2={M.l + IW}
                      y1={ysk(v)}
                      y2={ysk(v)}
                      className="chart-grid"
                    />
                    <text x={M.l - 8} y={ysk(v) + 3} className="chart-ylabel">
                      {v}
                    </text>
                  </g>
                ))}
                <line
                  x1={M.l}
                  x2={M.l + IW}
                  y1={ysk(5)}
                  y2={ysk(5)}
                  className="chart-threshold"
                />
                {kpPts.map((p, i) => (
                  <rect
                    key={i}
                    x={xsk(p.t) - barW / 2}
                    y={ysk(p.v)}
                    width={barW}
                    height={Math.max(0, ysk(0) - ysk(p.v))}
                    rx={1}
                    fill={gLevel(p.v).color}
                    opacity={p.t > now ? 0.5 : 0.95}
                  />
                ))}
                {nowLine(xsk)}
                {axis(kpTicks, xsk)}
              </svg>
            </section>

            {/* IMF Bz / Bt */}
            <section className="chart-card">
              <div className="chart-head">
                <h2>Interplanetary magnetic field</h2>
                <span className="chart-legend">
                  <i className="lg lg-bz" /> Bz (GSM)
                  <i className="lg lg-bt" /> Bt
                  <span className="lg-note">southward Bz = geoeffective</span>
                </span>
              </div>
              <svg viewBox={`0 0 ${CW} ${CH}`} className="chart">
                <rect
                  x={M.l}
                  y={ysi(0)}
                  width={IW}
                  height={Math.max(0, ysi(vMin) - ysi(0))}
                  className="chart-southband"
                />
                <line
                  x1={M.l}
                  x2={M.l + IW}
                  y1={ysi(0)}
                  y2={ysi(0)}
                  className="chart-zero"
                />
                <text x={M.l - 8} y={ysi(0) + 3} className="chart-ylabel">
                  0
                </text>
                <text x={M.l - 8} y={ysi(vMax) + 9} className="chart-ylabel">
                  {Math.round(vMax)}
                </text>
                <text x={M.l - 8} y={ysi(vMin) - 2} className="chart-ylabel">
                  {Math.round(vMin)}
                </text>
                {bt.length > 1 && (
                  <polyline points={poly(bt)} className="chart-line line-bt" />
                )}
                {bz.length > 1 && (
                  <polyline points={poly(bz)} className="chart-line line-bz" />
                )}
                {nowLine(xsi)}
                {axis(imfTicks, xsi)}
              </svg>
            </section>
          </>
        )}
      </div>
    </div>
  )
}
