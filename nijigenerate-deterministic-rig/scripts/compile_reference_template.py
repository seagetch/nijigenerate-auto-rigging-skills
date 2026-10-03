"""Fit ONE dimensionless template from all explicitly captured references.

No reference selection, character-name branch, or per-character runtime profile.
Raw source observations and fitting residuals remain outside the runtime template.
The result is a measured candidate until transfer and render validation complete.
"""
import argparse
from collections import defaultdict
from pathlib import Path
import numpy as np
from riglib.data import read_json, write_json, json_digest, digest


def role(name):
    tokens = [p.lower() for p in name.split('::') if p not in ('G', 'Root')]
    # Semantic spelling normalization, independent of reference identity.
    aliases = {'face':'face', 'body':'torso', 'chest':'chest',
        'fronthair':'hair_front', 'sidehair':'hair_side', 'backhair':'hair_back',
        'earbackhair':'hair_ear_back', 'headwear':'headwear', 'topwear':'topwear',
        'clothing':'skirt', 'skirt':'skirt', 'skirtpanel':'skirt_panel',
        'trainside':'train', 'train':'train', 'arm':'arm', 'sleeve':'sleeve',
        'leg':'leg', 'apron':'apron', 'tail':'tail', 'plush':'carried_accessory'}
    if not tokens or tokens[0] not in aliases:
        raise ValueError('Unresolved reference component role: '+name)
    return '/'.join([aliases[tokens[0]], *tokens[1:]])


def affine_world(snapshot):
    nodes={r['item']['uuid']:r['item']['data'] for r in snapshot['nodes']}
    parents={r['item']['uuid']:r['parent'] for r in snapshot['nodes']}
    cache={}
    def world(uid):
        if uid is None:return np.eye(4)
        if uid in cache:return cache[uid]
        d=nodes[uid];t=d['transform']
        # Reject unsupported coordinates rather than silently guessing them.
        if not np.allclose(t['rot'],0) or d.get('pinToMesh'):
            raise ValueError('Unresolved reference transform: '+d['name'])
        m=np.eye(4);m[:3,3]=t['trans'];m[0,0],m[1,1]=t['scale'][:2]
        if d.get('lockToRoot'):
            # Skeleton root lock is not needed to measure surface depth.
            cache[uid]=None
            return None
        parent=world(parents[uid])
        if parent is None:raise ValueError('Unresolved ancestor transform: '+d['name'])
        cache[uid]=parent@m
        return cache[uid]
    return nodes,parents,world


def sample(xs,ys,values,query):
    q=np.asarray(query);values=np.asarray(values).reshape(len(ys),len(xs))
    i=np.clip(np.searchsorted(xs,q[:,0],side='right')-1,0,len(xs)-2)
    j=np.clip(np.searchsorted(ys,q[:,1],side='right')-1,0,len(ys)-2)
    u=(q[:,0]-xs[i])/(xs[i+1]-xs[i]);v=(q[:,1]-ys[j])/(ys[j+1]-ys[j])
    return (1-u)*(1-v)*values[j,i]+u*(1-v)*values[j,i+1]+(1-u)*v*values[j+1,i]+u*v*values[j+1,i+1]


def fitted_stations(rows):
    """Fit corresponding line ranks at the highest observed resolution.

    Unioning two near-equal grids creates artificial narrow cells. Corresponding
    line ranks, resampled only when source counts differ, define one common grid.
    """
    rank=np.linspace(0,1,max(len(row) for row in rows))
    fitted=np.mean([np.interp(rank,np.linspace(0,1,len(row)),row) for row in rows],axis=0)
    if np.any(np.diff(fitted)<=0):raise ValueError('Common grid has collapsed cells')
    return fitted


