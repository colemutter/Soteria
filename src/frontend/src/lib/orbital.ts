import * as satellite from 'satellite.js'
import { Vector3 } from 'three'

/**
 * Orbital math helpers.
 *
 * Frame choice: we propagate satellites in the ECI (Earth-Centered Inertial)
 * frame and ROTATE THE EARTH MESH by GMST so that geography stays correct.
 * Working in the inertial frame means a satellite's path over one orbital
 * period is a clean, closed ellipse (the ground track precesses, but the orbit
 * itself doesn't smear), which looks far better than an earth-fixed spiral.
 *
 * Distances from satellite.js are in kilometres. We scale so that the Earth's
 * radius is SCENE_EARTH_RADIUS scene units.
 */

export const EARTH_RADIUS_KM = 6371
export const SCENE_EARTH_RADIUS = 2.5
export const KM_TO_SCENE = SCENE_EARTH_RADIUS / EARTH_RADIUS_KM

/**
 * Texture alignment offset (radians) applied to the Earth mesh rotation on top
 * of GMST so the equirectangular day texture's Greenwich meridian lines up with
 * the inertial frame. Tune if coastlines look rotated.
 */
export const TEXTURE_LON_OFFSET = 0

export type SatRec = ReturnType<typeof satellite.twoline2satrec>

export interface GeodeticInfo {
  latitudeDeg: number
  longitudeDeg: number
  altitudeKm: number
  speedKmS: number
}

/** Parse a TLE into a propagatable satrec. Throws if the TLE is unusable. */
export function parseTle(line1: string, line2: string): SatRec {
  const satrec = satellite.twoline2satrec(line1.trim(), line2.trim())
  // satrec.error is set to a non-zero code by twoline2satrec on bad input.
  if (satrec.error) {
    throw new Error(`Invalid TLE (error code ${satrec.error})`)
  }
  return satrec
}

/**
 * Map an ECI position (km) to a three.js Vector3 (scene units).
 * ECI is Z-up (north pole = +Z); three.js is Y-up, so we swap axes:
 *   three (x, y, z) = (eci.x, eci.z, -eci.y)
 */
function eciToVector3(p: { x: number; y: number; z: number }, target = new Vector3()): Vector3 {
  return target.set(p.x * KM_TO_SCENE, p.z * KM_TO_SCENE, -p.y * KM_TO_SCENE)
}

/** Current scene-space position of a satellite at the given date. Returns null if propagation fails. */
export function positionAt(satrec: SatRec, date: Date, target = new Vector3()): Vector3 | null {
  const pv = satellite.propagate(satrec, date)
  const eci = pv?.position
  if (!eci || typeof eci === 'boolean') return null
  return eciToVector3(eci, target)
}

/** Human-readable geodetic info (lat/lon/alt/speed) at the given date. */
export function geodeticAt(satrec: SatRec, date: Date): GeodeticInfo | null {
  const pv = satellite.propagate(satrec, date)
  const eci = pv?.position
  const vel = pv?.velocity
  if (!eci || typeof eci === 'boolean') return null

  const gmst = satellite.gstime(date)
  const geo = satellite.eciToGeodetic(eci, gmst)
  const speedKmS =
    vel && typeof vel !== 'boolean'
      ? Math.hypot(vel.x, vel.y, vel.z)
      : 0

  return {
    latitudeDeg: satellite.degreesLat(geo.latitude),
    longitudeDeg: satellite.degreesLong(geo.longitude),
    altitudeKm: geo.height,
    speedKmS,
  }
}

/** Orbital period in minutes (from mean motion, radians/min). */
export function orbitalPeriodMinutes(satrec: SatRec): number {
  return (2 * Math.PI) / satrec.no
}

/** Earth's gravitational parameter (GM), km^3/s^2 — for vis-viva. */
const MU_KM3_S2 = 398600.4418

