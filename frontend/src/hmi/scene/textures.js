// textures.js — 절차적 캔버스 텍스처(외부 에셋 0, AGPL/저작권 무관).
// 산업용 바닥 + 컨베이어 벨트 슬랫 패턴. CanvasTexture로 런타임 생성.
import * as THREE from 'three'

// 산업 콘크리트 바닥 — 미세 노이즈 + 타일 경계
export function makeFloorTexture() {
  const S = 512
  const c = document.createElement('canvas'); c.width = c.height = S
  const ctx = c.getContext('2d')

  // 베이스
  ctx.fillStyle = '#222c3d'
  ctx.fillRect(0, 0, S, S)

  // 거친 노이즈(콘크리트 질감)
  for (let i = 0; i < 2200; i++) {
    const x = Math.random() * S, y = Math.random() * S
    const g = 24 + Math.random() * 28
    ctx.fillStyle = `rgba(${g},${g + 8},${g + 20},0.45)`
    ctx.fillRect(x, y, 2, 2)
  }

  // 타일 경계선(각 텍스처 셀 = 1 타일)
  ctx.strokeStyle = 'rgba(120,150,195,0.16)'
  ctx.lineWidth = 3
  ctx.strokeRect(1.5, 1.5, S - 3, S - 3)

  const tex = new THREE.CanvasTexture(c)
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping
  tex.repeat.set(12, 4)
  tex.anisotropy = 4
  return tex
}

// 컨베이어 벨트 슬랫 — UV offset 스크롤용. X축으로 흐르는 가로 슬랫.
export function makeBeltTexture() {
  const W = 128, H = 64
  const c = document.createElement('canvas'); c.width = W; c.height = H
  const ctx = c.getContext('2d')

  ctx.fillStyle = '#1c2230'
  ctx.fillRect(0, 0, W, H)

  // 슬랫(가로 막대) — 흐를 때 진행 방향 인지
  const slat = 16
  for (let x = 0; x < W; x += slat) {
    ctx.fillStyle = '#2c3548'
    ctx.fillRect(x, 0, slat - 4, H)
    // 슬랫 사이 하이라이트
    ctx.fillStyle = 'rgba(130,160,200,0.22)'
    ctx.fillRect(x + slat - 4, 0, 2, H)
  }

  const tex = new THREE.CanvasTexture(c)
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping
  return tex
}
