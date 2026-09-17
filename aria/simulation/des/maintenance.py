"""Bounded, deterministic repair harness for injected virtual equipment faults.

No shell/LLM/physical actuator tools. Diagnosis reads simulated sensor evidence;
product anomaly scores never authorize equipment repair.
"""
import copy
import uuid

RECIPES = {
    'gripper_jam': dict(tool='clear_virtual_gripper', label='Gripper obstruction', location=[.45, 1.4, 2.05],
                        sensors={'gripper_open': False, 'drive_alarm': True},
                        healthy={'gripper_open': True, 'drive_alarm': False}),
    'camera_disconnect': dict(tool='reconnect_virtual_camera', label='Inspection camera link lost', location=[.45, 2.65, -.8],
                             sensors={'camera_link': False, 'frame_ready': False},
                             healthy={'camera_link': True, 'frame_ready': True}),
    'unknown': dict(tool=None, label='Unclassified equipment alarm', location=[0, 1.5, 0],
                    sensors={'unclassified_alarm': True}, healthy={}),
}
TERMINAL = {'RESTORED', 'ESCALATED', 'INTERRUPTED'}

class MaintenanceHarness:
    def __init__(self):
        self.tasks = []

    def start(self, engine, component, cause):
        if cause not in RECIPES:
            raise ValueError('Unsupported fault scenario')
        node = engine.nodes.get(component)
        if not node or node['c'].kind not in ('Machine', 'Inspection'):
            raise ValueError('Choose Machine or Inspection')
        if cause == 'camera_disconnect' and node['c'].kind != 'Inspection':
            raise ValueError('Camera scenario requires Inspection')
        if node['down'] or node['c'].maintenance or engine.now >= engine.model.simulation.duration:
            raise ValueError('Equipment must be available in an unfinished run')
        recipe = RECIPES[cause]
        token = uuid.uuid4().hex
        # Invalidate scheduled completions, retain the exact interrupted work.
        node['down'] = True
        node['epoch'] += 1
        for job in node['jobs']:
            if job['phase'] != 'ready':
                job['remaining'] = max(0., job['due'] - engine.now)
        node['fault'] = dict(id=token, cause=cause, label=recipe['label'], location=recipe['location'],
                             sensors=dict(recipe['sensors']), isolated=True, source='injected virtual sensor scenario')
        if cause=='gripper_jam' and node['c'].robot_model:
            x,y,z=engine.robot_state(node)['tcp']
            node['fault']['location']=[.45-x,.65+z,2.05+y] if node['c'].kind=='Machine' else [-.6+x,.99+z,-.35-y]
        engine._settle()
        task = dict(id=token, run=engine.run_token, component=component, cause=cause, state='DISPATCHED',
                    robot=None, elapsed=0., stage_elapsed=0., attempts=0, max_attempts=1, trace=[],
                    source='simulation only', started_sim_time=engine.now)
        self.tasks.append(task)
        self.tasks = self.tasks[-100:]
        self.transition(engine, task, 'DISPATCHED', 'observe', dict(node['fault']))
        return copy.deepcopy(task)

    def transition(self, engine, task, state, tool, evidence):
        task.update(state=state, stage_elapsed=0.)
        entry=dict(state=state, tool=tool, elapsed=round(task['elapsed'],3), sim_time=engine.now, evidence=copy.deepcopy(evidence))
        task['trace'].append(entry)
        engine.emit('maintenance_action', component=task['component'], task=task['id'], **entry)

    def tick(self, engine, patrol, dt):
        dt=max(0.,min(float(dt),.5))
        for task in self.tasks:
            if task['state'] in TERMINAL:
                continue
            node=engine.nodes.get(task['component'])
            robot=next((r for r in patrol.robots if r['id']==task['robot']),None)
            if task['run'] != engine.run_token or not node or node.get('fault',{}).get('id') != task['id']:
                self.transition(engine,task,'INTERRUPTED','cancel',{'reason':'Run or fault changed; recovery not verified'})
            elif not patrol.enabled:
                continue
            else:
                task['elapsed']+=dt;task['stage_elapsed']+=dt
                fault=node['fault'];recipe=RECIPES[task['cause']]
                if task['elapsed']>120:
                    self.transition(engine,task,'ESCALATED','timeout',{'reason':'120 s active wall-time budget exceeded; equipment remains isolated'})
                elif task['state']=='DISPATCHED':
                    # A report alone is insufficient: robot must still be on site.
                    robot=next((r for r in patrol.robots if r['target']==task['component'] and r['state']=='INSPECTING' and not r['path'] and not r.get('maintenance_hold')),None)
                    if robot:
                        task['robot']=robot['id'];robot['maintenance_hold']=task['id']
                        self.transition(engine,task,'DIAGNOSING','read_virtual_sensors',fault['sensors'])
                elif task['state']=='DIAGNOSING' and task['stage_elapsed']>=2:
                    if recipe['tool'] is None or fault['sensors']!=recipe['sensors']:
                        self.transition(engine,task,'ESCALATED','diagnose',{'reason':'No matching approved repair recipe'})
                    else:
                        task['attempts']+=1
                        self.transition(engine,task,'REPAIRING',recipe['tool'],{'preconditions':{'isolated':fault['isolated'],'on_site':robot is not None},'cause':recipe['label']})
                elif task['state']=='REPAIRING' and task['stage_elapsed']>=4:
                    if not robot or not fault['isolated'] or not node['down'] or task['attempts']>task['max_attempts']:
                        self.transition(engine,task,'ESCALATED','guard',{'reason':'Repair precondition failed'})
                    else:
                        if node['c'].robot_model:
                            fault['test_q']=engine.robot_state(node)['joints']
                            fault['test_elapsed']=0.
                        fault['sensors']=dict(recipe['healthy'])
                        self.transition(engine,task,'VERIFYING','virtual_function_test',{'expected':recipe['healthy'],'observed':fault['sensors']})
                elif task['state']=='VERIFYING':
                    fault['test_elapsed']=task['stage_elapsed']
                    if task['stage_elapsed']<4:continue
                    robot_check=engine.robot_state(node) if node['c'].robot_model else None
                    passed=(robot_check is None or robot_check['target_error_rad']<1e-6) and bool(recipe['healthy']) and fault['sensors']==recipe['healthy'] and node['down'] and fault['isolated']
                    if not passed:
                        self.transition(engine,task,'ESCALATED','verify',{'passed':False,'observed':fault['sensors']})
                    else:
                        # Only this successful verification can release a managed fault.
                        node.pop('fault');engine._resume_node(node, schedule_failure=False);engine._settle()
                        if not any(ev[2]=='failure' and ev[3]==task['component'] for ev in engine.heap):engine._next_failure(node)
                        self.transition(engine,task,'RESTORED','release_virtual_interlock',{'passed':True,'joint_return_error_rad':robot_check['target_error_rad'] if robot_check else None,'sensor_checks':dict(recipe['healthy']), 'state':node['state'], 'completed_at_release':node['total'], 'scope':'simulated sensor self-test; production output tracked separately'})
            if robot:
                if task['state'] in TERMINAL:
                    robot.pop('maintenance_hold',None);robot.update(state='INSPECTING',dwell=1.)
                else:
                    robot['state']=task['state']
            report=next((r for r in reversed(patrol.reports) if r['component']==task['component'] and r['kind']=='equipment_down' and r['run']==patrol.run),None)
            if report:
                report['maintenance']=copy.deepcopy(task)
                report['outcome']='Virtual repair harness: '+task['state']
                if task['stage_elapsed']==0:patrol.save()
        patrol.maintenance=copy.deepcopy(list(reversed(self.tasks)))
