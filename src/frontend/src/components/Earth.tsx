import { useMemo, useRef } from 'react'
import { useFrame, useLoader } from '@react-three/fiber'
import {
  TextureLoader,
  ShaderMaterial,
  Vector3,
  SRGBColorSpace,
  type Mesh,
} from 'three'
import { SCENE_EARTH_RADIUS, earthRotationY } from '../lib/orbital'
import { sunDirection } from '../lib/sun'
import { simClock } from '../lib/simClock'

const vertexShader = /* glsl */ `
  varying vec2 vUv;
  varying vec3 vWorldNormal;
  void main() {
    vUv = uv;
    vWorldNormal = normalize(mat3(modelMatrix) * normal);
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`

const fragmentShader = /* glsl */ `
  uniform sampler2D dayTexture;
  uniform sampler2D nightTexture;
  uniform vec3 sunDirection;
  varying vec2 vUv;
  varying vec3 vWorldNormal;

  uniform float ambient;    // general fill so the whole globe stays visible
  uniform float brightness; // overall day-map gain
  uniform float oceanLift;  // how much to lighten the deep-blue oceans (0 = off)
  uniform float shaded;     // 1 = day/night + ocean effects, 0 = plain lit globe

  void main() {
    // Sample the maps directly (no gamma linearization, which was crushing the
    // midtones/oceans into darkness) for a bright, vivid globe.
    vec3 dayTex = texture2D(dayTexture, vUv).rgb;
    vec3 nightTex = texture2D(nightTexture, vUv).rgb;

    // Shading off: show the plain day texture, fully lit everywhere.
    if (shaded < 0.5) {
      gl_FragColor = vec4(dayTex * brightness, 1.0);
      return;
    }

    // Lighten the deep-blue oceans so the day side reads lighter (boosts the
    // day/night contrast). Detect ocean by RELATIVE blue dominance (blue clearly
    // brighter than red & green) — this is scale-independent, so it works whether
    // the sampled texels are sRGB or GPU-decoded to linear. Land/clouds, where
    // red or green is comparable, are left alone.
    float rg = max(dayTex.r, dayTex.g);
    float oceanMask = smoothstep(1.1, 1.4, dayTex.b / (rg + 0.001));
    // Blend the ocean toward a single, fairly uniform lighter-blue (so the deep
    // ocean sits close to the coastal/shallow colour instead of going dark navy).
    // A small amount of the original is kept so it isn't perfectly flat.
    vec3 oceanColor = vec3(0.05, 0.18, 0.38); // uniform ocean blue (linear)
    dayTex = mix(dayTex, oceanColor, oceanMask * oceanLift);

    // cosAngle > 0 is the hemisphere facing the Sun, so the day/night split sits
    // exactly at cosAngle = 0 — i.e. almost exactly half the globe is "day",
    // centred on the sub-solar point. A narrow smoothstep keeps the terminator
    // crisp (clean half-and-half) instead of a wide, mushy gradient.
    float cosAngle = dot(normalize(vWorldNormal), normalize(sunDirection));
    float dayFactor = smoothstep(-0.07, 0.07, cosAngle);

    // Bright sunlit half vs. a clearly dimmer night half (the ambient level).
    vec3 base = dayTex * mix(ambient, 1.0, dayFactor) * brightness;

    // City lights as a subtle glow on the dark side only.
    vec3 cityLights = nightTex * (1.0 - dayFactor) * 0.5;

    gl_FragColor = vec4(base + cityLights, 1.0);
  }
`

/**
 * Textured Earth with a real day/night cycle. The mesh rotates by GMST so
 * geography lines up with the inertial satellite frame, and a custom shader
 * blends the night-lights texture across the terminator based on the live Sun
 * direction.
 */
export function Earth({ shadingOn = true }: { shadingOn?: boolean }) {
  const meshRef = useRef<Mesh>(null)

  const [dayMap, nightMap] = useLoader(TextureLoader, [
    '/textures/2k_earth_daymap.jpg',
    '/textures/2k_earth_nightmap.jpg',
  ])
  dayMap.colorSpace = SRGBColorSpace
  nightMap.colorSpace = SRGBColorSpace

  const material = useMemo(
    () =>
      new ShaderMaterial({
        uniforms: {
          dayTexture: { value: dayMap },
          nightTexture: { value: nightMap },
          sunDirection: { value: new Vector3(1, 0, 0) },
          ambient: { value: 0.15 },
          brightness: { value: 1.15 },
          oceanLift: { value: 0.0 },
          shaded: { value: 1 },
        },
        vertexShader,
        fragmentShader,
      }),
    [dayMap, nightMap],
  )

  useFrame(() => {
    if (meshRef.current) {
      meshRef.current.rotation.y = earthRotationY(simClock.date)
    }
    sunDirection(simClock.date, material.uniforms.sunDirection.value)
    material.uniforms.shaded.value = shadingOn ? 1 : 0
  })

  return (
    <group>
      <mesh ref={meshRef} material={material}>
        <sphereGeometry args={[SCENE_EARTH_RADIUS, 96, 96]} />
      </mesh>
      {/* Atmosphere glow: a slightly larger back-side shell. */}
      <mesh scale={1.02}>
        <sphereGeometry args={[SCENE_EARTH_RADIUS, 64, 64]} />
        <meshBasicMaterial color="#3a86ff" transparent opacity={0.12} side={1} />
      </mesh>
    </group>
  )
}
