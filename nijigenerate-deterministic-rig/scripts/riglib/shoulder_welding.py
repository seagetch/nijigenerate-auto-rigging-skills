"""Initial-generation shoulder welding through the existing public NJC API."""
from pathlib import Path
import math
import numpy as np
from PIL import Image
from scipy.ndimage import binary_erosion, distance_transform_edt
from scipy.spatial import cKDTree
from .carrier import rotation
from .data import read_json, write_json

NATIVE_WELD_DISTANCE=4.


def prepare(run, assembly, evidence, materials):
    """Detect proximal skin contours before Part AutoMesh in neutral model XY.

    O is shoulder, T the chest transverse axis, N points toward neck. Only the
    reference arm mesh is sampled densely; all geometry comes from Optimum.
    """
    run=Path(run);source_to_model=np.asarray(evidence['source_to_model'])
    def landmark(name):
        return (source_to_model@np.r_[evidence['landmarks'][name]['xy'],1])[:2]
    upward=landmark('neck_base')-landmark('chest');upward/=np.linalg.norm(upward)
    tangent=np.array([-upward[1],upward[0]])
    def contour(uid):
        material=materials[uid]
        with Image.open(material['file']) as image:
            alpha=np.asarray(image.convert('RGBA'))[:,:,3]>32
        y,x=np.nonzero(alpha&~binary_erosion(alpha))
        transform=np.asarray(material['pixel_to_model'])
        points=(np.c_[x+.5,y+.5,np.ones(len(x))]@transform.T)[:,:2]
        dy,dx=np.gradient(distance_transform_edt(~alpha)-distance_transform_edt(alpha))
        normals=np.c_[dx[y,x],dy[y,x]]@np.linalg.inv(transform[:2,:2])
        normals/=np.maximum(np.linalg.norm(normals,axis=1,keepdims=True),1e-12)
        return points,normals,int(np.count_nonzero(alpha))
    bodies=[m for m in assembly['materials'] if m['owner']=='torso' and m['role']['chart']=='body']
    report={'method':'PSD proximal contour overlap; native Optimum sampling; native AddWelding',
            'native_distance':NATIVE_WELD_DISTANCE,'pairs':[],'mesh_settings':{}}
    if not bodies:
        write_json(run/'shoulder-welding-source.json',report);return {}
    body_data={m['part']:contour(m['part']) for m in bodies}
    body_id=max(body_data,key=lambda uid:body_data[uid][2]);body,bnorm,_=body_data[body_id]
    for arm in assembly['materials']:
        if not arm['owner'].startswith('arm:') or arm['role']['chart']!='skin' or arm['role']['rule']!='arm':continue
        side=evidence['side_mapping'][arm['owner'].split(':')[1]]
        if side not in ('L','R'):continue
        origin=landmark('shoulder.'+side);axis=landmark('elbow.'+side)-origin
        length=float(np.linalg.norm(axis));axis/=length
        points,normals,_=contour(arm['part'])
        def region(p,n):
            delta=p-origin
            return (np.linalg.norm(delta,axis=1)<.30*length)&(delta@axis<.12*length)&(n@upward>.5)
        proximal=points[region(points,normals)];torso=body[region(body,bnorm)]
        record={'source':body_id,'target':arm['part'],'arm':arm['part'],'body':body_id,'side':side,'status':'not_matching',
                'frame':{'origin':origin.tolist(),'tangent':tangent.tolist(),'up':upward.tolist(),
                         'arm_axis':axis.tolist(),'upper_arm_length':length}}
        if len(proximal) and len(torso):
            distances=cKDTree(torso).query(proximal)[0];matched=proximal[distances<.07*length]
            fraction=float(len(matched)/len(proximal));span=float(np.ptp(matched@tangent)) if len(matched) else 0.
            record.update(matched_fraction=fraction,matched_span=span)
            if fraction>=.6 and span>=.18*length:
                record['status']='matching';record['weight']=0.
                # Native 4-unit welding needs enough receiving samples. This
                # changes Optimum sampling, never defines or edits a mesh.
                divisions=min(64.,max(12.,math.ceil(max(materials[arm['part']]['size'])/NATIVE_WELD_DISTANCE)))
                # A single expanded contour leaves radial gaps wider than
                # native welding's cutoff. Sample neighboring contour rings
                # with Optimum's own scale control, including both sides of
                # the artwork boundary. This retains its triangulator/UVs.
                radius=float(np.linalg.norm(materials[arm['part']]['size'])/2)
                ring_count=max(2,math.ceil(.2*radius/NATIVE_WELD_DISTANCE)+1)
                scales=np.linspace(.8,1.,ring_count).tolist()+[.5,0.]
                report['mesh_settings'][str(arm['part'])]={'div_per_part':divisions,'min_distance':1.,'scales':scales,
                    'advanced':{'large_threshold':50.,'length_threshold':20.,'ratio_threshold':.01}}
        report['pairs'].append(record)
    write_json(run/'shoulder-welding-source.json',report)
    return {int(uid):settings for uid,settings in report['mesh_settings'].items()}


def apply(client, program, run):
    """Apply once after hierarchy, UV registration and native AutoMesh settle."""
    run=Path(run);report=read_json(run/'shoulder-welding-source.json')
    parts={p['uuid']:p for d in program['domains'] for p in d['parts']}
    pairs=[p for p in report['pairs'] if p['status']=='matching']
    ids=sorted({p[k] for p in pairs for k in ('source','target')})
    before={uid:response['item']['data'] for uid,response in zip(ids,client.read_many(ids))}
    def world(uid):
        vertices=np.asarray(before[uid]['mesh']['verts']).reshape(-1,2);t=parts[uid]['original_transform']
        return (vertices*t['scale'])@rotation(t['rot'][2]).T+t['trans'][:2]
    for record in pairs:
        source=record['source'];target=record['target'];a=world(source);b=world(target)
        distances=np.linalg.norm(a[:,None,:]-b[None,:,:],axis=2)
        nearest=distances.argmin(axis=1);minimum=distances[np.arange(len(a)),nearest]
        mapping=np.where(minimum<NATIVE_WELD_DISTANCE,nearest,-1).tolist()
        matched=np.flatnonzero(np.asarray(mapping)>=0)
        record['predicted_pairs']=[{'source_vertex':int(i),'target_vertex':int(mapping[i]),
            'source_world':a[i].tolist(),'target_world':b[mapping[i]].tolist(),
            'neutral_snap_distance':float(minimum[i])} for i in matched]
        if not len(matched):
            record['status']='no_native_vertex_pairs';continue
        # Map each torso vertex to the reference arm. Target weight 1 leaves
        # the arm motion intact; source weight 0 makes the torso follow it.
        record['weight']=0.
        client.call('NodeWeldingCommand_AddWelding',target=target,weight=0.,context={'nodes':[source]})
        current=client.read(source)['item']['data'];receiver=client.read(target)['item']['data']
        link=next(link for link in current.get('weldedLinks',[]) if link['targetUUID']==target)
        if link['indices']!=mapping or link['weight']!=0.:
            raise ValueError('Native welding readback differs from predicted correspondence')
        if current['mesh']!=before[source]['mesh'] or receiver['mesh']!=before[target]['mesh']:
            raise ValueError('Welding changed native AutoMesh geometry')
        record.update(status='applied_readback_verified',indices=link['indices'],
                      mesh_arrays_unchanged=True,paired_vertices=len(matched))
        print('Shoulder welding',record['side'],len(matched),'native pairs',flush=True)
    write_json(run/'shoulder-welding-applied.json',report)
    return report
