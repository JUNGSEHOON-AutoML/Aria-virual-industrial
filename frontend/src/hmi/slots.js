// 슬롯 플러그인 레지스트리 — registerPanel(slot, component)로 끼우고 getPanel(slot)로 읽음.
// 다음 변경은 "갈아엎기"가 아니라 슬롯 교체로 끝낸다(스펙 §3 플러그인 패턴).
const registry = {}

export const SLOTS = [
  'topbar', 'kpi_bar', 'left_panel', 'viewport',
  'right_panel', 'bottom_panel', 'button_panel', 'settings_drawer',
]

export function registerPanel(slot, component) {
  if (!SLOTS.includes(slot)) console.warn(`[slots] 알 수 없는 slot: ${slot}`)
  registry[slot] = component
  return component
}

export function getPanel(slot) { return registry[slot] || null }
export function clearPanels() { for (const k of Object.keys(registry)) delete registry[k] }
