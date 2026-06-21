import { apiRequest } from './apiClient'
import {
  defineSatellite,
  DEFAULT_SATELLITE_MODEL,
  type SatelliteEntry,
} from '../data/satellites'

/**
 * Browser-side memory of the satellites a user has added. We cache their
 * external ids plus enough row data to rebuild them if a reload happens before
 * backend persistence is available.
 * Satellite DB reads now go through the backend API instead of Supabase directly.
 */

const STORAGE_KEY = 'soteria.addedSatellites'
const ROW_STORAGE_KEY = 'soteria.cachedSatelliteRows'

interface SatelliteRowLite {
  external_id: string
  norad_cat_id: number | null
  name: string
  tle_line1: string | null
  tle_line2: string | null
  tle_epoch: string | null
}

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

function normalizeRow(value: unknown): SatelliteRowLite | null {
  if (!value || typeof value !== 'object') return null
  const row = value as Partial<SatelliteRowLite>
  if (typeof row.external_id !== 'string' || typeof row.name !== 'string') {
    return null
  }
  return {
    external_id: row.external_id,
    norad_cat_id:
      typeof row.norad_cat_id === 'number' ? row.norad_cat_id : null,
    name: row.name,
    tle_line1: typeof row.tle_line1 === 'string' ? row.tle_line1 : null,
    tle_line2: typeof row.tle_line2 === 'string' ? row.tle_line2 : null,
    tle_epoch: typeof row.tle_epoch === 'string' ? row.tle_epoch : null,
  }
}

/** Cached satellite rows, used as a browser fallback while the DB is unavailable. */
export function getCachedSatelliteRows(): SatelliteRowLite[] {
  try {
    const raw = localStorage.getItem(ROW_STORAGE_KEY)
    const arr = raw ? JSON.parse(raw) : []
    return Array.isArray(arr)
      ? arr.map(normalizeRow).filter((row) => row !== null)
      : []
  } catch {
    return []
  }
}

/** Cache enough row data to rebuild satellites on reload, even before DB sync finishes. */
export function rememberSatelliteRows(rows: SatelliteRowLite[]): void {
  try {
    const byId = new Map(
      getCachedSatelliteRows().map((row) => [row.external_id, row]),
    )
    rows.map(normalizeRow).forEach((row) => {
      if (row) byId.set(row.external_id, row)
    })
    localStorage.setItem(ROW_STORAGE_KEY, JSON.stringify([...byId.values()]))
  } catch {
    /* storage disabled / over quota — non-fatal */
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
    const rows = getCachedSatelliteRows().filter((row) => row.external_id !== id)
    localStorage.setItem(ROW_STORAGE_KEY, JSON.stringify(rows))
  } catch {
    /* non-fatal */
  }
}

interface SatelliteListResponse {
  satellites: SatelliteRowLite[]
}

function mergeRows(
  cachedRows: SatelliteRowLite[],
  dbRows: SatelliteRowLite[],
): SatelliteRowLite[] {
  const byId = new Map(cachedRows.map((row) => [row.external_id, row]))
  dbRows.map(normalizeRow).forEach((dbRow) => {
    if (!dbRow) return
    const cachedRow = byId.get(dbRow.external_id)
    byId.set(dbRow.external_id, {
      ...cachedRow,
      ...dbRow,
      tle_line1: dbRow.tle_line1 ?? cachedRow?.tle_line1 ?? null,
      tle_line2: dbRow.tle_line2 ?? cachedRow?.tle_line2 ?? null,
      tle_epoch: dbRow.tle_epoch ?? cachedRow?.tle_epoch ?? null,
    })
  })
  return [...byId.values()]
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
 * Load persisted satellites through the backend API and rebuild entries. Cached
 * rows keep a reload from losing newly-added satellites if the DB request is
 * disabled, fails, or has not completed yet.
 */
export async function fetchStoredSatellites(): Promise<SatelliteEntry[]> {
  const cachedRows = getCachedSatelliteRows()
  let rows = cachedRows
  try {
    const response = await apiRequest<SatelliteListResponse>('/api/satellites?limit=200')
    if (response) {
      rows = mergeRows(cachedRows, response.satellites)
      rememberSatelliteRows(rows)
    }
  } catch (error) {
    console.error(
      '[api] satellite load failed:',
      error instanceof Error ? error.message : error,
    )
  }
  return rows.map(rowToEntry).filter((e) => !e.error && e.tle.line1 && e.tle.line2)
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
