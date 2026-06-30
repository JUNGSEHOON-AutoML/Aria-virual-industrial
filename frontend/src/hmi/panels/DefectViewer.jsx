// DefectViewer — 학습 후 MVTec 결함을 360° 회전 3D로 확인. 데이터셋 결함 위치를 직접 검수.
// 데이터셋 NG 샘플(class/samples) → analyze_path로 실 heatmap → 3D 부품에 relief + 2D 원본/heatmap.
import { useEffect, useState, useMemo } from 'react'
import { Box, Typography, Button, IconButton } from '@mui/material'
import { Canvas } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import { classSamples, analyzePath } from '../../api/apiClient'
import { DATA_ROOT } from '../sceneModel'
import { classShape } from '../scene/partShapes'
import { heightTexFromDataURI } from '../scene/inspectVfx'
import ReliefPatch from '../scene/ReliefPatch'

function PartModel({ className, heightTex, score }) {
  const shape = useMemo(() => classShape(className), [className])
  const half = (shape.args[1] || shape.args[2] || 0.3) / 2
  return (
    <group>
      <mesh castShadow>
        {shape.render === 'cylinder' && <cylinderGeometry args={shape.args} />}
        {shape.render === 'capsule' && <capsuleGeometry args={shape.args} />}
        {(shape.render === 'box' || shape.render === 'slab') && <boxGeometry args={shape.args} />}
        <meshStandardMaterial color={shape.color} metalness={shape.metalness} roughness={shape.roughness} />
      </mesh>
      {heightTex && (
        <ReliefPatch heightTex={heightTex} size={Math.max(half, 0.16) * 2.4}
          position={[0, half + 0.01, 0]} score={score ?? 0.6} />
      )}
    </group>
  )
}

