import axios from 'axios'

// ────────────────────────────────────────────────────────────────
//  Axios 인스턴스
//  - 개발: Vite proxy → localhost:8000 (vite.config.js 참조)
//  - 배포: VITE_API_URL 환경변수로 지정
//  ※ baseURL='' 이면 /api/... 요청이 Vite proxy를 통해 자동 포워딩
// ────────────────────────────────────────────────────────────────
const BASE_URL = import.meta.env.VITE_API_URL || ''

const api = axios.create({
  baseURL: BASE_URL,
  timeout: 600_000, // 10분 (VLM 추론 대기)
  headers: {
    'Content-Type': 'application/json',
  },
})

// ── Request 인터셉터 (필요 시 JWT 토큰 주입 가능) ──
api.interceptors.request.use((config) => {
  return config
}, (error) => Promise.reject(error))

// ── Response 인터셉터 (공통 에러 처리) ──
api.interceptors.response.use(
  (response) => response,
  (error) => {
    let msg
    if (error.code === 'ERR_NETWORK' || error.message === 'Network Error') {
      msg = '백엔드 서버에 연결할 수 없습니다. 서버가 실행 중인지 확인하세요.'
    } else if (error.code === 'ECONNABORTED') {
      msg = '요청 시간 초과 (VLM 추론 중). 잠시 후 다시 시도하세요.'
    } else {
      msg = error?.response?.data?.detail || error.message || 'Unknown error'
    }
    console.error('[API Error]', error.code, msg)
    return Promise.reject(new Error(msg))
  }
)

// ────────────────────────────────────────────────────────────────
//  API 함수들
// ────────────────────────────────────────────────────────────────

/**
 * 이미지 결함 분석 요청
 * @param {File} file - 업로드할 이미지 파일
 * @param {boolean} auto - Auto Scout 모드 여부
 * @returns {Promise<object>} - 분석 결과
 */
export async function analyzeImage(file, auto = false) {
  const form = new FormData()
  form.append('file', file)
  const url = auto ? '/api/analyze?auto=true' : '/api/analyze'
  const { data } = await api.post(url, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

/**
 * 학습용 ZIP 파일 업로드
 * @param {File} file - 업로드할 ZIP 파일
 * @returns {Promise<object>} - { run_id, n_images, classes, status }
 */
export async function uploadTraining(file) {
  const form = new FormData()
  form.append('file', file)
  const { data } = await api.post('/api/train/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

/**
 * 에이전트 시스템 상태 조회
 * @returns {Promise<object>} - { agent: { score, threshold, status }, session, memory }
 */
export async function fetchState() {
  const { data } = await api.get('/api/state')
  return data
}

/**
 * 하드웨어 텔레메트리 상태 조회
 * @returns {Promise<object>} - { ts, cuda_available, gpus: [{index, name, util_pct, vram_used_mb, vram_total_mb, temp_c}], cpu_pct, ram_used_mb, ram_total_mb }
 */
export async function fetchHardware() {
  const { data } = await api.get('/api/hardware')
  return data
}

/**
 * 에이전트 제어 액션 전송
 * @param {'emergency_stop'|'approve'|'resume'} action
 * @returns {Promise<object>}
 */
export async function sendAction(action) {
  const { data } = await api.post('/api/action', { action })
  return data
}

/**
 * Quick Launch: 에이전트 채팅 메시지 전송 (HTTP 폴백)
 * @param {string} message
 * @param {string|null} imagePath
 * @returns {Promise<object>}
 */
export async function sendChatHttp(message, imagePath = null) {
  const { data } = await api.post('/api/chat', { message, image_path: imagePath })
  return data
}

/**
 * 에이전트들의 실시간 상태 스냅샷 조회
 * @returns {Promise<object>}
 */
export async function fetchAgentsStatus() {
  const { data } = await api.get('/api/agents/status')
  return data
}

/**
 * WebSocket URL 반환
 * @returns {string}
 */
export function getWebSocketUrl() {
  // Vite proxy를 통해 현재 호스트의 /ws/chat으로 연결
  if (BASE_URL === '') {
    const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${wsProto}//${window.location.host}/ws/chat`
  }
  const wsProto = BASE_URL.startsWith('https') ? 'wss:' : 'ws:'
  const host = BASE_URL.replace(/^https?:\/\//, '')
  return `${wsProto}//${host}/ws/chat`
}

/**
 * 시뮬레이션 합성 데이터셋 업로드 요청 (good/defect 분리)
 * @param {string[]} images - base64 PNG 데이터 URL 배열
 * @param {number} defectRatio - 결함 이미지 합성 비율 (0.0 ~ 1.0)
 * @returns {Promise<object>} - { run_id, n_images, classes: {good, defect}, work_dir }
 */
export async function uploadSimDataset(images, defectRatio = 0.3) {
  const { data } = await api.post('/api/sim/dataset', { images, defect_ratio: defectRatio })
  return data
}

/**
 * 데이터셋 인테이크 요청 (ZIP/TAR)
 * @param {File} file - 업로드할 ZIP 또는 TAR 파일
 * @returns {Promise<object>} - { run_id, n_images, classes, resolution, domain }
 */
export async function intakeDataset(file) {
  const form = new FormData()
  form.append('file', file)
  const { data } = await api.post('/api/dataset/intake', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

/**
 * 시뮬레이션 환경 내 학습 시작 요청
 * @param {string} runId - 인테이크 시 발급받은 run_id
 * @returns {Promise<object>} - { ok, run_id }
 */
export async function simTrain(runId) {
  const { data } = await api.post('/api/sim/train', { run_id: runId })
  return data
}

/**
 * 시뮬레이션 환경 내 검증 시작 요청
 * @param {string} runId - 인테이크 시 발급받은 run_id
 * @returns {Promise<object>} - 검증 통계 결과
 */
export async function simValidate(runId) {
  const { data } = await api.post('/api/sim/validate', { run_id: runId })
  return data
}

export async function classTrain(classId, mvtecPath) {
  const { data } = await api.post('/api/class/train', { classId, mvtec_path: mvtecPath })
  return data
}

export async function classValidate(classId, mvtecPath) {
  const { data } = await api.post('/api/class/validate', { classId, mvtec_path: mvtecPath })
  return data
}

export async function mvtecScan(root) {
  const { data } = await api.get(`/api/mvtec/scan?root=${encodeURIComponent(root)}`)
  return data
}

export async function classSamples(classId, mvtec_path) {
  const { data } = await api.get(`/api/class/samples?classId=${encodeURIComponent(classId)}&mvtec_path=${encodeURIComponent(mvtec_path)}`)
  return data
}

export default api

