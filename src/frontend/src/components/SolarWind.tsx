import { useEffect, useMemo, useRef } from 'react'
import { useFrame, useThree } from '@react-three/fiber'
import {
  AdditiveBlending,
  Color,
  type Points,
  type ShaderMaterial,
  Vector3,
} from 'three'
import { sunDirection } from '../lib/sun'
import { simClock } from '../lib/simClock'
import {
  getSolarDataset,
  conditionsAt,
  DEFAULT_CONDITIONS,
  type SolarConditions,
  type SolarDataset,
} from '../lib/solarData'

/**
 * Solar-wind particle stream, driven by live space-weather data from Supabase.
 *
 * Particles flow radially away from the Sun (along -sunDirection) through a
 * cylindrical volume around Earth. Each particle keeps a fixed perpendicular
 * offset and an animated axial `phase` that wraps 0→1, so the field streams
 * continuously and rotates rigidly as the Sun direction changes. Live data maps:
 *   Kp            → flow speed + brightness
 *   Bz (south)+Kp → colour (calm blue → storm red)
 *   Bt            → brightness / particle size
 */

const COUNT = 2600
const SPAN = 30 // length of the streaming volume along the wind axis (scene units)
const RADIUS = 10 // perpendicular spread around the axis

const REFRESH_MS = 5 * 60 * 1000 // re-read conditions every 5 min

const CALM_COLOR = new Color('#5fa8ff')
const STORM_COLOR = new Color('#ff5230')

const vertexShader = /* glsl */ `
  uniform float uSize;
  uniform float uViewportHeight;
  uniform float uFadeNear;
  uniform float uFadeFar;
  varying float vFade;
  void main() {
    // Particles live at the scene root, so position is already relative to the
    // Earth (origin). Fade with distance from Earth so the wind reads as a glow
    // around the planet rather than a hard-edged volume.
    float distFromEarth = length(position);
    vFade = 1.0 - smoothstep(uFadeNear, uFadeFar, distFromEarth);

    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    // Scale the on-screen size with the viewport (drawing-buffer) height so
    // particles stay the same apparent size at any resolution / device pixel
    // ratio, with perspective attenuation (nearer particles look larger).
    // Clamped so near particles can't blow up into screen-filling blobs.
    gl_PointSize = clamp(uSize * uViewportHeight / -mv.z, 1.5, 64.0);
    gl_Position = projectionMatrix * mv;
  }
`

const fragmentShader = /* glsl */ `
  uniform vec3 uColor;
  uniform float uOpacity;
  varying float vFade;
  void main() {
    if (vFade <= 0.001) discard;
    // Soft round point.
    float d = length(gl_PointCoord - vec2(0.5));
    if (d > 0.5) discard;
    float a = smoothstep(0.5, 0.0, d) * uOpacity * vFade;
    gl_FragColor = vec4(uColor, a);
  }
`

const clamp01 = (x: number) => Math.min(1, Math.max(0, x))

