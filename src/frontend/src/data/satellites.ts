import { parseTle, type SatRec } from '../lib/orbital'

/**
 * A satellite is defined by:
 *  - `description`: what the model/object is (free text shown in the HUD)
 *  - its TLE (`tle`): a two-line element set that encodes BOTH the current
 *    location and the full trajectory — satellite.js derives position + orbit.
 *
 * To add a satellite, append an entry to the SATELLITES array below (or call
 * `defineSatellite(...)` and push it). TLEs are widely available from
 * CelesTrak (https://celestrak.org) and NORAD.
 */
/**
 * Collision / threat status surfaced in the HUD:
 *  - `safe`     (green)  — nothing of concern
 *  - `caution`  (yellow) — a tracked object worth watching
 *  - `critical` (red)    — an imminent close approach
 *
 * Placeholder for now; will be derived from a real conjunction feed later.
 */
export type DangerLevel = 'safe' | 'caution' | 'critical'

/**
 * How a satellite's orbital data is sourced:
 *  - `builtin`     — bundled sample TLE (static).
 *  - `theoretical` — user-entered TLE (static, what-if trajectory).
 *  - `real`        — looked up from the live TLE API and refreshed periodically.
 */
export type SatelliteKind = 'builtin' | 'theoretical' | 'real'

export interface SatelliteConfig {
  id: string
  /** Display name, e.g. "ISS (ZARYA)". */
  name: string
  /** What this satellite model is — purpose, operator, anything useful. */
  description: string
  /** Two-line element set. */
  tle: { line1: string; line2: string }
  /** Marker / orbit colour (any CSS/three colour string). */
  color?: string
  /** Current threat status. Defaults to `safe` when omitted (placeholder). */
  danger?: DangerLevel
  /** Data source. Defaults to `builtin` when omitted. */
  kind?: SatelliteKind
  /** NORAD catalog number — present for `real` satellites; used to refresh. */
  noradId?: number
  /** Element-set epoch of the last fetch (ISO) — present for `real` satellites. */
  updatedAt?: string
  /** Optional GLB model. If omitted, a glowing dot marker is used. */
  model?: {
    /** Path under /public, e.g. "/models/iss.glb". */
    url: string
    /** Largest bounding-box dimension in scene units (visual size, not physical). */
    size?: number
  }
}

/** A SatelliteConfig with its TLE parsed into a ready-to-propagate satrec. */
export interface SatelliteEntry extends SatelliteConfig {
  satrec: SatRec
  /** Set when the TLE failed to parse; the satellite is skipped if so. */
  error?: string
}

const DEFAULT_COLOR = '#4fd1ff'

/** Parse a config entry's TLE, attaching a `satrec` (or an `error`). */
export function defineSatellite(config: SatelliteConfig): SatelliteEntry {
  try {
    const satrec = parseTle(config.tle.line1, config.tle.line2)
    return { ...config, color: config.color ?? DEFAULT_COLOR, satrec }
  } catch (e) {
    return {
      ...config,
      color: config.color ?? DEFAULT_COLOR,
      satrec: undefined as unknown as SatRec,
      error: e instanceof Error ? e.message : String(e),
    }
  }
}

/** Default GLB model given to user-added satellites. */
export const DEFAULT_SATELLITE_MODEL = {
  url: '/models/satellite-generic.glb',
  size: 0.1,
}

/**
 * Build a *theoretical* satellite from a user-supplied name and TLE (the two
 * element lines), using the default model. Returns an entry with `error` set if
 * the TLE can't be parsed (the caller should surface that to the user). The id
 * is generated so user satellites can't collide with the built-ins or each other.
 */
export function createUserSatellite(
  name: string,
  line1: string,
  line2: string,
): SatelliteEntry {
  const trimmed = name.trim() || 'Unnamed satellite'
  return defineSatellite({
    id: `theo-${crypto.randomUUID()}`,
    name: trimmed,
    description: `Theoretical satellite "${trimmed}" (user-entered trajectory).`,
    danger: 'safe',
    kind: 'theoretical',
    model: DEFAULT_SATELLITE_MODEL,
    tle: { line1, line2 },
  })
}

/**
 * Build a *real* satellite from a live TLE-API record. Keyed by NORAD id so its
 * elements can be refreshed; uses the default model. The id is derived from the
 * NORAD number so re-adding the same satellite is detectable.
 */
export function createRealSatellite(record: {
  satelliteId: number
  name: string
  line1: string
  line2: string
  date: string
}): SatelliteEntry {
  return defineSatellite({
    id: `real-${record.satelliteId}`,
    name: record.name,
    description: `Live satellite · NORAD ${record.satelliteId}.`,
    danger: 'safe',
    kind: 'real',
    noradId: record.satelliteId,
    updatedAt: record.date,
    model: DEFAULT_SATELLITE_MODEL,
    tle: { line1: record.line1, line2: record.line2 },
  })
}

/**
 * Return a copy of `entry` with refreshed element lines (re-parsed satrec),
 * preserving its identity (id, name, colour, kind, …). Used by the periodic
 * refresh of real satellites. Strips any prior satrec/error before re-parsing.
 */
export function updateSatelliteTle(
  entry: SatelliteEntry,
  line1: string,
  line2: string,
  updatedAt?: string,
): SatelliteEntry {
  const { satrec: _satrec, error: _error, ...config } = entry
  return defineSatellite({
    ...config,
    tle: { line1, line2 },
    updatedAt: updatedAt ?? config.updatedAt,
  })
}

/**
 * Add satellites here, one by one. Each needs a description and a TLE.
 * (TLEs below are sample/illustrative and will drift over time — swap in fresh
 * ones from CelesTrak when you want accurate live positions.)
 */
const SATELLITE_CONFIGS: SatelliteConfig[] = [
  {
    id: 'iss',
    name: 'ISS (ZARYA)',
    description:
      'International Space Station — crewed low-Earth-orbit laboratory at ~420 km, ~51.6° inclination.',
    color: '#ffd24f',
    danger: 'safe', // placeholder threat status
    model: { url: '/models/iss.glb', size: 0.14 },
    tle: {
      line1: '1 25544U 98067A   24079.07757601  .00016717  00000-0  30074-3 0  9993',
      line2: '2 25544  51.6413 208.6424 0004604  73.7383  19.4396 15.50328171441162',
    },
  },
  {
    id: 'hst',
    name: 'Hubble Space Telescope',
    description:
      'Hubble Space Telescope — optical/UV observatory in a ~540 km, 28.5° inclination orbit.',
    color: '#ff7ad9',
    danger: 'safe', // placeholder threat status
    model: { url: '/models/hubble.glb', size: 0.1 },
    tle: {
      line1: '1 20580U 90037B   24079.16835648  .00001263  00000-0  64960-4 0  9994',
      line2: '2 20580  28.4698  13.8302 0002595 268.0935 188.5904 15.09299061635741',
    },
  },
  {
    id: 'gps',
    name: 'GPS BIIR-2 (PRN 13)',
    description:
      'GPS navigation satellite in semi-synchronous medium Earth orbit (~20 200 km, 55° inclination).',
    color: '#7affa1',
    danger: 'safe', // placeholder threat status
    model: { url: '/models/satellite-generic.glb', size: 0.1 },
    tle: {
      line1: '1 24876U 97035A   24078.51713874 -.00000056  00000-0  00000-0 0  9995',
      line2: '2 24876  55.5497  53.3534 0056676  54.8650 305.6755  2.00563367196066',
    },
  },
]

export const SATELLITES: SatelliteEntry[] = SATELLITE_CONFIGS.map(defineSatellite)