export default function DefectViewer({ open, onClose, category = 'bottle' }) {
  const [items, setItems] = useState([])
  const [idx, setIdx] = useState(0)
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(false)
  const [mode, setMode] = useState('overlay')

  // 열릴 때 NG 샘플 로드
  useEffect(() => {
    if (!open) return
    setData(null); setIdx(0)
    classSamples(category, `${DATA_ROOT}/${category}`)
      .then(r => { if (r?.ok) setItems((r.items || []).filter(it => it.label === 'NG')) })
      .catch(() => {})
  }, [open, category])

  // 현재 샘플 분석(실 heatmap)
  useEffect(() => {
    if (!open || !items.length) return
    const it = items[idx]; if (!it?.path) return
    setBusy(true); setData(null)
    analyzePath(category, it.path)
      .then(r => { if (r?.ok) setData(r) })
      .catch(() => {})
      .finally(() => setBusy(false))
  }, [open, items, idx, category])

  const heightTex = useMemo(
    () => (data?.heatmap_b64 ? heightTexFromDataURI(data.heatmap_b64) : null),
    [data?.heatmap_b64])

  if (!open) return null
  const it = items[idx]

  return (
    <Box sx={{ position: 'fixed', inset: 0, zIndex: 40, display: 'flex', alignItems: 'center',
      justifyContent: 'center', bgcolor: 'rgba(6,9,14,0.86)', backdropFilter: 'blur(2px)',
      fontFamily: "'Courier New',monospace" }}>
      <Box sx={{ width: 'min(900px, 94%)', height: 'min(560px, 88%)', bgcolor: '#0d1320',
        border: '1px solid #1FB8CD', borderRadius: 2, p: 2, display: 'flex', flexDirection: 'column' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
          <Typography sx={{ fontSize: 14, color: '#1FB8CD', letterSpacing: 0.5 }}>
            결함 3D 뷰어 · {category} — 360° 회전으로 결함 위치 검수
          </Typography>
          <IconButton size="small" onClick={onClose} sx={{ ml: 'auto', color: '#6b7280' }}>✕</IconButton>
        </Box>

        {!items.length ? (
          <Box sx={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#6b7280' }}>
            NG 샘플 로드 중… (학습된 클래스의 test 결함 이미지)
          </Box>
        ) : (
          <Box sx={{ flex: 1, display: 'grid', gridTemplateColumns: '1fr 300px', gap: 2, minHeight: 0 }}>
            {/* 좌: 360° 회전 3D 부품 + 결함 relief */}
            <Box sx={{ position: 'relative', borderRadius: 1.5, overflow: 'hidden',
              border: '1px solid rgba(255,255,255,0.1)', background: '#070b12' }}>
              <Canvas shadows camera={{ position: [0.6, 0.5, 0.8], fov: 45 }}>
                <color attach="background" args={['#070b12']} />
                <ambientLight intensity={0.7} />
                <hemisphereLight skyColor="#cfe0ff" groundColor="#141a26" intensity={0.6} />
                <directionalLight position={[2, 3, 2]} intensity={1.4} castShadow />
                <directionalLight position={[-2, 1, -1]} intensity={0.4} color="#4a6090" />
                <PartModel className={category} heightTex={heightTex} score={data?.score} />
                <OrbitControls autoRotate autoRotateSpeed={2.2} enableDamping
                  minDistance={0.5} maxDistance={2.5} />
              </Canvas>
              <Box sx={{ position: 'absolute', bottom: 8, left: 10, fontSize: 9, color: '#5b6677' }}>
                드래그로 회전 · 자동 360° 회전 중{busy ? ' · 분석 중…' : ''}
              </Box>
            </Box>

            {/* 우: 2D 원본/heatmap + 정보 + 네비 */}
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1, minHeight: 0 }}>
              <Box sx={{ position: 'relative', width: '100%', aspectRatio: '1/1', borderRadius: 1.5,
                overflow: 'hidden', border: '1px solid rgba(255,255,255,0.1)', background: '#05080e' }}>
                {it?.url && <img src={it.url} alt="" style={{ position: 'absolute', inset: 0,
                  width: '100%', height: '100%', objectFit: 'cover', opacity: mode === 'heat' ? 0.15 : 1 }} />}
                {data?.heatmap_b64 && (mode === 'heat' || mode === 'overlay') && (
                  <img src={data.heatmap_b64} alt="" style={{ position: 'absolute', inset: 0,
                    width: '100%', height: '100%', objectFit: 'cover', mixBlendMode: 'screen' }} />)}
              </Box>
              <Box sx={{ display: 'flex', gap: 0.6 }}>
                {[['base', '원본'], ['heat', 'heatmap'], ['overlay', 'overlay']].map(([m, l]) => (
                  <Button key={m} size="small" variant={mode === m ? 'contained' : 'outlined'}
                    onClick={() => setMode(m)} sx={{ flex: 1, fontSize: 9, minHeight: 28 }}>{l}</Button>
                ))}
              </Box>
              <Box sx={{ fontSize: 11, color: '#cbd5e1', lineHeight: 1.7 }}>
                <div>결함: <span style={{ color: '#facc15' }}>{it?.defect || '—'}</span></div>
                <div>판정: <span style={{ color: data?.verdict === 'NG' ? '#f87171' : '#34d399' }}>
                  {data?.verdict || '…'}</span> · score {data?.score != null ? data.score.toFixed(3) : '…'} / τ {data?.tau ?? 0.5}</div>
                {Array.isArray(data?.defect_xy) && (
                  <div style={{ color: '#9aa3b2' }}>위치 (u,v)=({data.defect_xy[0].toFixed(2)}, {data.defect_xy[1].toFixed(2)})</div>
                )}
              </Box>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 'auto' }}>
                <Button size="small" variant="outlined" onClick={() => setIdx(i => Math.max(0, i - 1))}
                  disabled={idx === 0} sx={{ minHeight: 32 }}>◀ 이전</Button>
                <Typography sx={{ fontSize: 10, color: '#6b7280' }}>{idx + 1} / {items.length}</Typography>
                <Button size="small" variant="outlined" onClick={() => setIdx(i => Math.min(items.length - 1, i + 1))}
                  disabled={idx >= items.length - 1} sx={{ minHeight: 32 }}>다음 ▶</Button>
              </Box>
            </Box>
          </Box>
        )}
      </Box>
    </Box>
  )
}
