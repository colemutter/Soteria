import { Suspense, useMemo, useRef } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { OrbitControls, useGLTF } from '@react-three/drei'
import { Box3, Vector3, type Group } from 'three'

/** A GLB model, cloned, centred, and scaled to fit a ~`fit`-unit box. */
function Model({ url, fit = 2.2 }: { url: string; fit?: number }) {
  const { scene } = useGLTF(url)
  const cloned = useMemo(() => scene.clone(true), [scene])
  const ref = useRef<Group>(null)

  const { scale, offset } = useMemo(() => {
    const box = new Box3().setFromObject(cloned)
    const dims = box.getSize(new Vector3())
    const center = box.getCenter(new Vector3())
    const max = Math.max(dims.x, dims.y, dims.z) || 1
    return { scale: fit / max, offset: center }
  }, [cloned, fit])

  // Gentle idle spin; OrbitControls lets the user take over.
  useFrame((_, dt) => {
    if (ref.current) ref.current.rotation.y += dt * 0.35
  })

  return (
    <group ref={ref} scale={scale}>
      <primitive object={cloned} position={[-offset.x, -offset.y, -offset.z]} />
    </group>
  )
}

/** Inline 3D viewer for a single satellite model (own canvas + lighting). */
export function ModelViewer({ url }: { url: string }) {
  return (
    <Canvas
      className="model-canvas"
      camera={{ position: [0, 0.6, 4], fov: 42, near: 0.1, far: 100 }}
      dpr={[1, 2]}
    >
      <ambientLight intensity={1.3} />
      <hemisphereLight args={['#dce8ff', '#3a4358', 1.5]} />
      <directionalLight position={[5, 4, 6]} intensity={2.6} />
      <directionalLight position={[-4, -2, -3]} intensity={0.8} />
      <Suspense fallback={null}>
        <Model url={url} />
      </Suspense>
      <OrbitControls
        enablePan={false}
        minDistance={2}
        maxDistance={8}
        autoRotate={false}
      />
    </Canvas>
  )
}
