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
