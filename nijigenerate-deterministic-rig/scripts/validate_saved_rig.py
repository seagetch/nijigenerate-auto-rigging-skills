"""Save/reopen a real rig, compare public snapshots and render all authored axes."""
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
    for row in n.binding_resources():
        result=n.invoke(['resources','read',row['uri']])
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
        n.save(state['output'])
        before,identity=public_snapshot(n)
        n.open(state['output'])
    after,identity_after=public_snapshot(n)
    if json_digest(before)!=json_digest(after):
        write_json(out/'before.json',before);write_json(out/'after.json',after)
        raise ValueError('NJC exposed model state changed across save/reopen')
    require_single_rig(n,state['rig_root'],state['bones'].values())
    write_json(out/'readback.json',{'public_snapshot_sha256':json_digest(after),
        'save_reopen_equal':True,'scope':'NJC exposed nodes and every discovered binding; not INX bytes',
        'parameter_properties_complete':False,'node_identity':identity_after,
        'bindings':len(after['bindings'])})
    program=read_json(Path(state_path).parent/'program.json')
    anatomical=validate_rest_scaffold(n,state,program)
    write_json(out/'scaffold-readback.json',anatomical)
    write_json(out/'hierarchy-readback.json',validate_hierarchy(n,state,program))
    inspection=inspect_live(n);write_json(out/'inspection.json',inspection)
    failures=[]
    for p in inspection['parameters']:
        for b in p['grid_bindings']:
            if b['minimum_cell_area_ratio'] is None or b['minimum_cell_area_ratio']<=.02:
                failures.append({'parameter':p['name'],**b})
            if b['neutral_max_offset'] is None or b['neutral_max_offset']>.01:
                failures.append({'parameter':p['name'],'reason':'nonzero or missing neutral',**b})
    cases=[('neutral',{})]
    facial=read_json(Path(__file__).resolve().parents[1]/'structures/reference-humanoid.registered.json').get('facial_controls',{}).get('parameters',{})
    for name,uid in state['parameters'].items():
        if name in facial:
            xs,ys=facial[name]['axes'];values=[[x,y] for x in (xs[0],xs[len(xs)//2],xs[-1]) for y in ys]
        elif name=='Eye::Gaze' or name.endswith('Yaw-Pitch'):
            values=[[-1,0],[1,0],[0,-1],[0,1],[-1,-1],[1,1],[.5,.5]]
        elif name.startswith('Eye::Blink'):
            values=[[.25],[.5],[.75],[1]]
        else:values=[[-1],[-.5],[.5],[1]]
        for k,value in enumerate(values):cases.append((name.replace('::','-')+'-'+str(k),{name:value}))
    compound={'Face::Yaw-Pitch':[-.5,.5],'Body::Yaw-Pitch':[.5,-.5],'Body::Roll':[.5]}
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
        n.call('ViewCommand_SaveScreenshot',filename=str(file))
        rendered.append({'label':label,'pose':values,'file':str(file),'sha256':digest(file)})
        print('Rendered '+label,flush=True)
    n.call('ViewportCommand_ResetParameters');n.save(state['output'])
    write_json(out/'validation.json',{'numerical_failures':failures,'rendered':rendered,
        'readback_equal':True,'scaffold_validation_passed':anatomical['passed'],
        'visual_review_required':True,'rig_complete':False})
    # Contact sheets derive their crop from the neutral render only.
    neutral=Image.open(out/'neutral.png').convert('RGBA'); box=neutral.getchannel('A').getbbox()
    for family,names in [('body',[r['label'] for r in rendered if not r['label'].startswith(('Eye-','Mouth-'))]),
                         ('face',[r['label'] for r in rendered if r['label'].startswith(('Face-','Eye-','Mouth-'))])]:
        names=['neutral']+[x for x in names if x!='neutral']
        rows=(len(names)+5)//6;sheet=Image.new('RGB',(1800,rows*350),(40,40,40));d=ImageDraw.Draw(sheet)
        x0,y0,x1,y1=box
        crop=(x0,y0,x1,y1) if family=='body' else (int((x0+x1)/2-(y1-y0)*.18),y0,int((x0+x1)/2+(y1-y0)*.18),int(y0+(y1-y0)*.25))
        for i,label in enumerate(names):
            im=Image.open(out/(label+'.png')).convert('RGBA').crop(crop);im.thumbnail((300,320))
            x=(i%6)*300;y=(i//6)*350;sheet.paste(im,(x+(300-im.width)//2,y),im);d.text((x+3,y+324),label,fill='white')
        sheet.save(out/(family+'-sheet.jpg'))
    print('Public readback matched; numerical failures:',len(failures),flush=True)
    if failures:raise ValueError('Saved rig failed numerical deformation validation')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--state',required=True);p.add_argument('--out',required=True);p.add_argument('--njc',required=True);p.add_argument('--baseline')
    a=p.parse_args();validate(a.state,a.out,a.njc,a.baseline)
