// AppShell — MUI7 슬롯 레이아웃.
// S1: 레거시 탭 없음(App.jsx에서 이미 제거).
// S2: uiMode(operator|expert) + [운영|전문가] 토글.
// S3: 패널별 모드 인식은 uiMode Context 경유.
// S4: isMobile(<900px) → flex-column 레이아웃, 3D 주연.
import { useEffect, useState } from 'react'
import {
  ThemeProvider, createTheme, CssBaseline, Box, AppBar, Toolbar, Typography,
  ToggleButton, ToggleButtonGroup, IconButton, Drawer, Tabs, Tab, Chip,
  useMediaQuery,
} from '@mui/material'
import SettingsIcon from '@mui/icons-material/Settings'
import { useSignalStore } from './signalStore'
import { getPanel } from './slots'
import { UIModeContext } from './uiMode'
import './registerPanels'

const theme = createTheme({
  palette: {
    mode: 'dark',
    background: { default: '#0b0d12', paper: '#11141b' },
    primary: { main: '#1FB8CD' },
    success: { main: '#34d399' }, error: { main: '#f87171' }, warning: { main: '#facc15' },
    text: { primary: '#e2e8f0', secondary: '#9aa0aa' },
  },
  typography: { fontFamily: "'Courier New', ui-monospace, monospace", fontSize: 12 },
  shape: { borderRadius: 10 },
})

function Placeholder({ name }) {
  return (
    <Box sx={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center',
      color: '#4b5563', border: '1px dashed rgba(255,255,255,0.07)', borderRadius: 2,
      bgcolor: 'rgba(255,255,255,0.02)', fontSize: 11, letterSpacing: 1 }}>
      {name}
    </Box>
  )
}

// 슬롯 컴포넌트 편의 렌더러
function SlotRender({ name, fallback }) {
  const Comp = getPanel(name)
  return Comp ? <Comp /> : (fallback ?? <Placeholder name={name} />)
}

