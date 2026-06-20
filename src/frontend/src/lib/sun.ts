import { Vector3 } from 'three'

/**
 * Low-precision solar position. Returns the unit direction from Earth's centre
 * toward the Sun, in the same scene frame as the satellites (inertial / ECI,
 * mapped to three.js Y-up). Because satellites live in the inertial frame and
 * the Earth mesh rotates beneath them, a fixed-ish Sun direction gives a correct
 * day/night cycle as the Earth spins.
 *
 * Algorithm: NOAA / Astronomical Almanac low-precision sun (good to ~0.01°).
 */
const DEG2RAD = Math.PI / 180

export function sunDirection(date: Date, target = new Vector3()): Vector3 {
  // Julian day and days since J2000.0
  const jd = date.getTime() / 86_400_000 + 2_440_587.5
  const n = jd - 2_451_545.0

  const L = (280.46 + 0.9856474 * n) % 360 // mean longitude (deg)
  const g = ((357.528 + 0.9856003 * n) % 360) * DEG2RAD // mean anomaly (rad)

  // Ecliptic longitude (deg)
  const lambda =
    (L + 1.915 * Math.sin(g) + 0.02 * Math.sin(2 * g)) * DEG2RAD
  // Obliquity of the ecliptic (rad)
  const eps = (23.439 - 0.0000004 * n) * DEG2RAD

  // Unit vector in equatorial (ECI) coordinates: X→vernal equinox, Z→north
  const x = Math.cos(lambda)
  const y = Math.cos(eps) * Math.sin(lambda)
  const z = Math.sin(eps) * Math.sin(lambda)

  // Map ECI (Z-up) → three.js (Y-up): (x, z, -y), matching orbital.ts
  return target.set(x, z, -y).normalize()
}
