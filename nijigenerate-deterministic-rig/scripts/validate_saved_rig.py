"""Save the active rig, read its public state and render without reloading it."""
import argparse
from pathlib import Path
import time
import numpy as np
from PIL import Image,ImageDraw
from riglib.data import read_json,write_json,json_digest,digest
from riglib.live import Live
from riglib.model import read_model_metadata
from build_native import require_single_rig
from render_rig import inspect_live
from riglib.scaffold_validation import validate_rest_scaffold
from riglib.hierarchy import validate_hierarchy


def public_snapshot(n):
    def census():
        rows=[]
        def visit(item,parent=None):
            rows.append((item['uuid'],item['typeId'],item['name'],parent))
            for child in item.get('children') or []:visit(child,item['uuid'])
        for item in n.find('*')['items']:visit(item)
        return sorted(rows,key=lambda r:(r[1],r[0]))
    initial_census=census()
    data,identity=read_model_metadata(client=n,require_parameters=False)
    bindings={}
    rows=n.binding_resources()
    for row,result in zip(rows,n.read_resources([row['uri'] for row in rows])):
        if not isinstance(result.get('item'),dict):raise ValueError('Live binding unavailable: '+str(result))
        bindings[row['uri']]=result['item']
    if census()!=initial_census:raise ValueError('Model changed during binding snapshot')
    return {'nodes':data,'bindings':bindings},identity


