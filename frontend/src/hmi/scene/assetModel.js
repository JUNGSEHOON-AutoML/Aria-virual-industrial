// assetModel.js — 설비 건전성(Asset Health) 파생 레이어.
// 원칙:
//  - 새 엔드포인트 없음. status·실측 지표는 기존 store 신호(kpi/scan)에서만 도출.
//  - temperature/vibration 등 라인에 센서 피드가 없는 값은 데모용 시뮬레이션 proxy(sim:true 표기).
//  - 물리/키네매틱스 아님. 표현·집계 레이어일 뿐.

// 3D 라벨 위치(머리 위) + 패널 메타. labelPos = [x, y, z]
export const ASSET_DEFS = [
  { id: 'robot_arm',      name: '로봇 팔',       kind: 'robot',  labelPos: [-6.2, 2.55, 1.4] },
  { id: 'vision_camera',  name: '비전 카메라',   kind: 'camera', labelPos: [0.0, 2.45, 0.0] },
  { id: 'conveyor_motor', name: '컨베이어 모터', kind: 'motor',  labelPos: [2.0, 1.45, 0.0] },
]

const STATUS_COLOR = { Running: '#34d399', Idle: '#9aa0aa', Warning: '#facc15', Error: '#f87171' }
const STATUS_KO    = { Running: '가동 중', Idle: '대기', Warning: '경고', Error: '오류' }
export const statusColor = s => STATUS_COLOR[s] || '#9aa0aa'
export const statusKo    = s => STATUS_KO[s] || s

// 결정적(시간 기반) 미세 변동 — 시뮬 센서값에 생동감
function wobble(seed, t, amp) {
  return Math.sin(t * 0.0011 + seed) * amp + Math.sin(t * 0.0007 + seed * 2.3) * amp * 0.4
}

// kpi/scan → 설비 3종의 건전성. nowMs = 시뮬 변동용 시간(performance.now 등).
export function deriveAssets(kpi = {}, scan = null, nowMs = 0) {
  const running  = String(kpi.state || '').toLowerCase().startsWith('run')
  const ack      = kpi.ack_max_ms ?? 0
  const inferP95 = kpi.infer_latency_p95_ms ?? 0
  const queue    = kpi.queue_depth ?? 0
  const drop     = kpi.drop_count ?? 0

  // ── 로봇 팔 — kpi.state 기반 ──
  const robotStatus = running ? 'Running' : 'Idle'

  // ── 비전 카메라 — 추론 지연 과다 시 경고(실측 신호 기반) ──
  let camStatus = running ? 'Running' : 'Idle'
  if (running && inferP95 > 80) camStatus = 'Warning'
  if (running && ack > 40) camStatus = 'Error'

  // ── 컨베이어 모터 — 드롭/백프레셔(실측 신호 기반) ──
  let motorStatus = running ? 'Running' : 'Idle'
  if (drop > 5) motorStatus = 'Error'
  else if (queue >= 4) motorStatus = 'Warning'

  return [
    {
      id: 'robot_arm', name: '로봇 팔', kind: 'robot', status: robotStatus,
      labelPos: ASSET_DEFS[0].labelPos,
      metrics: [
        { k: '온도', v: (38 + wobble(1, nowMs, 4) + (running ? 6 : 0)).toFixed(1), unit: '°C', sim: true },
        { k: '진동', v: (0.8 + Math.abs(wobble(2, nowMs, 0.5)) + (running ? 0.6 : 0)).toFixed(2), unit: 'mm/s', sim: true },
      ],
    },
    {
      id: 'vision_camera', name: '비전 카메라', kind: 'camera', status: camStatus,
      labelPos: ASSET_DEFS[1].labelPos,
      metrics: [
        { k: '추론 p95', v: inferP95.toFixed(0), unit: 'ms', sim: false },
        { k: 'ACK', v: ack.toFixed(1), unit: 'ms', sim: false },
        { k: '온도', v: (42 + wobble(3, nowMs, 3) + (running ? 8 : 0)).toFixed(1), unit: '°C', sim: true },
      ],
    },
    {
      id: 'conveyor_motor', name: '컨베이어 모터', kind: 'motor', status: motorStatus,
      labelPos: ASSET_DEFS[2].labelPos,
      metrics: [
        { k: '큐', v: `${queue}/4`, unit: '', sim: false },
        { k: '드롭', v: `${drop}`, unit: '', sim: false },
        { k: '진동', v: (1.1 + Math.abs(wobble(5, nowMs, 0.6)) + (running ? 0.5 : 0)).toFixed(2), unit: 'mm/s', sim: true },
      ],
    },
  ]
}

// 결함(Warning/Error) 설비만 추림 — 패널 상단 요약용
export function faultyAssets(assets) {
  return assets.filter(a => a.status === 'Error' || a.status === 'Warning')
}
