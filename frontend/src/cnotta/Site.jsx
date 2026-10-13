/** Campus §9.3/9.7: origin is [x,z] metres, rotation is yaw radians,
 * lanes is a list of model IDs. M7 owns multi-lane geometry and campus assembly.
 */
export function Site({origin=[0,0],rotation=0,lanes=[],children}) {
 return <group name="site" position={[origin[0],0,origin[1]]} rotation={[0,rotation,0]} userData={{lanes}}>
  {typeof children==='function'?children(lanes):children}
 </group>
}
