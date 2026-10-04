"""Generate Parts through NJC AutoMesh, save and capture native arrays."""
from riglib.run_options import render_images
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
    identity=n.ensure_source(run/'imported.inx',observation['source']['metadata_sha256'])
    if identity['metadata_sha256']!=observation['source']['metadata_sha256']:
        raise ValueError('NJC did not load the recorded unrigged PSD import')
    targets=list(dict.fromkeys(m['part'] for m in assembly['materials']))
    original={uid:r['item']['data'] for uid,r in zip(targets,n.read_many(targets))}
    if any(d['type']!='Part' for d in original.values()):raise ValueError('Part AutoMesh target is not a Part')
    n.save(output)
    n.call('ViewportCommand_ResetParameters')
    # Small/narrow alpha regions cannot support Optimum's native 10-pixel
    # minimum spacing. Choose the native contour processor from observed size,
    # independently of material names, model identity or manual coordinates.
    groups=defaultdict(list)
    for uid in targets:
        from PIL import Image
        alpha=Image.open(materials[uid]['file']).convert('RGBA').getchannel('A')
        box=alpha.getbbox()
        if box is None:raise ValueError('AutoMesh target has no visible alpha')
        short,long=sorted((box[2]-box[0],box[3]-box[1]))
        # A contour approximation may trim painted tips or discard small
        # islands. Native Grid AutoMesh covers the entire alpha rectangle and
        # its filtering margin, including transparent holes in mouth outlines.
        # It remains native-generated Part topology, not Python triangles.
        groups['grid',0].append(uid)
    configurations=[]
    for (processor,step),ids in sorted(groups.items()):
        simple={'x_segments':12,'y_segments':12,'margin':.1,'mask_threshold':1}
        axis=[-.1,*[i/12 for i in range(13)],1.1]
        advanced={'scale_x':axis,'scale_y':axis}
        n.call('AutoMesh_SetSimple_'+processor,**simple)
        n.call('AutoMesh_SetAdvanced_'+processor,**advanced)
        n.call('AutoMesh_Apply_'+processor,context={'nodes':ids})
        configurations.append({'processor':processor,'simple':simple,'advanced':advanced,'targets':ids})
        print('NJC AutoMesh',processor,step,':',len(ids),'Parts',flush=True)
    meshes={}
    for uid,response in zip(targets,n.read_many(targets)):
        data=response['item']['data']
        if data['transform']!=original[uid]['transform']:
            raise ValueError('AutoMesh changed the Part coordinate frame')
        meshes[str(uid)]=captured_mesh(data)
    n.save(output)
    for uid,response in zip(targets,n.read_many(targets)):verify_mesh(response['item']['data'],meshes[str(uid)])
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
    if render_images(run): n.call('ViewCommand_SaveScreenshot',filename=str(out/'automesh-neutral.png'))
    print('NJC AutoMesh generated and saved/read back',len(meshes),'Parts',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--out');p.add_argument('--njc',required=True)
    a=p.parse_args();prepare(a.run,a.out or a.run,a.njc)
