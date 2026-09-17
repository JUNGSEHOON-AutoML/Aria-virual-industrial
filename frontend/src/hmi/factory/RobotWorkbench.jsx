import SceneErrorBoundary from '../panels/SceneErrorBoundary'
import { useEffect, useState } from 'react'
import { Canvas } from '@react-three/fiber'
import { OrbitControls, Html } from '@react-three/drei'
import RobotArm from './RobotArm'
import { useFactory, factoryApi } from './factoryStore'
const deg=x=>(x*180/Math.PI).toFixed(1)
const toScene=p=>[p[0],p[2],-p[1]]
export default function RobotWorkbench({component,onClose}) {
 const snap=useFactory(s=>s.snapshot),patrol=useFactory(s=>s.patrol),action=useFactory(s=>s.action),busy=useFactory(s=>s.busy)
 const [model,setModel]=useState(null)
 useEffect(()=>{factoryApi('/robot/model').then(setModel).catch(e=>useFactory.setState({error:e.message}))},[])
 const resource=snap.metrics.resources[component.id],robot=resource.robot
 const task=patrol?.maintenance?.find(t=>t.component===component.id)
 return <div className="engineering-modal" role="dialog" aria-label="로봇 구동 모듈"><header><div><small>DOOSAN M0609 · VIRTUAL JOINT CONTROLLER</small><h2>{component.id} · 로봇 구동 모듈</h2></div><button onClick={onClose}>닫기 ×</button></header>
 <div className="engineering-body"><section className="engineering-canvas"><SceneErrorBoundary><Canvas shadows camera={{position:[1.8,1.4,2],fov:40}}><color attach="background" args={['#162934']}/><ambientLight intensity={1.2}/><directionalLight position={[2,4,2]} intensity={2.5}/>
 <mesh rotation={[-Math.PI/2,0,0]} position={[0,-.012,0]}><planeGeometry args={[5,5]}/><meshStandardMaterial color="#354c57"/></mesh><gridHelper args={[4,20,'#75959d','#49626c']}/>
 <RobotArm state={robot}/>
 {model&&Object.entries(model.fixtures).filter(([k])=>k!=='home').map(([k,p])=><group key={k} position={toScene(p)}><mesh position={[0,-.06,0]}><boxGeometry args={[.16,.04,.16]}/><meshStandardMaterial color={k==='inspect'?'#418cad':'#597380'}/></mesh><Html position={[0,-.17,0]} center><span className="evidence-pin">{k.toUpperCase()}</span></Html></group>)}
 {robot&&resource.occupancy>0&&<mesh position={toScene(robot.attached?robot.tcp:(model?.fixtures[robot.stage==='RELEASE'||robot.stage==='RETURN_HOME'?'place':'pick']||robot.tcp))}><boxGeometry args={[.045,.055,.045]}/><meshStandardMaterial color="#ffc165"/></mesh>}
 <OrbitControls target={[0,.4,0]} minDistance={.3} maxDistance={5}/></Canvas></SceneErrorBoundary>
 <div className="engineering-controls"><button disabled={busy} onClick={()=>action('/run',{speed:'1'})}>1× 공정 실행</button><button onClick={()=>action('/pause')}>일시정지</button><span>{resource.state} · {robot?.stage||'모듈 연결 필요'}</span></div>
 </section><aside><h3>명령 → 관절 → 작업 확인</h3>{!robot?<><p>이 셀에 M0609 모듈을 연결하면 집기·검사·놓기·복귀 완료가 공정 완료 조건이 됩니다. 적용 시 공정을 초기화합니다.</p><button className="primary" onClick={()=>{action(`/components/${component.id}`,{robot_model:'m0609',capacity:1},'PATCH');onClose()}}>M0609 모듈 연결 검토</button></>:<>
 <strong className={resource.state==='DOWN'?'robot-down':''}>{resource.state==='DOWN'?'INTERLOCK · 구동 정지':robot.stage}</strong><p>{snap.status} · 주기 {robot.elapsed.toFixed(2)} / {robot.duration.toFixed(2)} s<br/>그리퍼 {robot.gripper} · 제품 {robot.attached?'파지 중':'분리'}</p>
 <table><thead><tr><th>축</th><th>현재 °</th><th>목표 °</th><th>속도 °/s</th></tr></thead><tbody>{robot.joints.map((q,i)=><tr key={i}><td>J{i+1}</td><td>{deg(q)}</td><td>{deg(robot.target[i])}</td><td>{deg(robot.velocity[i])}</td></tr>)}</tbody></table>
 <p>완료 확인 {robot.completed_steps?.length||0} / 7<br/>{robot.completed_steps?.join(' → ')}</p><p>TCP (로봇 기준, m)<br/>{robot.tcp.map(v=>v.toFixed(3)).join(' / ')}</p><p>목표 관절 오차 {deg(robot.target_error_rad)}°</p></>}
 <h4>고장 → 진단 → 수리 → 시험</h4><button disabled={busy||resource.state==='DOWN'} onClick={()=>action('/maintenance/fault',{component:component.id,cause:'gripper_jam'})}>가상 그리퍼 고장 주입</button>
 {task&&<><p>{task.robot||'로봇 출동 대기'} · {task.state}</p><ol className="maintenance-trace">{task.trace.map((t,i)=><li key={i}><b>{t.state}</b><small>{t.elapsed}s · {t.tool}</small></li>)}</ol></>}
 <p className="engineering-note">공식 URDF 형상·관절 제한 + 자체 작성 작업 궤적. 값은 가상 제어 상태이며 실기기 측정 데이터가 아닙니다. 충돌·접촉·토크 동역학은 검증하지 않습니다.</p><a href="https://github.com/DoosanRobotics/doosan-robot2" target="_blank" rel="noreferrer">공식 모델 출처 ↗</a>
 </aside></div></div>
}
