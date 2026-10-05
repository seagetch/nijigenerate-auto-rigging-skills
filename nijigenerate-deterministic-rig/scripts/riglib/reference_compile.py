"""Apply the single bundled anatomical reference template to PSD observations."""
from pathlib import Path
import numpy as np
from .data import read_json, json_digest
from .reference_fields import make_frames, to_frame, from_frame, sample, CORE_PARAMETERS, DEPTH_ANGLE_PARAMETERS
from .semantic_registration import facial_landmarks,observed_landmarks,install_charts
from .resampling import choose_grid,quantize_deformation
from .reference_skeleton import install_support
from .carrier import make_carrier,to_local,to_root,local_frames,bounds_corners


def register_bilateral(domain,template,frames,scaffold,by_id,torso,checks):
    """Sample both anatomical fields onto one unsplit bilateral source Part.

    Distance to the fitted limb polylines gives continuous partition weights;
    artwork is neither duplicated nor assigned wholly to its centroid's side.
    """
    from .resampling import anchored_axis,calibrated_depth
    family=domain['owner'].split(':')[0]
    names=[family+'/'+s for s in ('r','l')]
    comps=[template['components'][name] for name in names]
    boxes=np.array([by_id[p['uuid']]['bounds']['nominal_world_xy'] for p in domain['parts']])
    lower=boxes[:,:2].min(0)-domain['bounds_padding'];upper=boxes[:,2:].max(0)+domain['bounds_padding']
    counts=[max(max(r[k] for r in c['source_resolution']) for c in comps) for k in (0,1)]
    xs=anchored_axis(lower[0],upper[0],counts[0]*2,[]);ys=anchored_axis(lower[1],upper[1],counts[1],[])
    xy=np.array([[x,y] for y in ys for x in xs]);dist=[]
    roles=('shoulder','elbow','wrist','hand_tip') if family=='arm' else ('hip','knee','ankle','foot_tip')
    for side in ('R','L'):
        pts=[np.asarray(scaffold['landmarks'][r+'.'+side]) for r in roles];segments=[]
        for a,b in zip(pts[:-1],pts[1:]):
            t=np.clip((xy-a)@(b-a)/np.dot(b-a,b-a),0,1)
            segments.append(np.linalg.norm(xy-a-t[:,None]*(b-a),axis=1))
        dist.append(np.min(segments,axis=0))
    d=np.array(dist);w=1/np.maximum(d,torso*.002)**4;w/=w.sum(0)
    depth=sum(w[k]*(calibrated_depth(template,name,frames[c['frame']],xy,torso)+template['bone_z'][c['depth']['origin']]*torso)
              for k,(name,c) in enumerate(zip(names,comps)))
    fields={}
    domain.update(reference_component=names,registration_frame=frames['body'],
                  carrier_frame={'origin':[0.,0.],'rotation':0.},axis_x=xs.tolist(),axis_y=ys.tolist(),
                  support_bounds=np.r_[lower,upper].tolist(),depth_model_units=depth.tolist(),reference_deformations=fields,
                  resampling={'method':'continuous distance partition of two shared template components','axis_counts':[len(xs),len(ys)]})


def component_role(domain,evidence):
    owner=domain['owner'];label=domain.get('semantic_chart',domain['id']).split('/',1)[1]
    if owner=='head':
        fixed={'face':'face','hair:front':'hair_front','hair:back':'hair_back','headwear':'headwear'}
        if label in fixed:return fixed[label]
        if label.startswith('ear:'):return 'headwear'
        if label.startswith('hair:'):return 'hair_side/'+evidence['side_mapping'][label.split(':')[1]].lower()
    if owner=='torso':
        fixed={'body':'torso','neck':'torso','topwear_front':'topwear/front','topwear_waist':'topwear/waist',
               'skirt':'skirt/front','apron':'apron','tail':'tail',
               'attachment:chest':'torso','attachment:pelvis':'skirt/front'}
        if label in fixed:return fixed[label]
        if label.startswith('skirt_back:'):return 'train/'+evidence['side_mapping'][label.split(':')[1]].lower()
        if label=='skirt_back':return 'skirt/back'
    family,tag=owner.split(':');side=evidence['side_mapping'][tag].lower()
    if family=='arm':return ('sleeve' if label in ('sleeve','shoulder') else 'arm')+'/'+side
    if family=='leg':return 'leg/'+side
    raise ValueError('No reference component for material role '+domain['id'])


