// partShapes — 검사 시편 형상을 "현재 라인 클래스"에서 결정(임의 기어/실린더 금지).
// 표면 클래스 = 평면 슬랙(relief), 부품 클래스 = 프록시, 금속 = metalness~0.8.
// 클래스: MVTec(bottle/capsule/carpet/...) + products/(dowel/foam/cable_gland/potato).

const SURFACE = new Set(['carpet', 'tile', 'leather', 'wood', 'grid', 'foam'])
const METAL   = new Set(['metal_nut', 'screw', 'cable_gland', 'transistor', 'metal_plate'])
const ROUND   = new Set(['bottle', 'capsule', 'pill', 'dowel', 'potato', 'hazelnut', 'toothbrush'])

// 클래스명 → { kind, render, args, color, metalness, roughness }
export function classShape(nameRaw) {
  const name = String(nameRaw || '').toLowerCase().trim()

  if (SURFACE.has(name)) {
    return { kind: 'surface', render: 'slab', args: [0.42, 0.05, 0.42],
      color: surfaceColor(name), metalness: 0.05, roughness: 0.95 }
  }
  if (METAL.has(name)) {
    const round = name === 'metal_nut' || name === 'cable_gland'
    return round
      ? { kind: 'part', render: 'cylinder', args: [0.16, 0.16, 0.12, 6], color: '#c2c8d2', metalness: 0.85, roughness: 0.22 }
      : { kind: 'part', render: 'box', args: [0.12, 0.30, 0.12], color: '#c2c8d2', metalness: 0.85, roughness: 0.22 }
  }
  if (ROUND.has(name)) {
    if (name === 'bottle') return { kind: 'part', render: 'cylinder', args: [0.13, 0.15, 0.34, 20], color: '#7fae9a', metalness: 0.15, roughness: 0.4 }
    if (name === 'capsule' || name === 'pill') return { kind: 'part', render: 'capsule', args: [0.10, 0.20, 6, 14], color: '#d8b25a', metalness: 0.1, roughness: 0.5 }
    if (name === 'dowel') return { kind: 'part', render: 'cylinder', args: [0.09, 0.09, 0.34, 16], color: '#b08d57', metalness: 0.1, roughness: 0.7 }
    return { kind: 'part', render: 'capsule', args: [0.13, 0.16, 6, 12], color: '#c8a06a', metalness: 0.1, roughness: 0.65 }   // potato/hazelnut/toothbrush 프록시
  }
  // 기타(cable/zipper/screw 외) — 박스 프록시
  return { kind: 'part', render: 'box', args: [0.30, 0.30, 0.30], color: '#9aa6b8', metalness: 0.35, roughness: 0.5 }
}

function surfaceColor(name) {
  return ({ carpet: '#8a6f5a', tile: '#cdd3da', leather: '#6e4a39', wood: '#a9824f', grid: '#7c8694', foam: '#d9d2c2' })[name] || '#9aa6b8'
}

// 시편의 상단 표면 높이(스캔 bbox·decal 참조용) — render별 반높이
export function halfHeight(shape) {
  switch (shape.render) {
    case 'slab':     return shape.args[1] / 2
    case 'cylinder': return shape.args[2] / 2
    case 'capsule':  return shape.args[1] / 2 + shape.args[0]
    default:         return shape.args[1] / 2
  }
}
