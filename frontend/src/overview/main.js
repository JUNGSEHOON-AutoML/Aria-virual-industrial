import tokens from '../brand/cnotta.tokens.json'
import layout from '../campus/campus.layout.json'
import progress from '../../../docs/autopilot/PROGRESS.md?raw'
import sceneGate from '../../../docs/autopilot/gates/m7-scene.json'
import fullGate from '../../../docs/autopilot/gates/m7.json'
import report from '../../../docs/autopilot/M7_REPORT.md?raw'
import './style.css'

const flat = {...tokens, ...Object.fromEntries(Object.entries(tokens.brand).map(([k,v]) => [`brand-${k}`,v]))}
for (const [key,value] of Object.entries(flat)) if (typeof value === 'string') document.documentElement.style.setProperty(`--${key}`,value)
const $ = selector => document.querySelector(selector)
const make = (tag, text, className) => {
  const element = document.createElement(tag)
  if (text !== undefined) element.textContent = text
  if (className) element.className = className
  return element
}
fetch('/brand/identity.json').then(r => {if (!r.ok) throw new Error('brand'); return r.json()}).then(brand => {$('#brand-mark').src = brand.mark}).catch(() => {$('#brand-mark').hidden = true})

const halls = layout.sites.filter(site => site.kind === 'inspection_hall')
let selected = halls[0].id
let campus = null
const labels = {coreset:'코어셋',ccifps:'CCIFPS',random_same_k:'random_same_k'}
for (const hall of halls) {
  const button = make('button', undefined, 'hall')
  button.type = 'button'
  button.dataset.hall = hall.id
  button.setAttribute('aria-pressed','false')
  button.append(make('span','CNOTTA','hall-brand'),make('strong',hall.name),make('span',`${hall.lanes.length} MODEL LANES`,'hall-lanes'))
  button.addEventListener('click',() => {selected = hall.id; renderHall()})
  $('#halls').append(button)
}
function renderHall() {
  const hall = halls.find(site => site.id === selected)
  $('#hall-name').textContent = hall.name
  $('#hall-position').textContent = `배치 원점 (${hall.origin.join(', ')}) ${layout.units} · 회전 ${hall.rotation} rad · 설계값 assumed`
  for (const button of document.querySelectorAll('[data-hall]')) button.setAttribute('aria-pressed',String(button.dataset.hall === selected))
  $('#lane-list').replaceChildren()
  for (const selector of hall.lanes) {
    const lane = campus?.sites.find(site => site.id === selected)?.lanes.find(l => l.selector === selector)
    const item = make('li')
    const label = make('div')
    label.append(make('b',labels[selector]),make('small',lane?.run ? `실행 ${lane.run.run_id}` : '동일 조건의 저장 실행'))
    const ready = lane?.status === 'ready'
    item.append(label,make('span',lane ? ready ? '준비됨' : '대기' : '미확인',`lane-status ${ready ? 'ready' : ''}`))
    $('#lane-list').append(item)
  }
}
renderHall()

async function refresh() {
  $('#refresh').disabled = true
  $('#connection').textContent = '읽기 전용 API 확인 중…'
  try {
    const response = await fetch('/api/dt/campus',{cache:'no-store',signal:AbortSignal.timeout(15000)})
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const data = await response.json()
    if (!Array.isArray(data.sites) || !Number.isInteger(data.ready_lanes)) throw new Error('응답 형식 오류')
    campus = data
    $('#ready-count').textContent = `${data.ready_lanes} / ${halls.reduce((n,h) => n+h.lanes.length,0)} 레인 준비`
    $('#study-status').textContent = data.full_study_ready ? '검증 완료 결과 연결 가능' : '실험 완료·검증 대기'
    $('#connection').textContent = `/api/dt/campus · ${new Date().toLocaleString('ko-KR')} 조회`
    $('#gate-note').textContent = `현재 API: ${data.ready_lanes}개 레인 준비. 기존 M7 전체 게이트는 ${fullGate.checks.nine_lanes.ready}/${fullGate.checks.nine_lanes.required}개 시점의 ${fullGate.status} 기록이며, 이번 조회로 재검증 통과를 선언하지 않습니다.`
  } catch (error) {
    campus = null
    $('#ready-count').textContent = '확인 불가'
    $('#study-status').textContent = '확인 불가'
    $('#connection').textContent = `API 연결을 확인하세요 (${error.message}). 아래 구현 설명은 저장된 문서 기준입니다.`
    $('#gate-note').textContent = '현재 API 상태는 확인할 수 없습니다. 기존 M7 게이트 기록과 아래 구현 설명은 그대로 보존됩니다.'
  } finally {renderHall(); $('#refresh').disabled = false}
}
$('#refresh').addEventListener('click',refresh)
refresh()

