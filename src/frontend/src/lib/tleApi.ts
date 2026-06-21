/**
 * Live TLE lookup via the public TLE API (https://tle.ivanstanojevic.me).
 *
 * Chosen because it's free, needs no API key, returns clean JSON, and — crucially
 * for a browser app — sends `Access-Control-Allow-Origin: *`, so we can call it
 * directly from the frontend with no backend proxy. It mirrors CelesTrak/
 * Space-Track element sets, refreshed on roughly a daily cadence upstream; we
 * re-fetch periodically so a satellite's orbit stays current.
 */

const BASE = 'https://tle.ivanstanojevic.me/api/tle'

export interface TleRecord {
  /** NORAD catalog number — stable id used to re-fetch fresh elements. */
  satelliteId: number
  name: string
  line1: string
  line2: string
  /** ISO timestamp of the element set epoch (when these elements were issued). */
  date: string
}

function toRecord(m: {
  satelliteId: number
  name: string
  line1: string
  line2: string
  date: string
}): TleRecord {
  return {
    satelliteId: m.satelliteId,
    name: m.name,
    line1: m.line1,
    line2: m.line2,
    date: m.date,
  }
}

/** Search satellites by name (e.g. "hubble", "starlink"). Returns best matches. */
export async function searchSatellites(query: string): Promise<TleRecord[]> {
  const res = await fetch(`${BASE}/?search=${encodeURIComponent(query)}`)
  if (!res.ok) throw new Error(`Lookup failed (HTTP ${res.status})`)
  const data = (await res.json()) as { member?: TleRecord[] }
  return (data.member ?? []).map(toRecord)
}

/** Fetch the current element set for a specific NORAD catalog number. */
export async function fetchTleById(id: number): Promise<TleRecord> {
  const res = await fetch(`${BASE}/${id}`)
  if (!res.ok) throw new Error(`Fetch failed (HTTP ${res.status})`)
  return toRecord(await res.json())
}
