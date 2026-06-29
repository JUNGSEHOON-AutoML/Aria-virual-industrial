// uiMode 컨텍스트 — AppShell이 provide, 패널들이 consume.
// 'operator': KPI 4 + 간결 우/하단  |  'expert': 전체 콕핏
import { createContext, useContext } from 'react'
export const UIModeContext = createContext('operator')
export const useUiMode = () => useContext(UIModeContext)
