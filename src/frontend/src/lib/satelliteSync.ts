import { geodeticAt, type SatRec } from './orbital'
import { supabase, warnNoSupabaseOnce } from './supabase'
import type { SatelliteEntry } from '../data/satellites'

/**
 * Mirrors the in-app satellite list into the Supabase `satellites` table.
 *
 * Each entry is mapped to a row (deriving everything we can from the TLE and
 * propagated state; fields the feed can't supply are left null) and upserted on
 * `external_id`, so re-adding the same real satellite updates its single row.
 */

const EARTH_RADIUS_KM = 6378.137 // SGP4 reference (xkmper)
/** Reference air-density constant tying SGP4's B* to a ballistic coefficient. */
const BSTAR_RHO0 = 0.1570 // kg/m² per Earth radius

/** satrec fields satellite.js doesn't surface on its public type. */
interface SatRecInternals {
  a: number // semi-major axis (Earth radii)
  ecco: number // eccentricity
  bstar: number // SGP4 drag term
  jdsatepoch: number // element-set epoch (Julian date, integer part)
  jdsatepochF?: number // fractional part (newer satellite.js)
}

function internals(satrec: SatRec): SatRecInternals {
  return satrec as unknown as SatRecInternals
}

/** Coarse orbit-regime classification from the mean semi-major axis + eccentricity. */
function orbitRegime(satrec: SatRec): string {
  const { a, ecco } = internals(satrec)
  const altKm = a * EARTH_RADIUS_KM - EARTH_RADIUS_KM
  if (!Number.isFinite(altKm)) return 'UNKNOWN'
  if (ecco > 0.25) return 'HEO' // eccentric (e.g. Molniya)
  if (altKm < 2000) return 'LEO'
  if (altKm < 35586) return 'MEO'
  if (altKm < 35986) return 'GEO'
  return 'HEO'
}

/** Element-set epoch as an ISO timestamp, derived from the satrec's Julian date. */
function tleEpochISO(satrec: SatRec): string | null {
  const { jdsatepoch, jdsatepochF } = internals(satrec)
  const jd = jdsatepoch + (jdsatepochF ?? 0)
  if (!Number.isFinite(jd) || jd <= 0) return null
  const d = new Date((jd - 2440587.5) * 86400000) // JD → Unix ms
  return Number.isNaN(d.getTime()) ? null : d.toISOString()
}

/**
 * Estimate the ballistic coefficient (kg/m²) from the TLE B* drag term:
 * B* = ρ0 / (2·BC) ⇒ BC = ρ0 / (2·B*). Null when B* is non-positive (no usable
 * drag info), which is common for high or station-kept orbits.
 */
function ballisticCoefficient(satrec: SatRec): number | null {
  const { bstar } = internals(satrec)
  if (!Number.isFinite(bstar) || bstar <= 0) return null
  return BSTAR_RHO0 / (2 * bstar)
}

export interface SatelliteRow {
  external_id: string
  norad_cat_id: number | null
  name: string
  operator: string | null
  country: string | null
  mission_class: string | null
  operational_status: string
  orbit_regime: string
  tle_line1: string
  tle_line2: string
  tle_epoch: string | null
  reference_epoch: string | null
  mass_kg: number | null
  cross_section_area_m2: number | null
  drag_coefficient: number
  ballistic_coefficient_kg_m2: number | null
  position_time: string
  latitude_deg: number | null
  longitude_deg: number | null
  altitude_km: number | null
  speed_km_s: number | null
  updated_at: string
}

/** Build the DB row for one satellite at the given (position) time. */
export function toSatelliteRow(entry: SatelliteEntry, date: Date): SatelliteRow {
  const geo = geodeticAt(entry.satrec, date)
  const iso = date.toISOString()
  return {
    external_id: entry.id,
    norad_cat_id: entry.noradId ?? null,
    name: entry.name,
    operator: null,
    country: null,
    mission_class: null,
    operational_status: 'active',
    orbit_regime: orbitRegime(entry.satrec),
    tle_line1: entry.tle.line1,
    tle_line2: entry.tle.line2,
    tle_epoch: tleEpochISO(entry.satrec),
    // Reference epoch for the stored state = the time we sampled the position.
    reference_epoch: iso,
    mass_kg: null,
    cross_section_area_m2: null,
    drag_coefficient: 2.2,
    ballistic_coefficient_kg_m2: ballisticCoefficient(entry.satrec),
    position_time: iso,
    latitude_deg: geo?.latitudeDeg ?? null,
    longitude_deg: geo?.longitudeDeg ?? null,
    altitude_km: geo?.altitudeKm ?? null,
    speed_km_s: geo?.speedKmS ?? null,
    updated_at: iso,
  }
}

/**
 * Upsert the given satellites into Supabase (positions sampled at `date`).
 * No-ops gracefully when Supabase isn't configured. Errored entries are skipped.
 */
export async function syncSatellites(
  entries: SatelliteEntry[],
  date: Date,
): Promise<void> {
  if (!supabase) {
    warnNoSupabaseOnce()
    return
  }
  const rows = entries.filter((e) => !e.error).map((e) => toSatelliteRow(e, date))
  if (rows.length === 0) return
  const { error } = await supabase
    .from('satellites')
    .upsert(rows, { onConflict: 'external_id' })
  if (error) {
    console.error('[supabase] satellite sync failed:', error.message)
  }
}
