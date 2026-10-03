"""Generate Parts through NJC AutoMesh, save, reopen and capture native arrays."""
import argparse
from collections import defaultdict
from pathlib import Path
from riglib.data import read_json,write_json,json_digest
from riglib.live import Live
from riglib.model import read_model_metadata
from riglib.part_mesh import captured_mesh,verify_mesh

# Native Optimum defaults, explicitly set so GUI settings cannot change a run.
SIMPLE={'div_per_part':12,'mask_threshold':1,'min_distance':10,'scales':[.5,0.]}
ADVANCED={'large_threshold':400,'length_threshold':100,'ratio_threshold':.2,
          'sharp_expand':.01,'unsharp_expand':.05,'unsharp_contract':.05}


def prepare(run,out,njc):
    run=Path(run).resolve();out=Path(out).resolve();out.mkdir(parents=True,exist_ok=True)
    observation=read_json(run/'observation.json');assembly=read_json(run/'assembly.json');evidence=read_json(run/'evidence.json')
    capture=read_json(run/'capture.json');materials={m['part']:m for m in capture['materials']}
    if any(d['observation_sha256']!=json_digest(observation) for d in (assembly,evidence)):
        raise ValueError('Part AutoMesh source provenance mismatch')
    output=out/'automeshed.inx';n=Live(njc,out/'automesh-journal')
    n.open(run/'imported.inx')
    _,identity=read_model_metadata(client=n)
    if identity['metadata_sha256']!=observation['source']['metadata_sha256']:
        raise ValueError('NJC did not load the recorded unrigged PSD import')
    targets=sorted({m['part'] for m in assembly['materials']})
    original={uid:n.read(uid)['item']['data'] for uid in targets}
    if any(d['type']!='Part' for d in original.values()):raise ValueError('Part AutoMesh target is not a Part')
    n.save(output)
    n.call('ViewportCommand_ResetParameters')
    # Small/narrow alpha regions cannot support Optimum's native 10-pixel
    # minimum spacing. Choose the native contour processor from observed size,
    # independently of material names, model identity or manual coordinates.
    groups=defaultdict(list)
    for uid in targets:
        short,long=sorted(materials[uid]['size'])
        if short<2*SIMPLE['min_distance']:
            step=max(1,int(min(short/2,long/12)))
            groups['contour',step].append(uid)
        else:groups['optimum',0].append(uid)
    configurations=[]
    for (processor,step),ids in sorted(groups.items()):
        simple=SIMPLE if processor=='optimum' else {'sampling_step':step,'mask_threshold':1}
        advanced=ADVANCED if processor=='optimum' else {'min_distance':max(1,step/2),
            'max_distance':step*2,'scales':[1,1.1,.5,0]}
        n.call('AutoMesh_SetSimple_'+processor,**simple)
        n.call('AutoMesh_SetAdvanced_'+processor,**advanced)
        n.call('AutoMesh_Apply_'+processor,context={'nodes':ids})
        configurations.append({'processor':processor,'simple':simple,'advanced':advanced,'targets':ids})
        print('NJC AutoMesh',processor,step,':',len(ids),'Parts',flush=True)
    meshes={}
    for uid in targets:
        data=n.read(uid)['item']['data']
        if data['transform']!=original[uid]['transform']:
            raise ValueError('AutoMesh changed the Part coordinate frame')
        meshes[str(uid)]=captured_mesh(data)
    n.save(output);n.open(output)
    for uid in targets:verify_mesh(n.read(uid)['item']['data'],meshes[str(uid)])
    _,saved_identity=read_model_metadata(client=n)
    evidence['part_meshes']=meshes
    evidence['part_mesh_source']=saved_identity
    evidence['part_mesh_generation']={'transport':'njc','configurations':configurations,
        'input_snapshot':observation['source']['metadata_sha256'],
        'saved_readback_verified':True,'output':str(output),'part_count':len(targets)}
    write_json(out/'evidence.json',evidence)
    write_json(out/'automesh-readback.json',{'source':saved_identity,'generation':evidence['part_mesh_generation'],
        'parts':{uid:{k:v for k,v in row.items() if k not in ('vertices','indices')} for uid,row in meshes.items()},
        'visual_acceptance':False})
    n.call('ViewportCommand_FitViewportToModel')
    n.call('ViewCommand_SaveScreenshot',filename=str(out/'automesh-neutral.png'))
    print('NJC AutoMesh generated and saved/read back',len(meshes),'Parts',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--out');p.add_argument('--njc',required=True)
    a=p.parse_args();prepare(a.run,a.out or a.run,a.njc)
