// coordinateTransform — 2D(u,v)→3D(x,y,z) 단일 진입점 (F-08 정형화).
// sim = 카메라 raycast / real = K·[R|t] 역투영. 난수 금지: uv 없으면 ok:false.
// 입력 uv는 항상 정규 [0..1] (heatmap/이미지 좌표, 원점 좌상단).
import * as THREE from 'three'

// uv[0..1] → NDC (중앙 원점, y 뒤집힘)
function uvToNdc(uv) {
  return new THREE.Vector2(uv[0] * 2 - 1, -(uv[1] * 2 - 1))
}

// sim 경로: 카메라에서 raycast → 메시 표면 교점
function projectSim(uv, camera, mesh) {
  const rc = new THREE.Raycaster()
  rc.setFromCamera(uvToNdc(uv), camera)
  const hit = rc.intersectObject(mesh, false)[0]
  if (!hit) return { ok: false }
  const normal = hit.face
    ? hit.face.normal.clone().transformDirection(mesh.matrixWorld)
    : new THREE.Vector3(0, 1, 0)
  return { ok: true, point: hit.point.clone(), normal, mode: 'sim' }
}

// real 경로: K·[R|t]로 픽셀→월드 광선 → 메시 교차.
// calib = { K:[fx,fy,cx,cy], R:[9 row-major], t:[3], imgW, imgH }
function projectReal(uv, calib, mesh) {
  const { K, R, t, imgW, imgH } = calib || {}
  if (!K || !R || !t || !imgW || !imgH) return { ok: false }
  const [fx, fy, cx, cy] = K
  const px = uv[0] * imgW, py = uv[1] * imgH
  // 카메라 좌표계 광선 방향
  const dCam = new THREE.Vector3((px - cx) / fx, (py - cy) / fy, 1).normalize()
  // R(3x3) world→cam. 광선 월드 방향 = R^T · dCam, 카메라 중심 = -R^T · t
  const Rm = new THREE.Matrix3().fromArray(R)        // row-major
  const Rt = Rm.clone().transpose()
  const dWorld = dCam.clone().applyMatrix3(Rt).normalize()
  const tV = new THREE.Vector3(t[0], t[1], t[2])
  const origin = tV.clone().applyMatrix3(Rt).multiplyScalar(-1)
  const rc = new THREE.Raycaster(origin, dWorld)
  const hit = rc.intersectObject(mesh, false)[0]
  if (!hit) return { ok: false }
  const normal = hit.face
    ? hit.face.normal.clone().transformDirection(mesh.matrixWorld)
    : new THREE.Vector3(0, 1, 0)
  return { ok: true, point: hit.point.clone(), normal, mode: 'real' }
}

// 단일 진입점. mode='sim'|'real'. real 캘리브 없으면 sim 폴백(라벨용 fellBack 표시).
export function project2Dto3D({ uv, mode = 'sim', camera, mesh, calib } = {}) {
  if (!Array.isArray(uv) || !mesh) return { ok: false }     // 난수 금지: 입력 없으면 실패
  if (mode === 'real') {
    const r = projectReal(uv, calib, mesh)
    if (r.ok) return r
    // 캘리브 미설정/실패 → sim 폴백
    const s = projectSim(uv, camera, mesh)
    return s.ok ? { ...s, mode: 'sim', fellBack: true } : { ok: false }
  }
  return projectSim(uv, camera, mesh)
}
