// 계층(Plant→Line→Station) 구조 소스 — factory_scene.json이 없으므로 여기서 못 박는다.
//  Lines  = mvtecScan 클래스 (비면 DEFAULT_LINES 폴백 → 트리 절대 안 빔)
//  Stations = factory.jsx 라인 구조에서 뽑은 정적 템플릿
// 순수 모듈(Node 검증 가능). R3F/three 미import.

export const DATA_ROOT = '/userHome/userhome4/sehoon/ARIArefactored/data'
export const DEFAULT_LINES = ['bottle', 'cable', 'capsule']
export const STATION_TEMPLATE = ['Infeed conveyor', 'Inspection gate', 'Sort bins (OK/NG)', 'Vision node']

export function buildHierarchy(classes) {
  const lines = (classes && classes.length) ? classes : DEFAULT_LINES
  return {
    id: 'plant', name: 'ARIA Factory', type: 'plant',
    children: lines.map(c => ({
      id: `line:${c}`, name: c, type: 'line', classId: c,
      children: STATION_TEMPLATE.map(s => ({
        id: `station:${c}:${s}`, name: s, type: 'station', classId: c, station: s,
      })),
    })),
  }
}

// 트리 노드 id → 선택 컨텍스트(group,id) 매핑
export function nodeToSelection(node) {
  if (!node) return null
  if (node.type === 'line') return { group: 'line', id: node.classId }
  if (node.type === 'station' && node.station === 'Vision node') return { group: 'node', id: 'patchcore' }
  if (node.type === 'station') return { group: 'station', id: node.id, classId: node.classId, station: node.station }
  return { group: 'plant', id: 'plant' }
}
