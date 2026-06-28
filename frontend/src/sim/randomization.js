export const RANGES = {
  part:  { x: [-0.15, 0.15], z: [-0.15, 0.15], rotY: [0, Math.PI * 2], tilt: [-0.12, 0.12] },
  light: { ambient: [0.20, 0.60], key: [0.60, 1.60] },
}
const rand = ([lo, hi]) => lo + Math.random() * (hi - lo)

// 색온도: warm ↔ cool 보간
function sampleColor() {
  const t = Math.random()
  const lerp = (a, b) => Math.round((a + (b - a) * t) * 255)
  return `rgb(${lerp(1.0, 0.86)},${lerp(0.94, 0.92)},${lerp(0.86, 1.0)})`
}

export function sampleSceneParams() {
  return {
    part:  {
      x: rand(RANGES.part.x), z: rand(RANGES.part.z),
      rotY: rand(RANGES.part.rotY),
      rotX: rand(RANGES.part.tilt), rotZ: rand(RANGES.part.tilt),
    },
    light: { ambient: rand(RANGES.light.ambient), key: rand(RANGES.light.key), color: sampleColor() },
  }
}

export function sampleCameraParams() {
  return {
    az: Math.random() * Math.PI * 2,        // 방위각
    el: 0.30 + Math.random() * 0.90,         // 고도(라디안)
    dist: 3.5 + Math.random() * 2.5,         // 거리
  }
}
