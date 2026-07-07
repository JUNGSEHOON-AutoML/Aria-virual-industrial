// left_panel 슬롯 — sceneModel + store.classes 로 Plant→Line→Station 트리. 클릭 → store.select.
import { useEffect, useState } from 'react'
import { Box, Typography } from '@mui/material'
import { useSignalStore } from '../signalStore'
import { buildHierarchy, nodeToSelection } from '../sceneModel'

const GROUPS_EXTRA = [
  { type: 'group', name: 'Detectors', children: [
    { id: 'det:patchcore', name: 'PatchCore', sel: { group: 'node', id: 'patchcore' } },
    { id: 'det:combined', name: 'PatchCore+YOLO', sel: { group: 'node', id: 'combined' } },
  ] },
  { type: 'group', name: 'Twin I/O', children: [
    { id: 'twin:opcua', name: 'OPC UA', sel: { group: 'twin', id: 'OPC UA' } },
    { id: 'twin:mqtt', name: 'MQTT', sel: { group: 'twin', id: 'MQTT' } },
  ] },
]

function Node({ node, depth, selectedId, onSelect }) {
  const [open, setOpen] = useState(depth < 2)
  const has = node.children && node.children.length
  const active = selectedId === node.id
  return (
    <Box>
      <Box onClick={() => { if (has) setOpen(o => !o); onSelect(node) }}
        sx={{ cursor: 'pointer', pl: depth * 1.4 + 0.5, py: 0.3, fontSize: 12, borderRadius: 1,
          color: active ? '#1FB8CD' : 'text.secondary', bgcolor: active ? 'rgba(31,184,205,0.12)' : 'transparent',
          display: 'flex', gap: 0.5, '&:hover': { color: 'text.primary' } }}>
        <span style={{ width: 10, color: '#5b6472', fontSize: 9 }}>{has ? (open ? '▼' : '▶') : ''}</span>
        {node.name}
      </Box>
      {has && open && node.children.map(c => (
        <Node key={c.id} node={c} depth={depth + 1} selectedId={selectedId} onSelect={onSelect} />
      ))}
    </Box>
  )
}

export default function HierarchyPanel() {
  const classes = useSignalStore(s => s.classes)
  const loadClasses = useSignalStore(s => s.loadClasses)
  const select = useSignalStore(s => s.select)
  const selection = useSignalStore(s => s.selection)
  const [selId, setSelId] = useState(null)
  useEffect(() => { loadClasses() }, [loadClasses])

  const tree = buildHierarchy(classes)
  const onSelect = (node) => {
    setSelId(node.id)
    const sel = node.sel || nodeToSelection(node)
    if (sel) select(sel.group, sel.id)
  }

  return (
    <Box sx={{ height: '100%', overflowY: 'auto', p: 1, bgcolor: 'rgba(255,255,255,0.03)', borderRadius: 2 }}>
      <Typography sx={{ fontSize: 10, color: '#6b7280', letterSpacing: 1, mb: 0.5 }}>HIERARCHY</Typography>
      <Node node={tree} depth={0} selectedId={selId} onSelect={onSelect} />
      {GROUPS_EXTRA.map(g => (
        <Node key={g.name} node={g} depth={0} selectedId={selId}
          onSelect={(n) => { setSelId(n.id); if (n.sel) select(n.sel.group, n.sel.id) }} />
      ))}
    </Box>
  )
}
