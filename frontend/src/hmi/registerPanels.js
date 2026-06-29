// 슬롯에 실제 패널 등록 (M3). AppShell이 import하면 렌더 전에 등록됨.
import { registerPanel } from './slots'
import KpiBarPanel from './panels/KpiBarPanel'
import HierarchyPanel from './panels/HierarchyPanel'
import ViewportSlot from './panels/ViewportSlot'
import RightPanel from './panels/RightPanel'
import BottomPanel from './panels/BottomPanel'
import ActionBar from './panels/ActionBar'

registerPanel('kpi_bar', KpiBarPanel)
registerPanel('left_panel', HierarchyPanel)
registerPanel('viewport', ViewportSlot)
registerPanel('right_panel', RightPanel)
registerPanel('bottom_panel', BottomPanel)
registerPanel('button_panel', ActionBar)
