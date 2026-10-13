import { create } from 'zustand'
export const useSelection = create(set => ({
  selected: null, preset: 'SITE_OVERVIEW', cameraRequest: 0,
  select: selected => set(s => ({ selected, preset: null, cameraRequest: s.cameraRequest + 1 })),
  setPreset: preset => set(s=>({selected:null,preset,cameraRequest:s.cameraRequest+1})),
  overview: () => set(s => ({ selected: null, preset:'SITE_OVERVIEW', cameraRequest: s.cameraRequest + 1 })),
}))
