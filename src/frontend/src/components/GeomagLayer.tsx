import { useEffect, useMemo, useRef } from 'react'
import { useFrame, useThree } from '@react-three/fiber'
import {
  AdditiveBlending,
  Color,
  type Points,
  type ShaderMaterial,
  Vector3,
} from 'three'
import { SCENE_EARTH_RADIUS, earthRotationY } from '../lib/orbital'
import { simClock } from '../lib/simClock'
import {
  getSolarDataset,
  conditionsAt,
  DEFAULT_CONDITIONS,
  type SolarDataset,
} from '../lib/solarData'

/**
 * Geomagnetic activity layer: auroral ovals around the north and south poles,
 * driven by the Kp index from the same SWPC table as the solar wind. As Kp
 * rises the ovals move equatorward (lower latitude), brighten, and shift from
 * green toward red — mirroring how real auroras intensify during storms. Reads
 * Kp at simClock.date each frame, so it follows the timeline (forecast included).
 *
 * Particles are placed by the vertex shader from per-particle (longitude, band
 * offset, pole) attributes plus a Kp-driven colatitude uniform, so we only
 * update a few uniforms per frame. The ovals are centred on the geographic axis
 * (the ~11° geomagnetic offset is ignored for now).
 */

const PER_POLE = 1200
const COUNT = PER_POLE * 2
const RADIUS = SCENE_EARTH_RADIUS * 1.02 // just above the surface
const REFRESH_MS = 5 * 60 * 1000
const DEG2RAD = Math.PI / 180

const QUIET_COLOR = new Color('#4dff9e') // green aurora
const STORM_COLOR = new Color('#ff3d6e') // red/magenta during strong storms

// Geomagnetic dipole offset: the magnetic axis is tilted ~11° from the spin
// axis, with the north geomagnetic pole near 80.7°N, 72.7°W. We pre-compute that
// pole's direction in the Earth's body frame (matching the mesh's texture
// mapping, where geographic lon maps to azimuth π + lon), then rotate it by the
// Earth's current spin each frame so the ovals track the magnetic poles.
const TILT_RAD = 11 * (Math.PI / 180)
const MAG_POLE_LON_RAD = -72.7 * (Math.PI / 180)
const BODY_PHI = Math.PI + MAG_POLE_LON_RAD
const BODY_HX = -Math.cos(BODY_PHI) * Math.sin(TILT_RAD)
const BODY_HZ = Math.sin(BODY_PHI) * Math.sin(TILT_RAD)
const BODY_Y = Math.cos(TILT_RAD)

const clamp01 = (x: number) => Math.min(1, Math.max(0, x))

const vertexShader = /* glsl */ `
  #define PI 3.141592653589793
  uniform float uColat;
  uniform float uBandWidth;
  uniform float uRadius;
  uniform float uSize;
  uniform float uViewportHeight;
  attribute float aLon;
  attribute float aWidth;
  attribute float aPole;
  void main() {
    // Polar angle from +Y: the oval sits at colatitude uColat (north) or its
    // mirror (south), spread by the band width.
    float colat = uColat + aWidth * uBandWidth;
    float theta = aPole > 0.0 ? colat : (PI - colat);
    float st = sin(theta);
    vec3 p = vec3(
      uRadius * st * cos(aLon),
      uRadius * cos(theta),
      uRadius * st * sin(aLon)
    );
    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    gl_PointSize = clamp(uSize * uViewportHeight / -mv.z, 1.0, 36.0);
    gl_Position = projectionMatrix * mv;
  }
`

const fragmentShader = /* glsl */ `
  uniform vec3 uColor;
  uniform float uOpacity;
  void main() {
    float d = length(gl_PointCoord - vec2(0.5));
    if (d > 0.5) discard;
    float a = smoothstep(0.5, 0.0, d) * uOpacity;
    gl_FragColor = vec4(uColor, a);
  }
`

export function GeomagLayer({ demo = false }: { demo?: boolean }) {
  const pointsRef = useRef<Points>(null)
  const matRef = useRef<ShaderMaterial>(null)

  // Per-particle attributes. `position` is required by three but unused — the
  // real location is computed in the vertex shader from the attributes below.
  const { positions, aLon, aWidth, aPole } = useMemo(() => {
    const positions = new Float32Array(COUNT * 3)
    const aLon = new Float32Array(COUNT)
    const aWidth = new Float32Array(COUNT)
    const aPole = new Float32Array(COUNT)
    for (let i = 0; i < COUNT; i++) {
      aLon[i] = Math.random() * Math.PI * 2
      // Triangular distribution → denser toward the centre of the band.
      aWidth[i] = Math.random() - Math.random()
      aPole[i] = i < PER_POLE ? 1 : -1
    }
    return { positions, aLon, aWidth, aPole }
  }, [])

  const uniforms = useMemo(
    () => ({
      uColor: { value: QUIET_COLOR.clone() },
      uOpacity: { value: 0.3 },
      uSize: { value: 0.22 },
      uViewportHeight: { value: 800 },
      uColat: { value: 23 * DEG2RAD },
      uBandWidth: { value: 5 * DEG2RAD },
      uRadius: { value: RADIUS },
    }),
    [],
  )

  // Keep point size scaled to the viewport (matches the solar-wind layer).
  const vh = useThree((s) => s.size.height)
  const dpr = useThree((s) => s.viewport.dpr)
  useEffect(() => {
    uniforms.uViewportHeight.value = vh * dpr
  }, [vh, dpr, uniforms])

  // Shared dataset (Kp history + forecast), read at simClock.date each frame.
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

  const up = useMemo(() => new Vector3(0, 1, 0), [])
  const magAxis = useMemo(() => new Vector3(), [])

  useFrame(() => {
    const mat = matRef.current
    if (!mat) return
    const ds = dataRef.current
    const kp = ds ? conditionsAt(ds, simClock.date).kp : DEFAULT_CONDITIONS.kp
    const kpN = clamp01(kp / 9)

    const u = mat.uniforms
    // Equatorward expansion: ~67° latitude (23° colat) quiet → ~40° at Kp 9.
    u.uColat.value = (23 + kpN * 27) * DEG2RAD
    u.uBandWidth.value = (4 + kpN * 3) * DEG2RAD
    u.uOpacity.value = 0.22 + 0.7 * kpN
    u.uSize.value = 0.2 + 0.16 * kpN
    u.uColor.value.copy(QUIET_COLOR).lerp(STORM_COLOR, clamp01((kp - 4) / 5))

    // Orient the ovals on the geomagnetic axis: rotate the body-frame pole by
    // the Earth's current spin, then aim the layer's local +Y at it. The shader
    // builds the ovals around local +Y, so both poles tilt together correctly.
    if (pointsRef.current) {
      const r = earthRotationY(simClock.date)
      const cr = Math.cos(r)
      const sr = Math.sin(r)
      magAxis.set(
        BODY_HX * cr + BODY_HZ * sr,
        BODY_Y,
        -BODY_HX * sr + BODY_HZ * cr,
      )
      pointsRef.current.quaternion.setFromUnitVectors(up, magAxis)
    }
  })

  return (
    <points ref={pointsRef} frustumCulled={false}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
        <bufferAttribute attach="attributes-aLon" args={[aLon, 1]} />
        <bufferAttribute attach="attributes-aWidth" args={[aWidth, 1]} />
        <bufferAttribute attach="attributes-aPole" args={[aPole, 1]} />
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
