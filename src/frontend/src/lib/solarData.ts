import { supabase } from './supabase'

/**
 * Space-weather drivers read from the SWPC tables in Supabase and used to drive
 * the solar-wind and geomagnetic (auroral) visualizations:
 *   - kp:   geomagnetic activity index (0–9)        → wind speed, aurora extent
 *   - bzNt: IMF Bz, GSM (nT, negative = southward)  → storminess / colour
 *   - btNt: total IMF magnitude (nT)                → density / brightness
 *
 * All three are time-resolved so conditions can be read at any instant — past,
 * present, or future (forecast / demo) — as the timeline is scrubbed.
 */
export interface SolarConditions {
  kp: number
  bzNt: number
  btNt: number
  observedAt: string | null
}

/** Quiet-Sun fallback used before the first fetch (or if the DB is unreachable). */
export const DEFAULT_CONDITIONS: SolarConditions = {
  kp: 0,
  bzNt: 5,
  btNt: 5,
  observedAt: null,
}

/** A driver's value over time: { t: ms epoch, v: value }, sorted ascending. */
type Series = { t: number; v: number }[]

export interface SolarDataset {
  kpSeries: Series
  bzSeries: Series
  btSeries: Series
}

interface ForecastRow {
  product_type: string
  value: number | null
  valid_start: string | null
}

/** Build a sorted, de-duplicated series from rows of a single product. */
function buildSeries(rows: ForecastRow[], product: string): Series {
  const byTime = new Map<number, number>()
  for (const r of rows) {
    if (r.product_type !== product || r.value == null || !r.valid_start) continue
    byTime.set(new Date(r.valid_start).getTime(), r.value)
  }
  return [...byTime.entries()]
    .map(([t, v]) => ({ t, v }))
    .sort((a, b) => a.t - b.t)
}

/** Linearly interpolate a series at time `t`, clamping at the ends. */
function interp(s: Series, t: number, fallback: number): number {
  if (s.length === 0) return fallback
  if (s.length === 1 || t <= s[0].t) return s[0].v
  if (t >= s[s.length - 1].t) return s[s.length - 1].v
  let lo = 0
  let hi = s.length - 1
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1
    if (s[mid].t <= t) lo = mid
    else hi = mid
  }
  const a = s[lo]
  const b = s[hi]
  const f = b.t === a.t ? 0 : (t - a.t) / (b.t - a.t)
  return a.v + (b.v - a.v) * f
}

/** Conditions at a given instant, interpolated from each driver's series. */
export function conditionsAt(ds: SolarDataset, date: Date): SolarConditions {
  const t = date.getTime()
  return {
    kp: interp(ds.kpSeries, t, DEFAULT_CONDITIONS.kp),
    bzNt: interp(ds.bzSeries, t, DEFAULT_CONDITIONS.bzNt),
    btNt: interp(ds.btSeries, t, DEFAULT_CONDITIONS.btNt),
    observedAt: null,
  }
}

/** Pull all three driver series from one of the forecast tables. */
async function fetchFromTable(table: string): Promise<SolarDataset | null> {
  if (!supabase) return null
  const { data, error } = await supabase
    .from(table)
    .select('product_type,value,valid_start')
    .in('product_type', [
      'kp_history',
      'kp_forecast',
      'solar_wind_mag_bz_gsm',
      'solar_wind_mag_bt',
    ])
    .order('valid_start', { ascending: true })
    .limit(2000)
  if (error || !data) return null
  const rows = data as ForecastRow[]
  // kp_history + kp_forecast merge into one Kp series.
  const kp = buildSeries(rows, 'kp_history').concat(
    buildSeries(rows, 'kp_forecast'),
  )
  kp.sort((a, b) => a.t - b.t)
  return {
    kpSeries: kp,
    bzSeries: buildSeries(rows, 'solar_wind_mag_bz_gsm'),
    btSeries: buildSeries(rows, 'solar_wind_mag_bt'),
  }
}

/** Live data from the real forecast table. */
function fetchSolarDataset(): Promise<SolarDataset | null> {
  return fetchFromTable('swpc_forecast_records')
}

/** Shift a series so its earliest sample lands at `anchor` (ms). */
function anchorSeries(s: Series, shift: number): Series {
  return s.map((p) => ({ t: p.t + shift, v: p.v }))
}

/**
 * Client-side copy of the demo storm profile (matches the SQL in the
 * `swpc_forecast_records_demo` migration). Used as a fallback when that table
 * hasn't been created/populated yet, so the demo still works. Anchored to now.
 */
function generateDemoSeries(): SolarDataset {
  const now = Date.now()
  const HOUR = 3600 * 1000
  const kpSeries: Series = []
  const bzSeries: Series = []
  const btSeries: Series = []
  for (let h = 0; h <= 48; h++) {
    const t = now + h * HOUR
    const ramp = Math.max(0, h - 24) / 24 // 0 first day, → 1 over the second
    kpSeries.push({ t, v: Math.min(9, 2 + 7 * ramp) })
    bzSeries.push({ t, v: 3 - 31 * ramp })
    btSeries.push({ t, v: 5 + 30 * ramp })
  }
  return { kpSeries, bzSeries, btSeries }
}

/** Demo data from the demo table, re-anchored to start "now"; falls back to the
 * generated profile if the table is missing/empty. */
async function fetchDemoDataset(): Promise<SolarDataset> {
  const ds = await fetchFromTable('swpc_forecast_records_demo')
  const all = ds ? [...ds.kpSeries, ...ds.bzSeries, ...ds.btSeries] : []
  if (!ds || all.length === 0) return generateDemoSeries()
  const minT = Math.min(...all.map((p) => p.t))
  const shift = Date.now() - minT
  return {
    kpSeries: anchorSeries(ds.kpSeries, shift),
    bzSeries: anchorSeries(ds.bzSeries, shift),
    btSeries: anchorSeries(ds.btSeries, shift),
  }
}

const cache: Record<'real' | 'demo', { ds: SolarDataset; at: number } | null> =
  { real: null, demo: null }
const inflight: Record<'real' | 'demo', Promise<SolarDataset | null> | null> = {
  real: null,
  demo: null,
}

/**
 * Cached accessor shared across layers. `demo` selects the synthetic escalating
 * storm dataset (from the demo table) instead of the live feed.
 */
export async function getSolarDataset(
  demo = false,
  maxAgeMs = 5 * 60 * 1000,
): Promise<SolarDataset | null> {
  const key = demo ? 'demo' : 'real'
  const c = cache[key]
  if (c && Date.now() - c.at < maxAgeMs) return c.ds
  if (inflight[key]) return inflight[key]
  inflight[key] = (async () => {
    const ds = demo ? await fetchDemoDataset() : await fetchSolarDataset()
    if (ds) cache[key] = { ds, at: Date.now() }
    inflight[key] = null
    return ds
  })()
  return inflight[key]
}
