"""Compile shared anatomical fields to explicit native DepthRig operations.

The compiler accepts source observations and semantic assignments, never source
names. Native API is responsible for skeletal deformation and binding baking.
"""
from collections import defaultdict
import numpy as np
from .anatomy import regular_mesh, depth_field, solve_scaffold
from .data import json_digest
from .hierarchy import compile_hierarchy
from .reference_compile import register_program
from .part_mesh import METHOD


def compile_native(observation, assembly, evidence, prior):
    digest=json_digest(observation)
    if assembly['observation_sha256']!=digest or evidence['observation_sha256']!=digest:
        raise ValueError('source observation hash mismatch')
    if not evidence.get('part_mesh_generation',{}).get('saved_readback_verified'):
        raise ValueError('Run NJC AutoMesh and verify saved Part meshes before compiling')
    scaffold=solve_scaffold(evidence,prior)
    by_id={str(n['uuid']):n for n in observation['nodes']}
    overrides=evidence.get('material_overrides',{})
    grouped=defaultdict(list)
    owner_of={}
    for material in assembly['materials']:
        uid=str(material['part'])
        role=overrides.get(uid,material)
        if 'chart' not in role or 'owner' not in role:
            raise ValueError(f'Unresolved material semantic role: {uid}')
        grouped[role['chart']].append(by_id[uid]); owner_of[role['chart']]=role['owner']
    domains=[]; h=scaffold['body_height']; pad=h*prior['bounds_padding_body_height']
    for chart,nodes in sorted(grouped.items()):
        owner=owner_of[chart]; label=chart.split('/',1)[1]
        boxes=np.array([n['bounds']['nominal_world_xy'] for n in nodes],float)
        bounds=[min(boxes[:,0])-pad,min(boxes[:,1])-pad,max(boxes[:,2])+pad,max(boxes[:,3])+pad]
        xy,faces,xs,ys=regular_mesh(bounds,h*prior['grid_step_body_height'],prior['minimum_grid_segments'],prior['maximum_grid_segments'])
        # Stable subpixel quantization bounds decimal payload size without
        # changing sampling density or splitting any NJC operation.
        xs=np.round(xs,4);ys=np.round(ys,4)
        xy=np.array([[x,y] for y in ys for x in xs])
        kind='surface';offset=0.;side=None;radius=None
        if owner=='head':
            bones=['Head']
            if label=='hair:back':kind='back_hair';offset=h*.003
            elif label.startswith(('hair','headwear','ear')):offset=h*.004
        elif owner=='torso':
            bones=['Pelvis','Spine','Chest']
            if label in ('skirt','skirt_back','apron'):
                kind='skirt_back' if label=='skirt_back' else 'skirt_front'
                bones=['Pelvis']
                if label=='apron':offset=h*.003
            elif label=='tail':kind='appendage';bones=['Pelvis'];offset=-h*.025
            elif label=='neck':bones=['Neck'];kind='neck'
            elif label=='attachment:chest':bones=['Chest']
            elif label=='attachment:pelvis':bones=['Pelvis']
        else:
            family,tag=owner.split(':')
            side=evidence['side_mapping'][tag]
            radius=evidence['limb_radii'][owner]
            if family=='arm':bones=[f'UpperArm.{side}',f'Forearm.{side}',f'Hand.{side}']
            elif family=='leg':bones=[f'Thigh.{side}',f'Shin.{side}',f'Foot.{side}']
            else:raise ValueError('unsupported owner')
            if label=='foot':bones=[f'Foot.{side}']
            if label=='attachment:ankle':bones=[f'Foot.{side}']
            if label=='attachment:thigh':bones=[f'Thigh.{side}']
            if label=='hand':bones=[f'Hand.{side}']
            if label in ('sleeve','shoulder'):offset=radius*.2
        domain={'id':chart,'owner':owner,'kind':kind,'offset':offset,'side':side,'radius':radius,
                'support_bounds':bounds,'bounds_padding':pad,'bone_sources':bones,'axis_x':xs.tolist(),'axis_y':ys.tolist(),
                'depth_model_units':depth_field(xy,{'kind':kind,'owner':owner,'offset':offset,'side':side,'radius':radius,'support_bounds':bounds},scaffold,prior).tolist(),
                'parts':[]}
        for node in nodes:
            mesh=evidence['part_meshes'][str(node['uuid'])]
            if mesh.get('method')!=METHOD:raise ValueError('Part geometry did not originate from NJC AutoMesh')
            domain['parts'].append({'uuid':node['uuid'],'vertices':mesh['vertices'],'indices':mesh['indices'],'mesh_method':mesh['method'],
                                    'original_transform':node['transform'],'original_draw_properties':node['draw_properties']})
        domains.append(domain)
    bounds=np.array([d['support_bounds'] for d in domains])
    extent=max(max(bounds[:,2])-min(bounds[:,0]),max(bounds[:,3])-min(bounds[:,1]))
    # Current native targetview.d has one global depth unit for this root.
    scale=max(1.,extent*(.42/2.9))
    for d in domains:d['depths']=np.round(np.array(d['depth_model_units'])/scale,6).tolist()
    dr=prior['drivers']
    parameters=[
        {'name':'Face::Yaw-Pitch','vec2':True,'bindings':[{'bone':'Head','axis':'y','input':0,'degrees':dr['head_yaw_degrees']},{'bone':'Head','axis':'x','input':1,'degrees':dr['head_pitch_degrees']}]},
        {'name':'Face::Roll','vec2':False,'bindings':[{'bone':'Neck','axis':'z','input':0,'degrees':dr['head_roll_degrees']}]},
        {'name':'Body::Yaw-Pitch','vec2':True,'bindings':[{'bone':'Spine','axis':'y','input':0,'degrees':dr['body_yaw_degrees']},{'bone':'Spine','axis':'x','input':1,'degrees':dr['body_pitch_degrees']}]},
        {'name':'Body::Roll','vec2':False,'bindings':[{'bone':'Pelvis','axis':'z','input':0,'degrees':dr['body_roll_degrees']}]},
    ]
    # Limb motion belongs to the reference Body controls. Do not invent a
    # second family of Arm/Elbow/Leg/Knee parameters from legacy priors.
    roots=[n for n in observation['nodes'] if n['parent'] is None]
    if len(roots)!=1:raise ValueError('expected one source root')
    result={'schema_version':'rig-native-program/1','source':evidence['part_mesh_source'],
            'psd_import_source':observation['source'],'source_root':roots[0]['uuid'],
            'hierarchy':compile_hierarchy(domains,evidence),
            'scaffold':scaffold,'domains':domains,'parameters':parameters,'native_depth_scale':scale,
            'coordinate_basis':'current native targetview.d: shared root-space extent * (0.42/2.9), positive raw depth along positive local Z',
            'quantization':{'xy_model_units':0.0001,'depth_units':0.000001},
            'observation_sha256':digest,'assembly_sha256':assembly['content_sha256'],'evidence_sha256':json_digest(evidence),'prior_sha256':json_digest(prior)}
    result['content_sha256']=json_digest(result)
    return register_program(result,observation,evidence)
