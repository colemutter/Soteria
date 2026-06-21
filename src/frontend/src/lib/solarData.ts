import { supabase } from './supabase'

/**
 * Current space-weather drivers, read from the SWPC tables in Supabase and used
 * to drive the solar-wind particle visualization.
 *
 * The feed doesn't carry plasma speed/density, so we use the magnetic-field and
 * geomagnetic-index products that are present:
 *   - kp:   geomagnetic activity index (0–9)               → flow speed / intensity
 *   - bzNt: IMF Bz, GSM (nT, negative = southward)         → storminess / colour
 *   - btNt: total IMF magnitude (nT)                       → density / brightness
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

const PRODUCTS = ['kp_history', 'solar_wind_mag_bz_gsm', 'solar_wind_mag_bt']

interface ForecastRow {
  product_type: string
  value: number | null
  valid_start: string | null
}

/**
 * Fetch the latest observed value of each driver. Returns null if Supabase isn't
 * configured or the query fails (callers fall back to DEFAULT_CONDITIONS).
 */
export async function fetchSolarConditions(): Promise<SolarConditions | null> {
  if (!supabase) return null
  const { data, error } = await supabase
    .from('swpc_forecast_records')
    .select('product_type,value,valid_start')
    .in('product_type', PRODUCTS)
    .order('valid_start', { ascending: false })
    .limit(150)
  if (error || !data) return null
  const rows = data as ForecastRow[]
  // Rows are newest-first, so the first match per product is the latest value.
  const latest = (p: string) =>
    rows.find((r) => r.product_type === p && r.value != null)
  const kp = latest('kp_history')
  const bz = latest('solar_wind_mag_bz_gsm')
  const bt = latest('solar_wind_mag_bt')
  return {
    kp: kp?.value ?? DEFAULT_CONDITIONS.kp,
    bzNt: bz?.value ?? DEFAULT_CONDITIONS.bzNt,
    btNt: bt?.value ?? DEFAULT_CONDITIONS.btNt,
    observedAt: kp?.valid_start ?? bz?.valid_start ?? bt?.valid_start ?? null,
  }
}

/**
 * A time-resolved view of the solar drivers, so conditions can be read at any
 * instant — including the future (via the Kp forecast) when scrubbing the
 * timeline. Bz/Bt have no forecast in the feed, so we carry their latest
 * observed values and hold them constant across time.
 */
export interface SolarDataset {
  /** Kp over time (observed history + forecast), sorted ascending by `t` (ms). */
  kpSeries: { t: number; kp: number }[]
  bzNt: number
  btNt: number
}

/** Fetch the Kp history+forecast series and the latest Bz/Bt. */
export async function fetchSolarDataset(): Promise<SolarDataset | null> {
  if (!supabase) return null
  const [kpRes, magRes] = await Promise.all([
    supabase
      .from('swpc_forecast_records')
      .select('value,valid_start')
      .in('product_type', ['kp_history', 'kp_forecast'])
      .order('valid_start', { ascending: true })
      .limit(800),
    supabase
      .from('swpc_forecast_records')
      .select('product_type,value,valid_start')
      .in('product_type', ['solar_wind_mag_bz_gsm', 'solar_wind_mag_bt'])
      .order('valid_start', { ascending: false })
      .limit(20),
  ])
  if (kpRes.error || magRes.error) return null

  // Build the Kp series (dedupe to one value per timestamp, last wins).
  const byTime = new Map<number, number>()
  for (const r of (kpRes.data ?? []) as ForecastRow[]) {
    if (r.value == null || !r.valid_start) continue
    byTime.set(new Date(r.valid_start).getTime(), r.value)
  }
  const kpSeries = [...byTime.entries()]
    .map(([t, kp]) => ({ t, kp }))
    .sort((a, b) => a.t - b.t)

  const mag = (magRes.data ?? []) as ForecastRow[]
  const latestMag = (p: string) =>
    mag.find((r) => r.product_type === p && r.value != null)?.value

  return {
    kpSeries,
    bzNt: latestMag('solar_wind_mag_bz_gsm') ?? DEFAULT_CONDITIONS.bzNt,
    btNt: latestMag('solar_wind_mag_bt') ?? DEFAULT_CONDITIONS.btNt,
  }
}

let cachedDataset: { ds: SolarDataset; at: number } | null = null
let inflight: Promise<SolarDataset | null> | null = null

/**
 * Cached accessor for the solar dataset, shared across layers (solar wind +
 * geomagnetic) so they don't each issue the same query. Re-fetches when the
 * cache is older than `maxAgeMs`.
 */
export async function getSolarDataset(
  maxAgeMs = 5 * 60 * 1000,
): Promise<SolarDataset | null> {
  if (cachedDataset && Date.now() - cachedDataset.at < maxAgeMs) {
    return cachedDataset.ds
  }
  if (inflight) return inflight
  inflight = (async () => {
    const ds = await fetchSolarDataset()
    if (ds) cachedDataset = { ds, at: Date.now() }
    inflight = null
    return ds
  })()
  return inflight
}

/** Conditions at a given instant: Kp interpolated from the series, Bz/Bt held. */
export function conditionsAt(ds: SolarDataset, date: Date): SolarConditions {
  const t = date.getTime()
  const s = ds.kpSeries
  let kp = DEFAULT_CONDITIONS.kp
  if (s.length === 1) {
    kp = s[0].kp
  } else if (s.length > 1) {
    if (t <= s[0].t) kp = s[0].kp
    else if (t >= s[s.length - 1].t) kp = s[s.length - 1].kp
    else {
      // Binary search for the bracketing interval, then linearly interpolate.
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
      kp = a.kp + (b.kp - a.kp) * f
    }
  }
  return { kp, bzNt: ds.bzNt, btNt: ds.btNt, observedAt: null }
}
