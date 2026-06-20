import { useRef } from 'react'
import { useFrame, useThree } from '@react-three/fiber'
import { Vector3 } from 'three'
import type { OrbitControls as OrbitControlsImpl } from 'three-stdlib'
import { positionAt, SCENE_EARTH_RADIUS } from '../lib/orbital'
import { simClock } from '../lib/simClock'
import type { SatelliteEntry } from '../data/satellites'

const ORIGIN = new Vector3()

/**
 * Drives the camera. On selection it eases the orbit pivot onto the satellite
 * and dollies in to a close framing, then tracks the satellite's motion while
 * leaving the user free to orbit and zoom. On deselection it eases back out to
 * the Earth overview ONCE, then hands control fully back to the user (so a zoom
 * in overview mode is not snapped back the next frame).
 *
 * `homeDistance` is the default framing distance — chosen by the scene to fit
 * the highest-altitude orbit in view.
 *
 * Reads the active controls from R3F state (OrbitControls is `makeDefault`),
 * which is more reliable than threading a ref.
 */
export function CameraRig({
  selected,
  homeDistance,
}: {
  selected: SatelliteEntry | null
  homeDistance: number
}) {
  const camera = useThree((s) => s.camera)
  const controls = useThree((s) => s.controls) as OrbitControlsImpl | null

  const pos = useRef(new Vector3())
  const offset = useRef(new Vector3())
  const activeId = useRef<string | null>(null)
  const settled = useRef(false)
  // True only while easing back to the overview after a deselection. Once we
  // arrive we clear it and stop touching the camera, leaving zoom to the user.
  const returning = useRef(false)

  useFrame(() => {
    if (!controls) return
    const sel = selected && !selected.error ? selected : null

    if (sel) {
      const p = positionAt(sel.satrec, simClock.date, pos.current)
      if (!p) return
      const desiredDist = Math.max((sel.model?.size ?? 0.08) * 3.2, 0.4)

      if (activeId.current !== sel.id) {
        activeId.current = sel.id
        settled.current = false
        controls.minDistance = 0.1
      }

      // Offset of camera from the pivot — preserves any user-applied rotation.
      offset.current.copy(camera.position).sub(controls.target)
      let len = offset.current.length()
      if (len < 1e-4) {
        offset.current.set(0, 0.3, 1)
        len = offset.current.length()
      }

      // Dolly in to the target framing once; afterwards leave zoom to the user.
      if (!settled.current) {
        let next = len + (desiredDist - len) * 0.08
        if (Math.abs(next - desiredDist) < 0.02) {
          next = desiredDist
          settled.current = true
        }
        offset.current.setLength(next)
      }

      controls.target.lerp(p, 0.25)
      camera.position.copy(controls.target).add(offset.current)
      controls.update()
    } else {
      // Just deselected: re-engage the overview homing pass once.
      if (activeId.current !== null) {
        activeId.current = null
        controls.minDistance = SCENE_EARTH_RADIUS * 1.3
        returning.current = true
      }
      // Outside that one homing pass, do nothing — the user owns the camera and
      // their zoom/orbit must persist (no snapping back to the default).
      if (!returning.current) return

      offset.current.copy(camera.position).sub(controls.target)
      const len = offset.current.length() || 1
      const nextLen = len + (homeDistance - len) * 0.05
      offset.current.setLength(nextLen)
      controls.target.lerp(ORIGIN, 0.05)
      camera.position.copy(controls.target).add(offset.current)
      controls.update()

      // Arrived at the overview — release the camera back to the user.
      if (
        Math.abs(nextLen - homeDistance) < 0.05 &&
        controls.target.lengthSq() < 1e-4
      ) {
        returning.current = false
      }
    }
  })

  return null
}