def extract(folder):
    folder=Path(folder);identity=read_json(folder/'identity.json');s=read_json(folder/'snapshot.json')
    if not identity['repeated_read_equal'] or json_digest(s)!=identity['public_snapshot_sha256']:
        raise ValueError('Unverified source snapshot')
    nodes,parents,world=affine_world(s)
    roots=[n for n in nodes.values() if n['type']=='DepthRigRoot']
    if len(roots)!=1:raise ValueError('Reference must contain one depth rig root')
    root=roots[0];root_inv=np.linalg.inv(world(root['uuid']))
    grids={b['target']:nodes[b['target']] for b in root['bindings'] if b['targetKind']=='grid'}
    extents=[]
    for uid,d in grids.items():
        xs,ys=d['grid_axis_x'],d['grid_axis_y']
        p=np.array([[x,y,0,1] for y in ys for x in xs])
        extents.extend((p@(root_inv@world(uid)).T)[:,:2])
    extent=np.ptp(np.array(extents),axis=0)
    unit=max(1.,float(max(extent))*.42/2.9)
    bones={d['boneId']:d for d in nodes.values() if d['type']=='DepthBone'}
    core=['Pelvis','Spine','Chest','Neck','Head']
    if not all(name in bones for name in core):raise ValueError('Missing canonical anatomical bones')
    pelvis=(root_inv@world(bones['Pelvis']['uuid']))[:3,3]
    head=(root_inv@world(bones['Head']['uuid']))[:3,3]
    torso_length=float(np.linalg.norm(np.asarray(bones['Neck']['restHead'])[:2]-np.asarray(bones['Pelvis']['restHead'])[:2]))
    face=next(d for d in grids.values() if role(d['name'])=='face')
    face_matrix=root_inv@world(face['uuid'])
    face_width=float(np.ptp(face['grid_axis_x'])*face_matrix[0,0])
    if min(torso_length,face_width)<=0:raise ValueError('Degenerate reference frame')
    observations=[]
    bone_by_uuid={d['uuid']:name for name,d in bones.items()}
    for binding in root['bindings']:
        uid=binding['target']
        if uid not in grids:raise ValueError('Non-grid reference target requires explicit support')
        d=grids[uid];r=role(d['name'])
        xs=np.array(d['grid_axis_x']);ys=np.array(d['grid_axis_y']);matrix=root_inv@world(uid)
        head_role=r=='face' or r.startswith(('hair_','headwear'))
        anchor=head if head_role else pelvis
        length=face_width if head_role else torso_length
        origin=matrix[:3,3]
        raw=np.array(d['depths'])
        depth=raw*unit*matrix[2,2]
        # Store origin placement separately. Never replace it with relief gain.
        offset=float((origin[2]-anchor[2])/length)
        support=[float((matrix[0,0]*xs[0]+origin[0]-anchor[0])/length),
                 float((matrix[1,1]*ys[0]+origin[1]-anchor[1])/length),
                 float((matrix[0,0]*xs[-1]+origin[0]-anchor[0])/length),
                 float((matrix[1,1]*ys[-1]+origin[1]-anchor[1])/length)]
        parent=parents[uid]
        while parent is not None and parent not in grids:parent=parents[parent]
        settings=[]
        for setting in binding['sourceSettings']:
            settings.append({'bone':bone_by_uuid[setting['bone']],
                'weight':setting['weight'],'depth_scale':setting['depthScale'],
                'depth_offset':float(setting['depthOffset']*unit*matrix[2,2]/length),
                'source_rotation_radians':setting['rotation']})
        effective=[depth*setting['depth_scale']/length+setting['depth_offset']+offset for setting in settings]
        active=[setting for setting in settings if setting['weight']>0]
        depth_settings={(setting['depth_scale'],setting['depth_offset'],setting['source_rotation_radians']) for setting in active}
        if len(depth_settings)!=1:
            raise ValueError('Different active source depth planes require a multi-source field: '+r)
        source_scale,source_offset,source_rotation=next(iter(depth_settings))
        if abs(source_rotation)>1e-8:
            raise ValueError('Tilted source plane needs explicit XY registration: '+r)
        deformations=[]
        for b in s['bindings']:
            if b['target']['uuid']!=uid or b['name']!='deform':continue
            if b['parameter']['name'] not in ('Face::Yaw-Pitch','Face::Roll','Body::Yaw-Pitch','Body::Roll'):continue
            values=np.array(b['data']['values'],float).reshape(len(b['axisValues'][0]),len(b['axisValues'][1]),len(raw),2)
            values=values@matrix[:2,:2].T/length
            deformations.append({'parameter':b['parameter']['name'],
                'axes':[b['axisValues'][0],b['axisValues'][1] if len(b['axisValues'][1])>1 else [0.]],
                'values':values.tolist(),'is_set':b['data']['isSet'],'interpolation':b['interpolateMode']})
        observations.append({'role':r,'source_uuid':uid,'source_name':d['name'],
            'frame':'head_face_width' if head_role else 'pelvis_torso_length',
            'support':support,'u':((xs-xs[0])/np.ptp(xs)).tolist(),
            'v':((ys-ys[0])/np.ptp(ys)).tolist(),
            'depth_local':(depth*source_scale/length).tolist(),'node_z_offset':offset,
            'source_z_offset':source_offset,
            'depth_scale_absorbed_from_source':source_scale,
            'bone_sources':settings,'influence_rule':binding['influenceRule'],
            'deformation_bindings':deformations,
            'parent_surface':None if parent is None else role(grids[parent]['name']),
            'effective_depth_ranges_by_source':[[float(min(z)),float(max(z))] for z in effective],
            'raw_depth_range':[float(min(raw)),float(max(raw))]})
    drivers=[]
    for b in s['bindings']:
        if b['target']['uuid'] not in bone_by_uuid or not b['name'].startswith('transform.'):
            continue
        if b['parameter']['name'] not in ('Face::Yaw-Pitch','Face::Roll','Body::Yaw-Pitch','Body::Roll'):
            continue
        values=np.array(b['data']['values'],float)
        if '.t.' in b['name']:values/=torso_length
        drivers.append({'parameter':b['parameter']['name'],'bone':bone_by_uuid[b['target']['uuid']],
            'property':b['name'],'axes':[b['axisValues'][0],b['axisValues'][1] if len(b['axisValues'][1])>1 else [0.]],
            'values':values.tolist(),'is_set':b['data']['isSet'],
            'interpolation':b['interpolateMode'],
            'units':'radians' if '.r.' in b['name'] else 'torso_length' if '.t.' in b['name'] else 'scale'})
    graph=[]
    for name,d in bones.items():
        if name not in core and not any(name.startswith(prefix+'.') for prefix in ('Clavicle','UpperArm','Forearm','Hand','Thigh','Shin','Foot')):
            continue
        parent=parents[d['uuid']]
        while parent in bone_by_uuid and bone_by_uuid[parent] not in core and not any(bone_by_uuid[parent].startswith(prefix+'.') for prefix in ('Clavicle','UpperArm','Forearm','Hand','Thigh','Shin','Foot')):
            parent=parents[parent]
        graph.append({'bone':name,'parent':bone_by_uuid.get(parent),
                      'allow_parent_to_targets':d['allowParentToTargets'],
                      'lock_to_root':d['lockToRoot']})
    return {'identity':identity,'native_depth_unit':unit,'face_width':face_width,
            'torso_length':torso_length,'surfaces':observations,'drivers':drivers,
            'core_skeleton':sorted(graph,key=lambda x:x['bone'])}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--capture',action='append',required=True)
    p.add_argument('--out',required=True);p.add_argument('--audit',required=True)
    a=p.parse_args();sources=sorted([extract(path) for path in a.capture],key=lambda s:s['identity']['public_snapshot_sha256'])
    if len(sources)<2:raise ValueError('At least two designated references are required')
    if any(s['core_skeleton']!=sources[0]['core_skeleton'] for s in sources):
        raise ValueError('Canonical skeleton constraints disagree')
    groups=defaultdict(list);curves=defaultdict(list)
    for k,s in enumerate(sources):
        for row in s['surfaces']:groups[row['role']].append((k,row))
        for row in s['drivers']:curves[(row['parameter'],row['bone'],row['property'])].append((k,row))
    components={};residuals={}
    for r,rows in sorted(groups.items()):
        parents={row['parent_surface'] for _,row in rows};frames={row['frame'] for _,row in rows}
        if len(parents)!=1 or len(frames)!=1:raise ValueError('Component structure/frame conflict: '+r)
        us=fitted_stations([row['u'] for _,row in rows])
        vs=fitted_stations([row['v'] for _,row in rows])
        uv=np.array([[u,v] for v in vs for u in us])
        fields=np.array([sample(np.array(row['u']),np.array(row['v']),row['depth_local'],uv) for _,row in rows])
        placement=float(np.mean([row['node_z_offset'] for _,row in rows]))
        source_placement=float(np.mean([row['source_z_offset'] for _,row in rows]))
        depth=fields.mean(axis=0)
        # A common plane plus zero-mean relief; no attenuation or per-model gain.
        plane=float(depth.mean());relief=depth-plane
        support=np.mean([row['support'] for _,row in rows],axis=0)
        components[r]={'frame':next(iter(frames)),'parent_surface':next(iter(parents)),
            'support':support.tolist(),'axis_u':us.tolist(),'axis_v':vs.tolist(),
            'depth':{'node_offset':placement,'source_offset':source_placement,'plane_offset':plane,'relief':relief.tolist(),
                     'composition':'host_origin_z + length_unit * (node_offset + source_offset + plane_offset + relief)',
                     'source_scale_already_applied':True},
            'evidence_count':len(rows),
            'source_resolution':[[len(row['u']),len(row['v'])] for _,row in rows]}
        deformation_groups=defaultdict(list)
        for source_id,row in rows:
            for binding in row['deformation_bindings']:
                array=np.array(binding['values'])
                sampled=np.empty((*array.shape[:2],len(uv),2))
                for i in range(array.shape[0]):
                    for j in range(array.shape[1]):
                        for axis in (0,1):
                            sampled[i,j,:,axis]=sample(np.array(row['u']),np.array(row['v']),array[i,j,:,axis],uv)
                deformation_groups[binding['parameter']].append((source_id,binding,sampled))
        deform={}
        for parameter,entries in sorted(deformation_groups.items()):
            if any(e[1]['axes']!=entries[0][1]['axes'] or e[1]['interpolation']!=entries[0][1]['interpolation'] for e in entries):
                raise ValueError('Incompatible surface parameter axes: '+r+' '+parameter)
            pooled=np.mean([e[2] for e in entries],axis=0)
            deform[parameter]={'axes':entries[0][1]['axes'],'interpolation':entries[0][1]['interpolation'],
                'values':pooled.tolist(),'evidence_count':len(entries),
                'source_maximum_fit_error':[float(np.max(abs(e[2]-pooled))) for e in entries],
                'space':'root-oriented XY displacement / component length unit; local binding before ancestor deformation',
                'source_key_commitment_complete':all(np.array(e[1]['is_set']).all() for e in entries)}
        components[r]['deformations']=deform
        source_settings=[row['bone_sources'] for _,row in rows]
        if all(settings==source_settings[0] for settings in source_settings):
            components[r]['bone_sources']=[{**setting,'depth_scale':1.,'depth_offset':0.} for setting in source_settings[0]]
        else:
            components[r]['bone_sources']=None
            components[r]['source_mapping_status']='different source skeletal controls; common mapping not yet resolved'
        residuals[r]=[{'source':k,'normalized_depth_rmse':float(np.sqrt(np.mean((fields[j]+row['node_z_offset']+row['source_z_offset']-depth-placement-source_placement)**2))),
                      'normalized_depth_max_error':float(np.max(abs(fields[j]+row['node_z_offset']+row['source_z_offset']-depth-placement-source_placement))),
                      'normalized_support_max_error':float(max(abs(np.array(row['support'])-support)))}
                     for j,(k,row) in enumerate(rows)]
    common=[];varying=[]
    for key,rows in sorted(curves.items()):
        if len(rows)!=len(sources):
            varying.append({'key':list(key),'reason':'not present in all references'});continue
        first=rows[0][1]
        if any(row['axes']!=first['axes'] or row['interpolation']!=first['interpolation'] for _,row in rows):
            varying.append({'key':list(key),'reason':'axis or interpolation differs'});continue
        arrays=np.array([row['values'] for _,row in rows]);spread=float(np.max(np.ptp(arrays,axis=0)))
        if spread>1e-5:
            varying.append({'key':list(key),'reason':'reference values differ','maximum_spread':spread,'units':first['units']});continue
        common.append({k:v for k,v in first.items() if k!='is_set'})
    template={'schema_version':'rig-common-reference-template/1','status':'measured_candidate_not_runtime_accepted',
        'template_count':1,'character_selection':False,'reference_count':len(sources),
        'normalization':'shared head face width / pelvis-to-neck torso length; Z origin at host bone',
        'core_skeleton':sources[0]['core_skeleton'],'components':components,'common_bone_curves':common,
        'unresolved_driver_differences':varying,
        'provenance':{'public_snapshot_sha256':[s['identity']['public_snapshot_sha256'] for s in sources],
                      'generator_sha256':digest(Path(__file__))},
        'acceptance':{'depth_transfer_verified':False,'pose_transfer_verified':False,
                      'attachment_continuity_verified':False,'reference_render_comparison_verified':False}}
    template['content_sha256']=json_digest(template)
    write_json(a.out,template)
    write_json(a.audit,{'template_sha256':template['content_sha256'],'source_observations':sources,
                       'fitting_residuals':residuals,'averaging_space':'normalized local fields and node placement separately',
                       'source_models_modified':False,'candidate_only':True})
    print('One template;',len(components),'components;',len(common),'common bone curves;',len(varying),'unresolved driver differences')
    for r in ('face','hair_front','hair_side/l','hair_side/r'):
        c=components[r];print(r,'grid',len(c['axis_u']),len(c['axis_v']),'placement',c['depth']['node_offset'],'plane',c['depth']['plane_offset'],'max fit error',max(v['normalized_depth_max_error'] for v in residuals[r]))


if __name__=='__main__':main()
