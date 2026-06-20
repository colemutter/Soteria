import { Suspense, useRef } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { OrbitControls, Stars } from '@react-three/drei'
import { DirectionalLight, Vector3 } from 'three'
import { Earth } from './Earth'
import { SatelliteObject } from './SatelliteObject'
import { CameraRig } from './CameraRig'
import { SCENE_EARTH_RADIUS, maxOrbitRadiusScene } from '../lib/orbital'
import { sunDirection } from '../lib/sun'
import { simClock } from '../lib/simClock'
import { SATELLITES } from '../data/satellites'

/** Vertical field of view (deg) of the scene camera — kept in sync with the
 * <Canvas camera> below and used to compute a framing distance. */
const CAMERA_FOV = 45

/** Advances the shared clock once per frame, from inside the Canvas. */
function ClockDriver() {
  useFrame(() => simClock.tick())
  return null
}

/** One-time camera placement: view the globe side-on to the Sun (terminator
 * down the middle), like a classic day/night render. The rig takes over after. */
function InitialCamera({ distance }: { distance: number }) {
  const camera = useThree((s) => s.camera)
  const done = useRef(false)
  useFrame(() => {
    if (done.current) return
    const sun = sunDirection(simClock.date, new Vector3())
    const up = new Vector3(0, 1, 0)
    const right = new Vector3().crossVectors(up, sun)
    if (right.lengthSq() < 1e-6) right.set(1, 0, 0)
    right.normalize()
    // Fully side-on to the Sun so the terminator runs straight down the middle
    // of the disk — one half bright, one half dim (classic day/night view).
    camera.position
      .copy(right)
      .addScaledVector(up, 0.2)
      .normalize()
      .multiplyScalar(distance)
    camera.lookAt(0, 0, 0)
    done.current = true
  })
  return null
}

/** Directional light that follows the real Sun direction. */
function SunLight() {
  const ref = useRef<DirectionalLight>(null)
  const tmp = useRef(new Vector3())
  useFrame(() => {
    if (ref.current) {
      sunDirection(simClock.date, tmp.current)
      ref.current.position.copy(tmp.current.multiplyScalar(100))
    }
  })
  return <directionalLight ref={ref} intensity={3.2} />
}

interface Props {
  selectedId: string | null
  onSelect: (id: string | null) => void
  shadingOn: boolean
}

export function Scene({ selectedId, onSelect, shadingOn }: Props) {
  const satellites = SATELLITES.filter((s) => !s.error)
  const selected = SATELLITES.find((s) => s.id === selectedId) ?? null

  // Default camera distance: frame the highest-altitude orbit so every orbit is
  // visible at the default zoom. We fit the apogee sphere of radius `maxR` into
  // the vertical FOV (distance = R / sin(halfFov)) with a small margin, and
  // never come closer than the old Earth-overview distance.
  const maxR = maxOrbitRadiusScene(
    satellites.map((s) => s.satrec),
    simClock.date,
  )
  const halfFov = ((CAMERA_FOV / 2) * Math.PI) / 180
  const homeDistance = Math.max(
    (maxR / Math.sin(halfFov)) * 1.15,
    SCENE_EARTH_RADIUS * 3.6,
  )

  return (
    <Canvas
      camera={{ position: [0, 3, 9], fov: CAMERA_FOV, near: 0.05, far: 2000 }}
      onPointerMissed={() => onSelect(null)}
    >
      <ClockDriver />
      <InitialCamera distance={homeDistance} />
      <CameraRig selected={selected} homeDistance={homeDistance} />

      <color attach="background" args={['#05070f']} />
      <ambientLight intensity={1.4} />
      {/* General fill so satellite models stay visible from all sides. */}
      <hemisphereLight args={['#dce8ff', '#3a4358', 1.8]} />
      <SunLight />

      <Stars radius={300} depth={60} count={6000} factor={6} fade speed={0.4} />

      <Suspense fallback={null}>
        <Earth shadingOn={shadingOn} />
      </Suspense>

      {satellites.map((sat) => (
        <SatelliteObject
          key={sat.id}
          sat={sat}
          selected={sat.id === selectedId}
          onSelect={onSelect}
        />
      ))}

      <OrbitControls
        makeDefault
        enablePan={false}
        minDistance={SCENE_EARTH_RADIUS * 1.3}
        maxDistance={400}
        rotateSpeed={0.5}
        zoomSpeed={0.8}
      />
    </Canvas>
  )
}