/**
 * Period (minutes) of the *current* osculating orbit, derived from the live
 * state vector at `date` via vis-viva — NOT from `satrec.no`.
 *
 * Why: `satrec.no` is the mean motion at the TLE epoch. SGP4 propagates secular
 * drag, so for an old TLE the orbit has decayed and its real period at `date`
 * differs (e.g. a stale ISS TLE: 92.9 min at epoch vs ~89 min two years later).
 * Sampling the epoch period over- or under-shoots a full revolution and the
 * orbit ring fails to close. The osculating period closes it to within the
 * tiny residual left by J2 precession (which sampleOrbit's exact-close handles).
 * Falls back to the mean-motion period if propagation can't supply a velocity.
 */
export function osculatingPeriodMinutes(satrec: SatRec, date: Date): number {
  const pv = satellite.propagate(satrec, date)
  const pos = pv?.position
  const vel = pv?.velocity
  if (!pos || typeof pos === 'boolean' || !vel || typeof vel === 'boolean') {
    return orbitalPeriodMinutes(satrec)
  }
  const r = Math.hypot(pos.x, pos.y, pos.z)
  const v2 = vel.x * vel.x + vel.y * vel.y + vel.z * vel.z
  // Vis-viva: specific orbital energy -> semi-major axis -> period.
  const energy = v2 / 2 - MU_KM3_S2 / r
  const a = -MU_KM3_S2 / (2 * energy)
  if (!(a > 0)) return orbitalPeriodMinutes(satrec) // non-elliptical guard
  return (2 * Math.PI * Math.sqrt((a * a * a) / MU_KM3_S2)) / 60
}

/**
 * Largest orbit radius (apogee) across a set of satellites, in scene units.
 *
 * Used to pick a default camera distance that frames every orbit. We take the
 * osculating semi-major axis from the live state vector (vis-viva, same as
 * `osculatingPeriodMinutes`) so a drifted TLE still gives the real current
 * orbit, then apogee = a·(1+e). Satellites whose propagation fails are skipped.
 * Returns 0 if none are usable.
 */
export function maxOrbitRadiusScene(satrecs: SatRec[], date: Date): number {
  let maxScene = 0
  for (const satrec of satrecs) {
    const pv = satellite.propagate(satrec, date)
    const pos = pv?.position
    const vel = pv?.velocity
    if (!pos || typeof pos === 'boolean' || !vel || typeof vel === 'boolean') continue
    const r = Math.hypot(pos.x, pos.y, pos.z)
    const v2 = vel.x * vel.x + vel.y * vel.y + vel.z * vel.z
    const energy = v2 / 2 - MU_KM3_S2 / r
    const a = -MU_KM3_S2 / (2 * energy)
    const apogeeKm = a > 0 ? a * (1 + satrec.ecco) : r
    const scene = apogeeKm * KM_TO_SCENE
    if (scene > maxScene) maxScene = scene
  }
  return maxScene
}

/** Static orbital elements derived directly from the satrec. */
export function orbitalElements(satrec: SatRec): {
  inclinationDeg: number
  periodMinutes: number
  eccentricity: number
} {
  return {
    inclinationDeg: satrec.inclo * (180 / Math.PI),
    periodMinutes: orbitalPeriodMinutes(satrec),
    eccentricity: satrec.ecco,
  }
}

/**
 * Sample one full orbital period into an array of scene-space points,
 * forming a closed loop suitable for a <Line>. Computed in the inertial frame.
 */
export function sampleOrbit(satrec: SatRec, date: Date, segments = 256): Vector3[] {
  // Use the orbit's CURRENT period (from the live state vector), not the stale
  // epoch mean motion — otherwise a decayed/old TLE over- or under-shoots one
  // revolution and the ring fails to close into a single ellipse.
  const periodMs = osculatingPeriodMinutes(satrec, date) * 60_000
  const points: Vector3[] = []
  // Sample one period as distinct points...
  for (let i = 0; i < segments; i++) {
    const t = new Date(date.getTime() + (periodMs * i) / segments)
    const v = positionAt(satrec, t)
    if (v) points.push(v)
  }
  // ...then close the loop exactly so the start and end meet (no kink/overlap
  // from orbital precession over the sampled period).
  if (points.length) points.push(points[0].clone())
  return points
}

/** Earth mesh rotation (radians, about Y) that aligns geography for a given date. */
export function earthRotationY(date: Date): number {
  return satellite.gstime(date) + TEXTURE_LON_OFFSET
}