const names = {M0:'기반 준비',M1:'장면·브랜드',M2:'저장 결과 재생',L1:'비전 분석',M7:'캠퍼스',G1:'움직임 엔진',G2:'하류 물류',L2:'실시간 운영 연결',L3:'에이전트 작업',L4:'4족 순찰',V1:'2.5D 결함 뷰어',V2:'실측 3D 뷰어',V3:'부품 외형',M3:'선택·검색',M4:'KPI·재검사 패널',G3:'수치 출처',M5:'본 실험 결과 연결',M6:'데모 패키징'}
const rows = progress.split('\n').map(line => line.split('|').map(cell => cell.trim())).filter(row => names[row[0]])
const implemented = new Set(['M0','M1','M2','L1','M7','M3','M4','M6'])
for (const [id,status,gate,next] of rows) {
  const details = make('details', undefined, 'milestone')
  details.dataset.category = implemented.has(id) ? 'implemented' : 'pending'
  // M7's saved progress can lag the read-only catalog: keep gate evidence distinct.
  const shownStatus = id === 'M7' ? '화면 자동 게이트 통과 · 전체 데이터 게이트는 이전 기록' : status
  const summary = make('summary')
  summary.append(make('span',id,'stage-id'),make('b',names[id]),make('span',shownStatus,'stage-status'))
  const body = make('div',undefined,'stage-body')
  body.append(make('p',id === 'M5' ? '완료된 전체 실험의 REPORT와 대조한 뒤 최종 요약을 연결합니다. 기존 어댑터·결과 미완료 처리는 구현되어 있습니다.' : next))
  if (['M3','M4','M6'].includes(id)) body.append(make('p','기존 Replay 기준 완료입니다. 새 운영·물류 기능 연결 후 재검증합니다.'))
  body.append(make('code',`출처: docs/autopilot/PROGRESS.md · ${gate}`))
  details.append(summary,body)
  $('#milestones').append(details)
}
for (const filter of document.querySelectorAll('[data-filter]')) filter.addEventListener('click',() => {
  for (const button of document.querySelectorAll('[data-filter]')) button.setAttribute('aria-pressed',String(button === filter))
  for (const row of document.querySelectorAll('.milestone')) row.hidden = filter.dataset.filter !== 'all' && row.dataset.category !== filter.dataset.filter
})

const checks = sceneGate.checks
const evidence = [
  [sceneGate.pass ? '통과' : '미통과','M7 화면 자동 게이트','m7-scene.json · 실제 GPU 미확인'],
  [`${Math.min(...checks.roof_wordmark.glyph_heights_px).toFixed(1)} px`,'지붕 워드마크 최소 글자 높이',`${checks.viewport.measured.join(' × ')} · m7-scene.json`],
  [report.match(/\| 백엔드 전체 \| ([^|]+) \|/)?.[1]?.trim() || '기록 확인 필요','이전 백엔드 검증 기록','M7_REPORT.md · 이번 안내 작업에서 재실행하지 않음'],
  [report.match(/\| 골든 트레이스 \| ([^|]+) \|/)?.[1]?.trim() || '기록 확인 필요','이전 골든 트레이스 기록','M7_REPORT.md · 계산 엔진 변경 없음'],
]
for (const [value,label,source] of evidence) {
  const card = make('article')
  card.append(make('strong',value),make('h3',label),make('small',source))
  $('#evidence-cards').append(card)
}
$('#evidence-date').textContent = `화면 게이트 측정 시각: ${new Date(sceneGate.at).toLocaleString('ko-KR')} · 본 페이지는 기존 검증 결과를 인용합니다.`
