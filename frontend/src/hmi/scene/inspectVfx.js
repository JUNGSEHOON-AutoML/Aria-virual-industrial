// inspectVfx — 2D↔3D 시각화 공용 헬퍼(스캔라인 셰이더 + Decal 빌더).
// 명세 §B/§C. 물리/리메시 없음. 셰이더 1개 + DecalGeometry.
import * as THREE from 'three'
import { DecalGeometry } from 'three/examples/jsm/geometries/DecalGeometry.js'

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

// 부스 카메라 raycast 역투영 → 부품 표면 교점에 적색 emissive Decal 생성.
// peakXY = [nx, ny] (0..1, heatmap 좌표) · boothCam = PerspectiveCamera · target = 부품 mesh
// 반환: { decal, point, normal } 또는 null.
export function buildDecal(target, boothCam, peakXY, heatTex, size = 0.34) {
  if (!target || !boothCam || !peakXY) return null
  // heatmap 정규좌표(좌상단 원점) → NDC(중앙 원점, y 뒤집힘)
  const ndc = new THREE.Vector2(peakXY[0] * 2 - 1, -(peakXY[1] * 2 - 1))
  const rc = new THREE.Raycaster()
  rc.setFromCamera(ndc, boothCam)
  const hit = rc.intersectObject(target, false)[0]
  if (!hit) return null

  const normal = hit.face
    ? hit.face.normal.clone().transformDirection(target.matrixWorld)
    : new THREE.Vector3(0, 1, 0)
  const helper = new THREE.Object3D()
  helper.position.copy(hit.point)
  helper.lookAt(hit.point.clone().add(normal))

  const geo = new DecalGeometry(target, hit.point, helper.rotation,
    new THREE.Vector3(size, size, size))
  const mat = new THREE.MeshStandardMaterial({
    map: heatTex || null, emissiveMap: heatTex || null,
    emissive: 0xff3344, emissiveIntensity: heatTex ? 1.0 : 0.85,
    color: heatTex ? 0xffffff : 0xff3344,
    transparent: true, opacity: 0.95, depthTest: true, depthWrite: false,
    polygonOffset: true, polygonOffsetFactor: -4,
  })
  const decal = new THREE.Mesh(geo, mat)
  return { decal, point: hit.point.clone(), normal }
}
