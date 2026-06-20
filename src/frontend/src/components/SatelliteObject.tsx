import { Suspense, useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import { Line, Html, useGLTF } from '@react-three/drei'
import { Vector3, Box3, type Group } from 'three'
import { positionAt, sampleOrbit } from '../lib/orbital'
import { simClock } from '../lib/simClock'
import type { SatelliteEntry } from '../data/satellites'

interface Props {
  sat: SatelliteEntry
  selected: boolean
  onSelect: (id: string) => void
}

/**
 * Zoom-responsive sizing for satellite models. To keep a satellite visible
 * without having to zoom all the way in, we hold its *apparent* (on-screen)
 * size roughly constant by growing the model in proportion to the camera's
 * distance from it — then clamp that to a world-unit floor and ceiling so it
 * never gets too small (vanishing) or too big (dominating the view):
 *
 *   targetWorldSize = clamp(APPARENT_FACTOR · distance, baseSize, MAX_WORLD_SIZE)
 *   scale           = targetWorldSize / baseSize
 *
 * - Up close (distance · APPARENT_FACTOR < baseSize) it sits at its true size.
 * - Across the mid/overview range it tracks a constant apparent size.
 * - Far out it caps at MAX_WORLD_SIZE so it can't balloon.
 */
const APPARENT_FACTOR = 0.04
const MAX_WORLD_SIZE = 0.75

function zoomScaleFor(distance: number, baseSize: number): number {
  const target = Math.min(
    MAX_WORLD_SIZE,
    Math.max(baseSize, APPARENT_FACTOR * distance),
  )
  return target / baseSize
}

/** A GLB model, cloned, centred, and scaled to `size` scene units. */
function SatelliteModel({ url, size }: { url: string; size: number }) {
  const { scene } = useGLTF(url)
  const cloned = useMemo(() => scene.clone(true), [scene])
  const { scale, offset } = useMemo(() => {
    const box = new Box3().setFromObject(cloned)
    const dims = box.getSize(new Vector3())
    const center = box.getCenter(new Vector3())
    const max = Math.max(dims.x, dims.y, dims.z) || 1
    return { scale: size / max, offset: center }
  }, [cloned, size])

  return (
    <group scale={scale}>
      <primitive object={cloned} position={[-offset.x, -offset.y, -offset.z]} />
    </group>
  )
}

function DotMarker({ color, scale }: { color: string; scale: number }) {
  return (
    <mesh scale={scale}>
      <sphereGeometry args={[0.025, 16, 16]} />
      <meshBasicMaterial color={color} />
    </mesh>
  )
}

export function SatelliteObject({ sat, selected, onSelect }: Props) {
  const groupRef = useRef<Group>(null)
  const scratch = useMemo(() => new Vector3(), [])

  const orbitPoints = useMemo(
    () => sampleOrbit(sat.satrec, simClock.date),
    [sat.satrec],
  )

  const size = sat.model?.size ?? 0.08
  const hitRadius = Math.max(size, 0.06)

  useFrame((state) => {
    if (!groupRef.current) return
    const p = positionAt(sat.satrec, simClock.date, scratch)
    if (!p) return
    groupRef.current.position.copy(p)
    // Grow the model as the camera pulls away so it stays visible, capped.
    const dist = state.camera.position.distanceTo(p)
    groupRef.current.scale.setScalar(zoomScaleFor(dist, size))
  })

  return (
    <>
      <Line
        points={orbitPoints}
        color={sat.color}
        transparent
        opacity={selected ? 0.85 : 0.22}
        lineWidth={selected ? 1.6 : 1}
        // Depth-test ON so the opaque Earth occludes the half of the orbit that
        // passes behind it — otherwise the back half shows through and the globe
        // reads as translucent. depthWrite stays off (it's a transparent line).
        depthWrite={false}
      />

      <group ref={groupRef}>
        {/* Invisible hit area for easy clicking. */}
        <mesh
          onClick={(e) => {
            e.stopPropagation()
            onSelect(sat.id)
          }}
          onPointerOver={(e) => {
            e.stopPropagation()
            document.body.style.cursor = 'pointer'
          }}
          onPointerOut={() => {
            document.body.style.cursor = 'auto'
          }}
        >
          <sphereGeometry args={[hitRadius, 12, 12]} />
          <meshBasicMaterial transparent opacity={0} depthWrite={false} />
        </mesh>

        {sat.model ? (
          <Suspense
            fallback={<DotMarker color={sat.color!} scale={selected ? 1.8 : 1} />}
          >
            <SatelliteModel url={sat.model.url} size={size} />
          </Suspense>
        ) : (
          <DotMarker color={sat.color!} scale={selected ? 1.8 : 1} />
        )}

        {selected && (
          <Html position={[0, hitRadius + 0.05, 0]} center zIndexRange={[10, 0]}>
            <div className="sat-label">{sat.name}</div>
          </Html>
        )}
      </group>
    </>
  )
}
