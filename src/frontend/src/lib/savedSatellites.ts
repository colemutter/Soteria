import { apiRequest } from './apiClient'
import {
  defineSatellite,
  DEFAULT_SATELLITE_MODEL,
  type SatelliteEntry,
} from '../data/satellites'

/**
 * Browser-side memory of the satellites a user has added. We cache just their
 * external ids (the `satellites` table key, e.g. `real-25544` / `theo-<uuid>`)
 * in localStorage so the local UI can remember user intent across reloads.
 * Satellite DB reads now go through the backend API instead of Supabase directly.
 */

const STORAGE_KEY = 'soteria.addedSatellites'

/** The cached list of added-satellite external ids. */
export function getRememberedIds(): string[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    const arr = raw ? JSON.parse(raw) : []
    return Array.isArray(arr) ? arr.filter((x) => typeof x === 'string') : []
  } catch {
    return []
  }
}

/** Remember an added satellite by its external id (deduped). */
export function rememberSatellite(id: string): void {
  try {
    const ids = getRememberedIds()
    if (!ids.includes(id)) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify([...ids, id]))
    }
  } catch {
    /* storage disabled / over quota — non-fatal */
  }
}

/** Forget a satellite (e.g. if it was removed). */
export function forgetSatellite(id: string): void {
  try {
    const ids = getRememberedIds().filter((x) => x !== id)
    localStorage.setItem(STORAGE_KEY, JSON.stringify(ids))
  } catch {
    /* non-fatal */
  }
}

interface SatelliteRowLite {
  external_id: string
  norad_cat_id: number | null
  name: string
  tle_line1: string | null
  tle_line2: string | null
  tle_epoch: string | null
}

interface SatelliteListResponse {
  satellites: SatelliteRowLite[]
}

/** Rebuild a satellite entry from its stored DB row. */
function rowToEntry(row: SatelliteRowLite): SatelliteEntry {
  const id = row.external_id
  const kind = id.startsWith('real-') ? 'real' : 'theoretical'
  const noradId = row.norad_cat_id ?? undefined
  return defineSatellite({
    id,
    name: row.name,
    description:
      kind === 'real'
        ? `Live satellite · NORAD ${noradId ?? '—'}.`
        : `Theoretical satellite "${row.name}" (user-entered trajectory).`,
    danger: 'safe',
    kind,
    noradId,
    updatedAt: row.tle_epoch ?? undefined,
    model: DEFAULT_SATELLITE_MODEL,
    tle: { line1: row.tle_line1 ?? '', line2: row.tle_line2 ?? '' },
  })
}

/**
 * Load persisted satellites through the backend API and rebuild entries.
 * Returns [] if the backend API isn't configured or the query fails.
 */
export async function fetchStoredSatellites(): Promise<SatelliteEntry[]> {
  try {
    const response = await apiRequest<SatelliteListResponse>('/api/satellites?limit=200')
    if (!response) return []
    return response.satellites
      .map(rowToEntry)
      .filter((e) => !e.error && e.tle.line1 && e.tle.line2)
  } catch (error) {
    console.error(
      '[api] satellite load failed:',
      error instanceof Error ? error.message : error,
    )
    return []
  }
}

export async function fetchSavedSatellites(): Promise<SatelliteEntry[]> {
  const rememberedIds = new Set(getRememberedIds())
  if (rememberedIds.size === 0) return []
  const stored = await fetchStoredSatellites()
  return stored.filter((entry) => rememberedIds.has(entry.id))
}

export async function fetchAllDbSatellites(): Promise<SatelliteEntry[]> {
  return fetchStoredSatellites()
}
