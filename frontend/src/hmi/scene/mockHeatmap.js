// mockHeatmap — Standalone(Mock) 폴백용 합성 2D 검사 데이터.
// 명세 §2: verdict만 난수로 찍지 말고 "2D 히트맵을 만들어" §3의 동일 raycast를 태운다.
// 핵심: 3D 결함 위치는 여기서 만든 2D blob(defect_xy)에서 *유도*된다(난수 3D 좌표 아님).
// part_id 해시로 결정적 — 같은 부품이면 같은 위치(재현성, placeholder 표기).

function hash01(str, salt = 0) {
  let h = 2166136261 ^ salt
  const s = String(str || 'P0')
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619) }
  return ((h >>> 0) % 10000) / 10000
}

// 합성 원본 + heatmap 캔버스 + peak 좌표. score/verdict는 인자로 받아(난수 금지) 표현만.
export function makeMockInspection(partId, score = 0.42, tau = 0.5) {
  const W = 192, H = 192
  // 결함 blob 위치 — part_id 해시(결정적), 가장자리 회피
  const nx = 0.18 + hash01(partId, 1) * 0.64
  const ny = 0.18 + hash01(partId, 2) * 0.64
  const px = nx * W, py = ny * H
  const ng = score >= tau   // anomaly score=낮을수록 정상, ≥τ=NG (로직 불변)

  // 원본(합성 표면)
  const base = document.createElement('canvas'); base.width = W; base.height = H
  const bx = base.getContext('2d')
  const g = bx.createRadialGradient(W / 2, H / 2, 20, W / 2, H / 2, 140)
  g.addColorStop(0, '#b9c2d0'); g.addColorStop(1, '#5d6977')
  bx.fillStyle = g; bx.fillRect(0, 0, W, H)
  for (let i = 0; i < 2200; i++) { const v = 110 + Math.random() * 80; bx.fillStyle = `rgba(${v},${v + 6},${v + 14},0.22)`; bx.fillRect(Math.random() * W, Math.random() * H, 2, 2) }
  bx.strokeStyle = 'rgba(40,52,70,0.55)'; bx.lineWidth = 7; bx.strokeRect(14, 14, W - 28, H - 28)
  // 결함 얼룩
  const dr = bx.createRadialGradient(px, py, 2, px, py, 22)
  dr.addColorStop(0, 'rgba(28,20,24,0.8)'); dr.addColorStop(1, 'rgba(60,55,60,0)')
  bx.fillStyle = dr; bx.beginPath(); bx.arc(px, py, 22, 0, 7); bx.fill()

  // heatmap(적색 가우시안)
  const heat = document.createElement('canvas'); heat.width = W; heat.height = H
  const hx = heat.getContext('2d')
  const hr = hx.createRadialGradient(px, py, 2, px, py, 34)
  hr.addColorStop(0, ng ? 'rgba(255,40,40,0.95)' : 'rgba(255,170,40,0.75)')
  hr.addColorStop(0.5, 'rgba(255,90,40,0.4)')
  hr.addColorStop(1, 'rgba(255,40,40,0)')
  hx.fillStyle = hr; hx.fillRect(0, 0, W, H)

  return {
    image_b64: base.toDataURL('image/jpeg', 0.6),
    heatmap_b64: heat.toDataURL('image/png'),
    defect_xy: [Number(nx.toFixed(4)), Number(ny.toFixed(4))],
    _mock: true,
  }
}
