// ReliefPatch — 2D heatmap → 3D 표면 요철(displacement). 결함 영역 정점을 돌출.
// 높이맵 R채널=이상도. score↑ → 돌출량↑. 실데이터 기반(난수 아님). InspectionSpecimen·QCLine 공용.
export default function ReliefPatch({ heightTex, size, y = 0, score, position = [0, 0, 0] }) {
  const scale = Math.min(0.12, Math.max(0.02, (score ?? 0.5) * 0.14))
  return (
    <mesh position={[position[0], y || position[1], position[2]]} rotation={[-Math.PI / 2, 0, 0]} castShadow>
      <planeGeometry args={[size, size, 96, 96]} />
      <meshStandardMaterial
        color="#b8c2d2"
        emissive="#ff2a2a" emissiveMap={heightTex} emissiveIntensity={1.3}
        displacementMap={heightTex} displacementScale={scale} displacementBias={0}
        metalness={0.25} roughness={0.65} />
    </mesh>
  )
}
