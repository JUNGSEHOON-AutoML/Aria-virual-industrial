// inspectVfx — 2D↔3D 시각화 공용 헬퍼(스캔라인 셰이더 + Decal 빌더).
// 명세 §B/§C. 물리/리메시 없음. 셰이더 1개 + DecalGeometry.
import * as THREE from 'three'
import { DecalGeometry } from 'three/examples/jsm/geometries/DecalGeometry.js'
import { project2Dto3D } from './coordinateTransform'

// 표준 머티리얼에 월드Y 스캔라인 발광선 주입. material.userData.shader 로 uniforms 접근.
export function injectScanShader(mat, color = 0x1FB8CD) {
  mat.onBeforeCompile = (shader) => {
    shader.uniforms.uScanY = { value: -9999 }
    shader.uniforms.uScanColor = { value: new THREE.Color(color) }
    mat.userData.shader = shader
    shader.vertexShader = 'varying vec3 vWPScan;\n' + shader.vertexShader.replace(
      '#include <begin_vertex>',
      '#include <begin_vertex>\n  vWPScan = (modelMatrix * vec4(transformed,1.0)).xyz;'
    )
    shader.fragmentShader =
      'uniform float uScanY;\nuniform vec3 uScanColor;\nvarying vec3 vWPScan;\n' +
      shader.fragmentShader.replace(
        '#include <dithering_fragment>',
        `#include <dithering_fragment>
         float dScan = abs(vWPScan.y - uScanY);
         float glow = smoothstep(0.06, 0.0, dScan);
         gl_FragColor.rgb += glow * uScanColor * 1.8;`
      )
  }
  mat.needsUpdate = true
}

export function setScanY(mat, y) {
  const s = mat?.userData?.shader
  if (s) s.uniforms.uScanY.value = y
}

// data URI → THREE.Texture (heatmap 크롭/오버레이용). 실패 시 null.
export function texFromDataURI(uri) {
  if (!uri) return null
  const img = new Image()
  const tex = new THREE.Texture(img)
  img.onload = () => { tex.needsUpdate = true }
  img.src = uri
  return tex
}

// heatmap_b64(alpha=이상도) → 그레이스케일 높이맵 텍스처(R채널=높이). displacementMap용.
// 결함 점수 높은(붉은=alpha 큰) 영역 → 밝음 → 정점 돌출. 실데이터 기반(난수 아님).
export function heightTexFromDataURI(uri) {
  if (!uri) return null
  const tex = new THREE.Texture()
  const img = new Image()
  img.onload = () => {
    try {
      const c = document.createElement('canvas'); c.width = img.width; c.height = img.height
      const ctx = c.getContext('2d'); ctx.drawImage(img, 0, 0)
      const d = ctx.getImageData(0, 0, c.width, c.height)
      const px = d.data
      for (let i = 0; i < px.length; i += 4) {
        const a = px[i + 3]              // alpha = 이상도
        px[i] = a; px[i + 1] = a; px[i + 2] = a; px[i + 3] = 255
      }
      ctx.putImageData(d, 0, 0)
      tex.image = c; tex.needsUpdate = true
    } catch { /* 무시 */ }
  }
  img.src = uri
  return tex
}

// (u,v)→(x,y,z) 변환(coordinateTransform 단일 모듈) → 표면 교점에 적색 emissive Decal.
// peakXY = [nx, ny] (0..1, heatmap 좌표) · boothCam = PerspectiveCamera · target = 부품 mesh
// opts = { mode:'sim'|'real', calib } (real 캘리브 없으면 sim 폴백)
// 반환: { decal, point, normal, mode } 또는 null.
export function buildDecal(target, boothCam, peakXY, heatTex, size = 0.34, opts = {}) {
  if (!target || !boothCam || !peakXY) return null
  const r = project2Dto3D({ uv: peakXY, mode: opts.mode || 'sim', camera: boothCam, mesh: target, calib: opts.calib })
  if (!r.ok) return null
  const { point, normal } = r
  const helper = new THREE.Object3D()
  helper.position.copy(point)
  helper.lookAt(point.clone().add(normal))

  const geo = new DecalGeometry(target, point, helper.rotation,
    new THREE.Vector3(size, size, size))
  const mat = new THREE.MeshStandardMaterial({
    map: heatTex || null, emissiveMap: heatTex || null,
    emissive: 0xff3344, emissiveIntensity: heatTex ? 1.0 : 0.85,
    color: heatTex ? 0xffffff : 0xff3344,
    transparent: true, opacity: 0.95, depthTest: true, depthWrite: false,
    polygonOffset: true, polygonOffsetFactor: -4,
  })
  const decal = new THREE.Mesh(geo, mat)
  return { decal, point: point.clone(), normal, mode: r.mode, fellBack: r.fellBack }
}