def validate(state_path,out,executable,baseline=None):
    state=read_json(state_path); out=Path(out).resolve();out.mkdir(parents=True,exist_ok=True)
    n=Live(executable,out/'journal')
    n.call('ToolCommand_ModelEditMode')
    n.call('ViewportCommand_ResetParameters')
    require_single_rig(n,state['rig_root'],state['bones'].values())
    if baseline:
        before=read_json(baseline)
    else:
        before,identity=public_snapshot(n)
    n.save(state['output'])
    after,identity_after=public_snapshot(n)
    if json_digest(before)!=json_digest(after):
        write_json(out/'before.json',before);write_json(out/'after.json',after)
        raise ValueError('NJC exposed model state changed across save')
    del before
    require_single_rig(n,state['rig_root'],state['bones'].values())
    write_json(out/'readback.json',{'public_snapshot_sha256':json_digest(after),
        'save_reopen_equal':None,'save_reopen_performed':False,'save_state_equal':True,
        'scope':'NJC exposed active model before/after save; no file reload or INX byte inspection',
        'parameter_properties_complete':False,'node_identity':identity_after,
        'bindings':len(after['bindings'])})
    program=read_json(Path(state_path).parent/'program.json')
    from riglib.shape_validation import validate as validate_shapes
    shape_check=validate_shapes(Path(state_path).resolve().parent,state,after)
    write_json(out/'shape-readback.json',shape_check)
    evidence=read_json(Path(state_path).parent/'evidence.json')
    static_checked=[]
    if evidence.get('static_materials'):
        parents={};public_nodes={}
        def collect(node,parent=None):
            uid=node['uuid'];parents[uid]=parent;public_nodes[uid]=node
            for child in node.get('children',[]):collect(child,uid)
        collect(after['nodes']['nodes'])
        bound={b['target']['uuid'] for b in after['bindings'].values()}
        for material in evidence['static_materials']:
            uid=material['part'];chain=[];cursor=uid
            while cursor is not None:chain.append(cursor);cursor=parents[cursor]
            if set(chain)&bound or any(public_nodes[k]['type'] in ('GridDeformer','DepthBone') for k in chain):
                raise ValueError('Static PSD background still has an animated support')
            static_checked.append({'part':uid,'animated_supports':False,'source_rendering_retained':public_nodes[uid]['enabled']})
    humanoid=program.get('kind','humanoid')=='humanoid'
    anatomical=validate_rest_scaffold(n,state,program) if humanoid else {'passed':True,'applicable':False,'kind':program['kind']}
    write_json(out/'scaffold-readback.json',anatomical)
    if humanoid:write_json(out/'hierarchy-readback.json',validate_hierarchy(n,state,program))
    inspection=inspect_live(n,after,identity_after);write_json(out/'inspection.json',inspection)
    failures=[]
    for p in inspection['parameters']:
        for b in p['grid_bindings']:
            if b['minimum_cell_area_ratio'] is None or b['minimum_cell_area_ratio']<=.02:
                failures.append({'parameter':p['name'],**b})
            if b['neutral_max_offset'] is None or b['neutral_max_offset']>.01:
                failures.append({'parameter':p['name'],'reason':'nonzero or missing neutral',**b})
    cases=[('neutral',{})]
    saved_axes={b['parameter']['name']:b['axisValues'] for b in after['bindings'].values()}
    facial=read_json(Path(__file__).resolve().parents[1]/'structures/reference-humanoid.registered.json').get('facial_controls',{}).get('parameters',{})
    for name,uid in state['parameters'].items():
        if name in saved_axes:
            xs,ys=saved_axes[name]
            values=[[x,y] for x in xs for y in ys]
        elif name in state.get('control_specs',{}):
            xs,ys=state['control_specs'][name]['axes']
            values=[[x,y] for x in xs for y in ys]
        elif name in facial:
            xs,ys=facial[name]['axes'];values=[[x,y] for x in (xs[0],xs[len(xs)//2],xs[-1]) for y in ys]
        elif name=='Eye::Gaze' or name.endswith('Yaw-Pitch'):
            values=[[-1,0],[1,0],[0,-1],[0,1],[-1,-1],[1,1],[.5,.5]]
        elif name.startswith('Eye::Blink'):
            values=[[.25],[.5],[.75],[1]]
        else:values=[[-1],[-.5],[.5],[1]]
        for k,value in enumerate(values):cases.append((name.replace('::','-')+'-'+str(k),{name:value}))
    compound={'Face::Yaw-Pitch':[-.5,.5],'Body::Yaw-Pitch':[.5,-.5],'Body::Roll':[.5]}
    compound={k:v for k,v in compound.items() if k in state['parameters']}
    if not compound:compound={k:[.5,1.] for k in state.get('control_specs',{})}
    if 'Eye::Blink::L' in state['parameters']:compound['Eye::Blink::L']=[.5]
    if 'Eye::L::Blink' in state['parameters']:compound['Eye::L::Blink']=[.5,0]
    cases.append(('combined',compound))
    n.call('ViewportCommand_FitViewportToModel')
    time.sleep(.5)
    rendered=[]
    for label,values in cases:
        n.call('ViewportCommand_ResetParameters')
        for name,value in values.items():
            n.call('ParameditCommand_SetParameterKeypoint',context={'parameters':[state['parameters'][name]],'parameterValue':value})
        time.sleep(.12)
        file=out/(label+'.png')
        from riglib.render_camera import capture as capture_camera
        capture_camera(n,Path(state_path).resolve().parent,file)
        rendered.append({'label':label,'pose':values,'file':str(file),'sha256':digest(file)})
        print('Rendered '+label,flush=True)
    n.call('ViewportCommand_ResetParameters')
    require_single_rig(n,state['rig_root'],state['bones'].values())
    n.save(state['output'])
    write_json(out/'validation.json',{'numerical_failures':failures,'rendered':rendered,
        'static_materials_verified':static_checked,
        'readback_equal':True,'save_reopen_performed':False,'readback_scope':'current_model_after_save',
        'scaffold_validation_passed':anatomical['passed'],
        'rendered_key_coverage':'all_saved_parameter_axes',
        'visual_review_required':True,'rig_complete':False})
    # Contact sheets derive their crop from the neutral render only.
    neutral=Image.open(out/'neutral.png').convert('RGBA'); box=neutral.getchannel('A').getbbox()
    for family,names in [('body',[r['label'] for r in rendered if r['label'].startswith('Body-') or r['label']=='combined']),
                         ('face',[r['label'] for r in rendered if r['label'].startswith(('Face-','Eye-','Mouth-'))])]:
        if not humanoid:names=[r['label'] for r in rendered]
        names=['neutral']+[x for x in names if x!='neutral']
        rows=(len(names)+5)//6;sheet=Image.new('RGB',(1800,rows*350),(40,40,40));d=ImageDraw.Draw(sheet)
        x0,y0,x1,y1=box
        crop=(x0,y0,x1,y1) if family=='body' or not humanoid else (int((x0+x1)/2-(y1-y0)*.18),y0,int((x0+x1)/2+(y1-y0)*.18),int(y0+(y1-y0)*.25))
        if not humanoid:crop=(0,0,neutral.width,neutral.height)
        for i,label in enumerate(names):
            im=Image.open(out/(label+'.png')).convert('RGBA').crop(crop);im.thumbnail((300,320))
            x=(i%6)*300;y=(i//6)*350;sheet.paste(im,(x+(300-im.width)//2,y),im);d.text((x+3,y+324),label,fill='white')
        sheet.save(out/(family+'-sheet.jpg'))
    print('Public readback matched; numerical failures:',len(failures),flush=True)
    from review_sheets import create as create_review_sheets
    create_review_sheets(Path(state_path).resolve().parent)
    if failures:print('Recorded deformation findings; saved renders remain available for inspection',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--state',required=True);p.add_argument('--out',required=True);p.add_argument('--njc',required=True);p.add_argument('--baseline')
    a=p.parse_args();validate(a.state,a.out,a.njc,a.baseline)
