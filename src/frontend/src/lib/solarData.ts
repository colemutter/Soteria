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
export type Series = { t: number; v: number }[]

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

/**
 * Resample `s` every `stepMs` across [a, b], linearly interpolating between real
 * samples to fill gaps (e.g. the 3-hourly Kp forecast → a smooth curve). The
 * span is clipped to the series' actual data range, so we never extrapolate past
 * the first/last sample: a window that sits entirely beyond the data (e.g. a
 * forward window over the observation-only IMF feed) returns []. Always includes
 * the right edge so the resampled series spans the full available range.
 */
export function resampleSeries(
  s: Series,
  a: number,
  b: number,
  stepMs: number,
): Series {
  if (s.length === 0) return []
  const from = Math.max(a, s[0].t)
  const to = Math.min(b, s[s.length - 1].t)
  if (to < from) return []
  const out: Series = []
  for (let t = from; t < to; t += stepMs) out.push({ t, v: interp(s, t, s[0].v) })
  out.push({ t: to, v: interp(s, to, s[0].v) })
  return out
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
const PAGE = 1000 // PostgREST caps each request at 1000 rows
// The real feed's Bz/Bt both come from this SWPC endpoint, which is indexed
// (endpoint, valid_start). Filtering by endpoint is ~20× faster than by
// product_type (which can't use the index) and returns exactly Bz + Bt.
const MAG_ENDPOINT = '/json/rtsw/rtsw_mag_1m.json'

/**
 * Fetch the magnetic-field rows newest-first. With `full`, page through the
 * whole high-cadence series in parallel (the API caps at 1000 rows/request) so
 * a chart can span all the hours that exist; otherwise just the latest page
 * (enough for the layers, which only sample near "now").
 */
async function fetchMagRows(
  table: string,
  full: boolean,
): Promise<ForecastRow[]> {
  if (!supabase) return []
  const isDemo = table.endsWith('_demo')
  const page = (from: number) => {
    const base = supabase!.from(table).select('product_type,value,valid_start')
    const filtered = isDemo
      ? base.in('product_type', ['solar_wind_mag_bz_gsm', 'solar_wind_mag_bt'])
      : base.eq('endpoint', MAG_ENDPOINT)
    return filtered
      .order('valid_start', { ascending: false })
      .range(from, from + PAGE - 1)
  }
  if (!full) {
    const { data } = await page(0)
    return (data ?? []) as ForecastRow[]
  }
  // 14 pages ≈ 14k rows covers the current IMF history with margin; empty pages
  // beyond the data just return nothing. Parallel = one round-trip of latency.
  const pages = await Promise.all(
    Array.from({ length: 14 }, (_, p) => page(p * PAGE)),
  )
  const out: ForecastRow[] = []
  for (const { data, error } of pages) {
    if (!error && data) out.push(...(data as ForecastRow[]))
  }
  return out
}

async function fetchFromTable(
  table: string,
  full = false,
): Promise<SolarDataset | null> {
  if (!supabase) return null
  // Query Kp and the magnetic field separately, NEWEST-FIRST: the IMF products
  // are high-cadence, so a single ascending+limit query would return the oldest
  // rows and drop both the recent observations and the Kp forecast.
  const [kpRes, magRows] = await Promise.all([
    supabase
      .from(table)
      .select('product_type,value,valid_start')
      .in('product_type', ['kp_history', 'kp_forecast'])
      .order('valid_start', { ascending: false })
      .limit(1500),
    fetchMagRows(table, full),
  ])
  if (kpRes.error) return null
  const kpRows = (kpRes.data ?? []) as ForecastRow[]
  // kp_history + kp_forecast merge into one Kp series.
  const kp = buildSeries(kpRows, 'kp_history').concat(
    buildSeries(kpRows, 'kp_forecast'),
  )
  kp.sort((a, b) => a.t - b.t)
  return {
    kpSeries: kp,
    bzSeries: buildSeries(magRows, 'solar_wind_mag_bz_gsm'),
    btSeries: buildSeries(magRows, 'solar_wind_mag_bt'),
  }
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
  const ds = await fetchFromTable('swpc_forecast_records_demo', true)
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

const cache = new Map<string, { ds: SolarDataset; at: number }>()
const inflight = new Map<string, Promise<SolarDataset | null>>()

/**
 * Cached accessor shared across layers and the weather charts. `demo` selects
 * the synthetic escalating-storm dataset; `full` pages through the entire IMF
 * history (for the charts) instead of just the latest page (for the layers).
 */
export async function getSolarDataset(
  demo = false,
  full = false,
  maxAgeMs = 5 * 60 * 1000,
): Promise<SolarDataset | null> {
  const key = `${demo ? 'demo' : 'real'}:${full ? 'full' : 'light'}`
  const c = cache.get(key)
  if (c && Date.now() - c.at < maxAgeMs) return c.ds
  const existing = inflight.get(key)
  if (existing) return existing
  const promise = (async () => {
    const ds = demo
      ? await fetchDemoDataset()
      : await fetchFromTable('swpc_forecast_records', full)
    if (ds) cache.set(key, { ds, at: Date.now() })
    inflight.delete(key)
    return ds
  })()
  inflight.set(key, promise)
  return promise
}