export default function AppShell() {
  const connect = useSignalStore(s => s.connect)
  const wsStatus = useSignalStore(s => s.wsStatus)
  const mode = useSignalStore(s => s.mode)
  const setMode = useSignalStore(s => s.setMode)
  const [drawer, setDrawer] = useState(false)
  const [tab, setTab] = useState(0)
  const [uiMode, setUiMode] = useState('operator')
  const isMobile = useMediaQuery('(max-width:900px)')

  useEffect(() => { connect() }, [connect])

  const isExpert = uiMode === 'expert'
  const SettingsPanel = getPanel('settings_drawer')

  // ── Topbar (공통) ─────────────────────────────────────────────────────────
  const Topbar = (
    <AppBar position="static" elevation={0}
      sx={{ bgcolor: 'rgba(255,255,255,0.03)', borderRadius: 2 }}>
      <Toolbar variant="dense" sx={{ minHeight: 44, gap: 1 }}>
        <Typography sx={{ color: 'primary.main', fontWeight: 700, letterSpacing: 1.5,
          fontSize: 13, whiteSpace: 'nowrap', mr: 0.5 }}>
          ARIA · DIGITAL TWIN
        </Typography>

        {/* Standalone / Live */}
        <ToggleButtonGroup size="small" exclusive value={mode}
          onChange={(_, v) => v && setMode(v)}>
          <ToggleButton value="standalone" sx={{ fontSize: 9, py: 0.2, px: 1, minHeight: 28 }}>
            STANDALONE
          </ToggleButton>
          <ToggleButton value="live" sx={{ fontSize: 9, py: 0.2, px: 1, minHeight: 28 }}>
            LIVE
          </ToggleButton>
        </ToggleButtonGroup>

        {/* Operator / Expert — S2 핵심 */}
        <ToggleButtonGroup size="small" exclusive value={uiMode}
          onChange={(_, v) => v && setUiMode(v)} sx={{ ml: 0.5 }}>
          <ToggleButton value="operator"
            sx={{ fontSize: 9, py: 0.2, px: 1.2, minHeight: 28,
              '&.Mui-selected': { bgcolor: 'rgba(52,211,153,0.12)', color: '#34d399' } }}>
            운영
          </ToggleButton>
          <ToggleButton value="expert"
            sx={{ fontSize: 9, py: 0.2, px: 1.2, minHeight: 28,
              '&.Mui-selected': { bgcolor: 'rgba(31,184,205,0.12)', color: '#1FB8CD' } }}>
            전문가
          </ToggleButton>
        </ToggleButtonGroup>

        <Box sx={{ flex: 1 }} />
        <Chip size="small" label={`WS ${wsStatus}`}
          color={wsStatus === 'open' ? 'success' : 'error'} variant="outlined"
          sx={{ fontSize: 10, height: 22 }} />
        <IconButton size="small" onClick={() => setDrawer(true)}
          sx={{ color: 'text.secondary', minWidth: 44, minHeight: 44 }}>
          <SettingsIcon fontSize="small" />
        </IconButton>
      </Toolbar>
    </AppBar>
  )

  // ── 데스크톱 그리드 — expert vs operator ─────────────────────────────────
  const expertGrid = {
    gridTemplateColumns: '180px 1fr 230px',
    gridTemplateRows: 'auto auto 1fr 210px',
    gridTemplateAreas: `
      "topbar topbar topbar"
      "kpi    kpi    kpi"
      "left   vp     right"
      "bottom bottom bottom"`,
  }
  const operatorGrid = {
    gridTemplateColumns: '1fr 200px',
    gridTemplateRows: 'auto auto 1fr 68px',
    gridTemplateAreas: `
      "topbar topbar"
      "kpi    kpi"
      "vp     right"
      "bottom bottom"`,
  }

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <UIModeContext.Provider value={uiMode}>

        {/* ── S4 모바일: flex-column ───────────────────────────────────── */}
        {isMobile ? (
          <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column',
            gap: 1, p: 1, boxSizing: 'border-box', bgcolor: 'background.default', overflow: 'hidden' }}>
            <Box sx={{ flexShrink: 0 }}>{Topbar}</Box>

            {/* KPI — 4개 compact */}
            <Box sx={{ flexShrink: 0, minHeight: 52 }}>
              <SlotRender name="kpi_bar" />
            </Box>

            {/* 3D 뷰포트 — 주연, 55vh */}
            <Box sx={{ flex: '0 0 55vh', minHeight: 0, borderRadius: 2, overflow: 'hidden',
              border: '1px solid rgba(255,255,255,0.06)' }}>
              <SlotRender name="viewport" />
            </Box>

            {/* 하단 스크롤 영역: right + bottom + actions */}
            <Box sx={{ flex: 1, minHeight: 0, overflowY: 'auto', display: 'flex',
              flexDirection: 'column', gap: 1 }}>
              <Box sx={{ minHeight: 90, p: 1, bgcolor: 'rgba(255,255,255,0.03)', borderRadius: 2 }}>
                <SlotRender name="right_panel" />
              </Box>
              <Box sx={{ minHeight: 56, p: 1, bgcolor: 'rgba(255,255,255,0.03)', borderRadius: 2 }}>
                <SlotRender name="bottom_panel" />
              </Box>
              <Box sx={{ minHeight: 100 }}>
                <SlotRender name="button_panel" />
              </Box>
            </Box>
          </Box>

        ) : (
        /* ── 데스크톱: CSS Grid ─────────────────────────────────────────── */
          <Box sx={{ height: '100%', display: 'grid', gap: 1, p: 1,
            boxSizing: 'border-box', bgcolor: 'background.default',
            ...(isExpert ? expertGrid : operatorGrid) }}>

            <Box sx={{ gridArea: 'topbar' }}>{Topbar}</Box>

            <Box sx={{ gridArea: 'kpi', minHeight: 0 }}>
              <SlotRender name="kpi_bar" />
            </Box>

            {/* left_panel — expert만 */}
            {isExpert && (
              <Box sx={{ gridArea: 'left', minHeight: 0, minWidth: 0 }}>
                <SlotRender name="left_panel" />
              </Box>
            )}

            <Box sx={{ gridArea: 'vp', minHeight: 0, borderRadius: 2, overflow: 'hidden',
              border: '1px solid rgba(255,255,255,0.06)' }}>
              <SlotRender name="viewport" />
            </Box>

            <Box sx={{ gridArea: 'right', minHeight: 0, minWidth: 0 }}>
              <SlotRender name="right_panel" />
            </Box>

            {/* bottom — operator: ticker+actions / expert: alarms+ECharts+actions */}
            <Box sx={{ gridArea: 'bottom', minHeight: 0, display: 'grid', gap: 1,
              gridTemplateColumns: isExpert ? '1fr 360px' : '1fr 180px' }}>
              <Box sx={{ minHeight: 0, bgcolor: isExpert ? 'transparent' : 'rgba(255,255,255,0.03)',
                borderRadius: 2, overflow: 'hidden' }}>
                <SlotRender name="bottom_panel" />
              </Box>
              <Box sx={{ minHeight: 0 }}>
                <SlotRender name="button_panel" />
              </Box>
            </Box>
          </Box>
        )}

        {/* Settings Drawer */}
        <Drawer anchor="right" open={drawer} onClose={() => setDrawer(false)}
          PaperProps={{ sx: { width: 380, bgcolor: 'background.paper', p: 2 } }}>
          <Typography sx={{ fontSize: 13, color: 'primary.main', mb: 1 }}>Settings</Typography>
          <Tabs value={tab} onChange={(_, v) => setTab(v)} variant="scrollable"
            sx={{ minHeight: 32, mb: 1 }}>
            {['Scene', 'Visual', 'Detector', 'Interfaces', 'AI'].map(t =>
              <Tab key={t} label={t} sx={{ fontSize: 10, minHeight: 32, py: 0 }} />)}
          </Tabs>
          {SettingsPanel ? <SettingsPanel tab={tab} /> :
            <Typography sx={{ fontSize: 11, color: 'text.secondary' }}>
              설정 항목은 전문가 모드에서 접근하세요.
            </Typography>}
        </Drawer>

      </UIModeContext.Provider>
    </ThemeProvider>
  )
}