def register_program(program,observation,evidence,template=None):
    path=Path(__file__).resolve().parents[2]/'structures/reference-humanoid.registered.json'
    template=read_json(path) if template is None else template
    signed=dict(template);signature=signed.pop('content_sha256')
    if json_digest(signed)!=signature:raise ValueError('Common template hash mismatch')
    if template['template_count']!=1 or template['character_selection']:raise ValueError('Expected one common template')
    if template.get('depth_angle_parameters')!=list(DEPTH_ANGLE_PARAMETERS):
        raise ValueError('Template must declare native depth-only face angles')
    for collection in ('components',):
        if any(c['deformations'] for c in template[collection].values()):
            raise ValueError('Forbidden angle-specific face residual in shared template')
    scaffold=program['scaffold'];bones={b['id']:b for b in scaffold['bones']}
    by_id={n['uuid']:n for n in observation['nodes']}
    boxes=np.array([by_id[uid]['bounds']['nominal_world_xy'] for uid in evidence['face_parts']['face']])
    face_bounds=np.r_[boxes[:,:2].min(0),boxes[:,2:].max(0)]
    frames=make_frames(bones,face_bounds)
    materials=[]
    for node in observation['nodes']:
        if node['type']!='Part':continue
        b=node['bounds']['nominal_world_xy']
        materials.append((node['name'],[[b[0],b[1]],[b[2],b[3]]]))
    if 'semantic_charts' not in template:raise ValueError('Common template lacks required semantic correspondence')
    if 'facial_landmarks_model' not in evidence:
        raise ValueError('Compiler requires PSD-derived semantic facial landmarks')
    landmarks=observed_landmarks(bones,evidence['facial_landmarks_model'])
    install_charts(frames,landmarks,template['semantic_charts'])
    torso=np.linalg.norm(np.array(bones['Neck']['head'])-bones['Pelvis']['head'])
    face_width=face_bounds[2]-face_bounds[0]
    for bone in scaffold['bones']:
        bone['pose_origin_z']=template['bone_z'][bone['id']]*torso
    # Chest Bone follows the axial Spine-Neck line; breast relief stays in Grid depth.
    spine,chest,neck=(bones[name] for name in ('Spine','Chest','Neck'))
    lower=np.linalg.norm(np.asarray(chest['head'][:2])-spine['head'][:2])
    upper=np.linalg.norm(np.asarray(neck['head'][:2])-chest['head'][:2])
    if lower+upper<=0:raise ValueError('Collapsed Spine-Chest-Neck axis')
    chest['pose_origin_z']=(upper*spine['pose_origin_z']+lower*neck['pose_origin_z'])/(lower+upper)
    install_support(scaffold,template,frames,torso)
    domain_errors=[]
    for domain in program['domains']:
        if domain['owner'].endswith(':both'):
            register_bilateral(domain,template,frames,scaffold,by_id,torso,domain_errors)
            continue
        name=component_role(domain,evidence)
        if name not in template['components']:raise ValueError('Missing common template surface: '+name)
        c=template['components'][name];f=frames[c['frame']]
        if domain['owner'].startswith('arm:'):
            binding=c.get('bone_binding')
            if binding is None:raise ValueError('Arm Grid lacks the shared reference BoneSource mapping')
            domain['bone_sources']=binding['bones']
            domain['bone_influence_rule']=binding['influence_rule']
        if not c['orientation_accepted']:raise ValueError('Common reference component has unresolved inversions: '+name)
        cx,cy=np.array(c['axis_x']),np.array(c['axis_y'])
        corners=from_frame([[cx[0],cy[0]],[cx[0],cy[-1]],[cx[-1],cy[0]],[cx[-1],cy[-1]]],f)
        b=np.array(domain['support_bounds'])
        # The reference anatomical envelope and the target's actual material
        # coverage are independent constraints. Neither can silently crop art.
        # A local hand/garment carrier covers its own material support, not the
        # entire reference limb rectangle. The common depth field is sampled
        # on this support; do not create distant unused grid cells.
        carrier=make_carrier(domain['owner'],f)
        field_frames=local_frames(frames,carrier)
        support=np.concatenate([to_local(bounds_corners(by_id[p['uuid']]['bounds']['nominal_world_xy']),carrier)
                                for p in domain['parts']])
        lower=support.min(0)-domain['bounds_padding'];upper=support.max(0)+domain['bounds_padding']
        z=c['depth'];unit=face_width if z['units']=='face width' else torso
        print('Registering semantic surface '+domain['id'],flush=True)
        xs,ys,xy,depth,fields,resampling=choose_grid(template,name,field_frames,lower,upper,unit,
            [max(r[0] for r in c['source_resolution']),max(r[1] for r in c['source_resolution'])],
            to_local([landmarks[c['frame']][label] for label in c['vertex_landmarks']],carrier).tolist())
        depth+=template['bone_z'][z['origin']]*torso
        root_corners=to_root(bounds_corners(np.r_[lower,upper]),carrier)
        domain.update({'reference_component':name,'registration_frame':f,'carrier_frame':carrier,
            'support_bounds':np.r_[root_corners.min(0),root_corners.max(0)].tolist(),'axis_x':xs.tolist(),'axis_y':ys.tolist(),
            'depth_model_units':depth.tolist(),'reference_deformations':{},'resampling':resampling})
    by_role={d.get('reference_component'):d for d in program['domains']}
    body=by_role.get('torso')
    if body is not None:
        for side in ('L','R'):
            arm=by_role.get('arm/'+side.lower())
            if arm is None:continue
            bone=bones['UpperArm.'+side]
            shoulder=np.asarray(bone['head'][:2],float)
            elbow=np.asarray(bone['tail'][:2],float)
            axis=elbow-shoulder
            local_shoulder=to_local([shoulder],arm['carrier_frame'])
            body_z=float(sample(body['axis_x'],body['axis_y'],body['depth_model_units'],
                                to_local([shoulder],body['carrier_frame']))[0,0])
            arm_z=float(sample(arm['axis_x'],arm['axis_y'],arm['depth_model_units'],local_shoulder)[0,0])
            xy=np.array([[x,y] for y in arm['axis_y'] for x in arm['axis_x']])
            world=to_root(xy,arm['carrier_frame'])
            t=np.clip(((world-shoulder)@axis)/(axis@axis),0.,1.)
            weight=(1.-t)**2*(1.+2.*t)
            anchor=float(sample(arm['axis_x'],arm['axis_y'],weight,local_shoulder)[0,0])
            if anchor<=0.:raise ValueError('Arm shoulder is outside its depth field')
            arm['depth_model_units']=(np.asarray(arm['depth_model_units'])+
                                      (body_z-arm_z)*weight/anchor).tolist()
    by_domain={d['id']:d for d in program['domains']};order_reports=[]
    for constraint in evidence.get('depth_order_constraints',[]):
        aliases=program.get('domain_aliases',{})
        front=by_domain[aliases.get(constraint['front'],constraint['front'])];back=by_domain[aliases.get(constraint['back'],constraint['back'])]
        if front['bone_sources']!=['Head'] or back['bone_sources']!=['Head']:
            raise ValueError('Depth placement requires a shared verified head projection')
        xy=constraint['xy_model']
        zf=sample(front['axis_x'],front['axis_y'],front['depth_model_units'],to_local(xy,front['carrier_frame']))[:,0]
        zb=sample(back['axis_x'],back['axis_y'],back['depth_model_units'],to_local(xy,back['carrier_frame']))[:,0]
        gap=face_width*.001;shift=max(0.,float(np.max(zb-zf))+gap)
        front['depth_model_units']=(np.array(front['depth_model_units'])+shift).tolist()
        front['placement_offset_model_units']=shift
        order_reports.append({'front':front['id'],'back':back['id'],'opaque_overlap_samples':len(xy),
            'minimum_before':float(np.min(zf-zb)),'minimum_after':float(np.min(zf+shift-zb)),
            'plane_offset_model_units':shift,'minimum_gap_model_units':float(gap),
            'relief_changed':False,'method':'least nonnegative plane shift satisfying measured alpha-overlap ordering'})
    bounds=np.array([d['support_bounds'] for d in program['domains']])
    extent=max(bounds[:,2:].max(0)-bounds[:,:2].min(0));scale=max(1.,extent*.42/2.9)
    for domain in program['domains']:domain['depths']=np.round(np.array(domain['depth_model_units'])/scale,6).tolist()
    program['native_depth_scale']=float(scale)
    for spec in program['parameters']:
        if spec['name'] not in CORE_PARAMETERS:continue
        spec['deformation_authority']='native_depth_projection'
        spec['reference_curves']=[c for c in template['bone_curves'] if c['parameter']==spec['name']]
        spec['bindings']=[]
    program['reference_template']={'sha256':signature,'count':1,'reference_count':template['reference_count'],
        'frames':frames,'torso_length':float(torso),'orientation_checks':domain_errors,
        'motion_policy':template['motion_policy'],'depth_order_fit':order_reports}
    program['quantization']['reference_deformation']='6 significant digits, rounded to 0.0001 model units; orientation and transport checked after quantization'
    program.pop('content_sha256',None);program['content_sha256']=json_digest(program)
    return program
