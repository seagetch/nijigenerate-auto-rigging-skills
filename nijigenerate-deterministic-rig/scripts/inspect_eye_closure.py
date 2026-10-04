"""Inspect real saved eye masks through NJC, then discard temporary visibility edits."""
import argparse
from pathlib import Path
import numpy as np
from riglib.data import read_json,write_json,json_digest
from riglib.live import Live,created_id
from validate_saved_rig import public_snapshot
from build_native import require_single_rig


def inspect(run,njc):
    run=Path(run).resolve();state=read_json(run/'native-state.json');evidence=read_json(run/'evidence.json')
    n=Live(njc,run/'eye-closure-inspection-journal');n.open(state['output'])
    require_single_rig(n,state['rig_root'],state['bones'].values())
    n.call('ToolCommand_ModelEditMode');n.call('ViewportCommand_ResetParameters')
    before,_=public_snapshot(n);original=json_digest(before);records=[]
    eyes=sorted(evidence.get('eyes',[]),key=lambda e:e['side'])
    try:
        for eye in eyes:
            side=eye['side'];groups=eye['part_groups'];name='Eye::'+side+'::Blink';pid=state['parameters'][name]
            program=read_json(run/'program.json');ends=np.asarray(eye['canthi_model']);center=ends.mean(0)
            camera=created_id(n.call('NodeCommand_AddNode',className='Camera',_suffix='',context={'nodes':[program['source_root']]}))
            camera_name='Inspection::Eye::'+side
            n.call('NodeCommand_SetNodeName',newNames=[camera_name],context={'nodes':[camera]})
            scale=float(np.linalg.norm(ends[1]-ends[0])*5/1920)
            for axis,k in [('X',0),('Y',1)]:
                n.call('Inspector_Apply_Translation'+axis,value=float(center[k]),context={'nodes':[camera]})
                n.call('Inspector_Apply_Scale'+axis,value=scale,context={'nodes':[camera]})
            def pose(value):
                n.call('ViewportCommand_ResetParameters')
                n.call('ParameditCommand_SetParameterKeypoint',context={'parameters':[pid],'parameterValue':[value,0.]})
            def render(label):
                path=run/('inspection-eye-'+side+'-'+label+'.png')
                n.call('FileCommand_ExportPNG',file=str(path),cameraName=camera_name,transparency=True,postprocessing=False)
                records.append({'side':side,'label':label,'file':str(path)})
                print('Eye inspection',side,label,flush=True)
            pose(1.);render('closed');render('closed-repeat')
            hidden=[]
            for uid in groups.get('iris',[])+groups.get('upper',[])+groups.get('lower',[]):
                if n.read(uid)['item']['data']['enabled']:
                    n.call('NodeCommand_ToggleVisibility',context={'nodes':[uid]});hidden.append(uid)
            pose(0.);render('sclera-open')
            pose(1.);render('sclera-closed')
            for uid in hidden:n.call('NodeCommand_ToggleVisibility',context={'nodes':[uid]})
            pose(1.)
            for uid in groups.get('iris',[]):
                masks=n.read(uid)['item']['data'].get('masks',[])
                for mask in masks:
                    if mask['source'] in groups['sclera'] and mask['mode']=='Mask':
                        n.call('NodeMaskCommand_RemoveMask',maskSrc=mask['source'],context={'nodes':[uid]})
            render('without-iris-mask')
            n.open(state['output']);n.call('ViewportCommand_ResetParameters')
    finally:
        n.open(state['output']);n.call('ViewportCommand_ResetParameters')
    after,_=public_snapshot(n)
    restored=json_digest(after)==original
    write_json(run/'eye-closure-inspection.json',{'images':records,'saved_model_writes':False,
        'public_state_restored':restored,'original_public_state_sha256':original,'final_public_state_sha256':json_digest(after)})
    if not restored:raise RuntimeError('Temporary eye inspection state did not restore')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--njc',required=True)
    a=p.parse_args();inspect(a.run,a.njc)