export function SolarWind({ demo = false }: { demo?: boolean }) {
  const pointsRef = useRef<Points>(null)
  const matRef = useRef<ShaderMaterial>(null)

  // Fixed per-particle perpendicular offsets + animated axial phase.
  const { offU, offV, phase, positions } = useMemo(() => {
    const offU = new Float32Array(COUNT)
    const offV = new Float32Array(COUNT)
    const phase = new Float32Array(COUNT)
    const positions = new Float32Array(COUNT * 3)
    for (let i = 0; i < COUNT; i++) {
      const angle = Math.random() * Math.PI * 2
      const r = Math.sqrt(Math.random()) * RADIUS // uniform over the disk
      offU[i] = Math.cos(angle) * r
      offV[i] = Math.sin(angle) * r
      phase[i] = Math.random()
    }
    return { offU, offV, phase, positions }
  }, [])

  const uniforms = useMemo(
    () => ({
      uColor: { value: CALM_COLOR.clone() },
      uOpacity: { value: 0.5 },
      // `uSize` is a small world-space factor; the on-screen size is
      // uSize * viewportHeight / depth (see the vertex shader).
      uSize: { value: 0.3 },
      uViewportHeight: { value: 800 },
      // Fade range (scene units from Earth center): full near the surface,
      // gone by ~FADE_FAR so the field doesn't read as a rectangular volume.
      uFadeNear: { value: 3.0 },
      uFadeFar: { value: 13.0 },
    }),
    [],
  )

  // Keep the point-size scale in sync with the canvas resolution so particles
  // are sized relative to the viewport (not in fixed device pixels).
  const viewportHeight = useThree((s) => s.size.height)
  const dpr = useThree((s) => s.viewport.dpr)
  useEffect(() => {
    uniforms.uViewportHeight.value = viewportHeight * dpr
  }, [viewportHeight, dpr, uniforms])

  // Time-resolved dataset (Kp history+forecast + latest Bz/Bt), kept in a ref so
  // the frame loop can read conditions at simClock.date — including future times
  // while scrubbing the timeline — without re-rendering.
  const dataRef = useRef<SolarDataset | null>(null)
  useEffect(() => {
    let active = true
    const load = async () => {
      const ds = await getSolarDataset(demo)
      if (active && ds) dataRef.current = ds
    }
    void load()
    const id = setInterval(() => void load(), REFRESH_MS)
    return () => {
      active = false
      clearInterval(id)
    }
  }, [demo])

  // Apply conditions (for the current simulated time) to speed + material.
  const speedRef = useRef(4)
  const applyConditions = (cond: SolarConditions) => {
    const kpN = clamp01(cond.kp / 9)
    const southward = Math.max(0, -cond.bzNt) // southward IMF is geoeffective
    const storm = clamp01(kpN * 0.65 + (southward / 15) * 0.35)
    const btN = clamp01(cond.btNt / 20)

    speedRef.current = 3 + kpN * 12 // scene units / sec
    if (matRef.current) {
      matRef.current.uniforms.uColor.value
        .copy(CALM_COLOR)
        .lerp(STORM_COLOR, storm)
      matRef.current.uniforms.uOpacity.value = 0.5 + 0.4 * Math.max(kpN, btN)
      matRef.current.uniforms.uSize.value = 0.26 + 0.34 * Math.max(storm, btN)
    }
  }

  // Reusable scratch vectors for the per-frame basis.
  const sun = useMemo(() => new Vector3(), [])
  const windDir = useMemo(() => new Vector3(), [])
  const U = useMemo(() => new Vector3(), [])
  const V = useMemo(() => new Vector3(), [])
  const UP = useMemo(() => new Vector3(0, 1, 0), [])

  useFrame((_, delta) => {
    const geo = pointsRef.current?.geometry
    if (!geo) return

    // Conditions at the current simulated time (forecast when scrubbed ahead).
    const ds = dataRef.current
    applyConditions(ds ? conditionsAt(ds, simClock.date) : DEFAULT_CONDITIONS)

    // Wind flows from the Sun toward the anti-solar side.
    sunDirection(simClock.date, sun)
    windDir.copy(sun).multiplyScalar(-1).normalize()
    // Orthonormal basis perpendicular to the wind axis.
    U.crossVectors(windDir, UP)
    if (U.lengthSq() < 1e-6) U.set(1, 0, 0)
    U.normalize()
    V.crossVectors(windDir, U).normalize()

    const dPhase = (speedRef.current / SPAN) * Math.min(delta, 0.05)
    const pos = geo.attributes.position.array as Float32Array
    for (let i = 0; i < COUNT; i++) {
      let ph = phase[i] + dPhase
      if (ph >= 1) ph -= 1
      phase[i] = ph
      const axial = ph * SPAN - SPAN / 2
      const ou = offU[i]
      const ov = offV[i]
      const j = i * 3
      pos[j] = windDir.x * axial + U.x * ou + V.x * ov
      pos[j + 1] = windDir.y * axial + U.y * ou + V.y * ov
      pos[j + 2] = windDir.z * axial + U.z * ou + V.z * ov
    }
    geo.attributes.position.needsUpdate = true
  })

  return (
    <points ref={pointsRef} frustumCulled={false}>
      <bufferGeometry>
        <bufferAttribute
          attach="attributes-position"
          args={[positions, 3]}
        />
      </bufferGeometry>
      <shaderMaterial
        ref={matRef}
        uniforms={uniforms}
        vertexShader={vertexShader}
        fragmentShader={fragmentShader}
        transparent
        depthWrite={false}
        blending={AdditiveBlending}
      />
    </points>
  )
}
