"""Compile one anatomy-registered template from the designated NJC captures."""
import argparse
from collections import defaultdict
from pathlib import Path
import numpy as np
from compile_reference_template import extract, affine_world, role
from riglib.data import read_json, write_json, json_digest, digest
from riglib.reference_fields import (CORE_PARAMETERS, TRANSFER_PARAMETERS, DEPTH_ANGLE_PARAMETERS, StaticReference, make_frames,
                                    frame_role, to_frame, from_frame, delta_to_frame, sample, fit_positive_cells, evaluate_component)
from riglib.semantic_registration import facial_landmarks,observed_landmarks,build_charts,affine_from
from riglib.reference_skeleton import compile_support
from riglib.resampling import anchored_axis
from riglib.facial_controls import compile_controls


def source(folder):
    folder=Path(folder); measured=extract(folder); snapshot=read_json(folder/'snapshot.json')
    nodes, parents, world=affine_world(snapshot)
    bones={d['boneId']: {'head':d['restHead'], 'tail':d['restTail']}
           for d in nodes.values() if d['type']=='DepthBone'}
    face_parts=[d for d in nodes.values() if d['type']=='Part' and d['name'].lower() in ('face','face_skin')]
    if len(face_parts)!=1: raise ValueError('Reference needs an unambiguous face surface')
    face=face_parts[0]; m=world(face['uuid'])
    xy=np.asarray(face['mesh']['verts']).reshape(-1,2)@m[:2,:2].T+m[:2,3]
    frames=make_frames(bones,np.r_[xy.min(0),xy.max(0)])
    evaluator=StaticReference(snapshot,nodes,parents,world)
    rig_root=next(d for d in nodes.values() if d['type']=='DepthRigRoot')
    source_bindings={b['target']:b for b in rig_root['bindings']}
    materials=[]
    for uid,d in nodes.items():
        if d['type']!='Part' or not d.get('enabled',True):continue
        local=np.asarray(d['mesh']['verts']).reshape(-1,2)
        for parameter in CORE_PARAMETERS:
            binding=evaluator.bindings.get((uid,parameter))
            if binding is not None:
                local=local+np.asarray(binding['data']['values'][2][2 if parameter.endswith('Yaw-Pitch') else 0]).reshape(-1,2)
        matrix=world(uid)
        materials.append((d['name'],local@matrix[:2,:2].T+matrix[:2,3]))
    landmarks=observed_landmarks(bones,facial_landmarks(materials))
    bone_z={d['boneId']:float(world(d['uuid'])[2,3]) if not d['lockToRoot'] else float(d['transform']['trans'][2])
            for d in nodes.values() if d['type']=='DepthBone'}
    torso=measured['torso_length']
    result=[]
    for row in measured['surfaces']:
        uid=row['source_uuid'];d=nodes[uid];m=world(uid);f=frames[frame_role(row['role'])]
        xy=np.array([[x,y] for y in d['grid_axis_y'] for x in d['grid_axis_x']])@m[:2,:2].T+m[:2,3]
        registered=to_frame(xy,f)
        parent,path=evaluator.ancestors(uid)
        stopper=next((p for p in path if nodes[p]['type']!='Part'),None)
        attachment={'mode':'none'}
        if parent is not None:
            if stopper is None:attachment={'mode':'parent_grid_field'}
            elif nodes[stopper]['type']=='Node':attachment={'mode':'translation_at_node_origin',
                'point_in_child_frame':to_frame(world(stopper)[:2,3][None,:],f)[0].tolist()}
            else:raise ValueError('Unresolved reference support boundary')
        raw=np.asarray(d['depths']);active=[s for s in row['bone_sources'] if s['weight']>0]
        # A Z plane is global geometry. Store it relative to the pelvis Z origin,
        # not independently relative to each component's host bone.
        length=measured['face_width'] if row['frame']=='head_face_width' else torso
        z=raw*measured['native_depth_unit']*row['depth_scale_absorbed_from_source']
        host='Head' if frame_role(row['role'])=='head' else 'Pelvis'
        z+=row['source_z_offset']*length+m[2,3]-bone_z[host]
        z_unit=float(frames['head']['matrix'][0][0]) if host=='Head' else torso
        result.append({'row':row,'grid':d,'matrix':m,'frame':f,
                       'support':np.r_[registered.min(0),registered.max(0)],
                       'z':z/z_unit,'uid':uid,'attachment':attachment,
                       'influence_rule':source_bindings[uid]['influenceRule']})
    return {'measured':measured,'snapshot':snapshot,'nodes':nodes,'parents':parents,'evaluator':evaluator,'frames':frames,
            'surfaces':result,'torso_length':torso,'landmarks':landmarks,
            'bone_z':{k:(v-bone_z['Pelvis'])/torso for k,v in bone_z.items()}}


def compile_template(folders):
    sources=sorted([source(f) for f in folders],key=lambda s:s['measured']['identity']['public_snapshot_sha256'])
    if len(sources)<2:raise ValueError('Use all designated references')
    charts=build_charts(sources)
    for src in sources:
        for row in src['surfaces']:
            d=row['grid'];m=row['matrix']
            if row['attachment']['mode']=='translation_at_node_origin':
                point=affine_from([row['attachment']['point_in_child_frame']],row['frame'])
                row['attachment']['point_in_child_frame']=to_frame(point,row['frame'])[0].tolist()
            xy=np.array([[x,y] for y in d['grid_axis_y'] for x in d['grid_axis_x']])@m[:2,:2].T+m[:2,3]
            q=to_frame(xy,row['frame']);row['support']=np.r_[q.min(0),q.max(0)]
    groups=defaultdict(list)
    for src in sources:
        for row in src['surfaces']:groups[row['row']['role']].append((src,row))
    components={};errors={}
    for name,rows in sorted(groups.items()):
        # Register the anatomy first; corresponding sample indices alone do not
        # register a face, a shoulder or a waist between different characters.
        support=np.mean([r['support'] for _,r in rows],axis=0)
        nx=max(len(r['grid']['grid_axis_x']) for _,r in rows)
        ny=max(len(r['grid']['grid_axis_y']) for _,r in rows)
        chart=charts[frame_role(name)]
        vertex_labels=(['eye_l_outer','eye_r_outer'] if frame_role(name)=='head' and name!='face'
                       else chart['labels'])
        anchors=np.asarray([chart['canonical'][chart['labels'].index(label)] for label in vertex_labels])
        # The common template itself has the observed reference budget.
        # Landmarks relocate existing lines; adding their coordinates to a
        # uniform axis silently creates a higher-resolution template.
        xs=anchored_axis(support[0],support[2],nx,
            anchors[(anchors[:,0]>support[0])&(anchors[:,0]<support[2]),0])
        ys=anchored_axis(support[1],support[3],ny,
            anchors[(anchors[:,1]>support[1])&(anchors[:,1]<support[3]),1])
        query=np.array([[x,y] for y in ys for x in xs]);zs=[];poses=defaultdict(list)
        source_pose_errors={}
        for src,r in rows:
            root=from_frame(query,r['frame']);m=r['matrix'];d=r['grid']
            local=(root-m[:2,3])@np.linalg.inv(m[:2,:2]).T
            zs.append(sample(d['grid_axis_x'],d['grid_axis_y'],r['z'],local)[:,0])
            inverse=np.linalg.inv(r['frame']['matrix'])
            for parameter in TRANSFER_PARAMETERS:
                shape=(5,5 if parameter.endswith('Yaw-Pitch') else 1,len(query),2)
                values=np.empty(shape)
                for i in range(shape[0]):
                    for j in range(shape[1]):
                        # The chart selects neutral anatomical locations.
                        # A Body motion vector belongs to the anatomical
                        # basis; warping its posed endpoint through the neutral
                        # TPS also warps the authored rotation and joint arc.
                        values[i,j]=src['evaluator'].local_at(r['uid'],parameter,i,j,root)@inverse.T
                poses[parameter].append(values)
        depth=np.mean(zs,axis=0);plane=float(depth.mean())
        deformations={}
        for parameter,values in poses.items():
            mean=np.mean(values,axis=0)
            # Numeric noise at the true neutral is removed, never a pose gain.
            neutral=mean[2,2 if mean.shape[1]==5 else 0]
            if np.max(abs(neutral))>1e-5:raise ValueError('Reference has nonzero neutral: '+name)
            mean[2,2 if mean.shape[1]==5 else 0]=0
            deformations[parameter]={'axes':[[-1,-.5,0,.5,1],[-1,-.5,0,.5,1] if mean.shape[1]==5 else [0]],
                'values':mean.tolist(),'space':'local residual displacement in registered anatomical frame',
                'interpolation':'Linear','orientation_fit':[]}
            source_pose_errors[parameter]=[float(np.max(np.linalg.norm(v-mean,axis=-1))) for v in values]
        modes={r['attachment']['mode'] for _,r in rows}
        if len(modes)!=1:raise ValueError('Reference support modes disagree: '+name)
        attachment={'mode':next(iter(modes))}
        if attachment['mode']=='translation_at_node_origin':
            attachment['point_in_child_frame']=np.mean([r['attachment']['point_in_child_frame'] for _,r in rows],axis=0).tolist()
        components[name]={'frame':frame_role(name),'axis_x':xs.tolist(),'axis_y':ys.tolist(),'attachment':attachment,
            'vertex_landmarks':vertex_labels,
            'vector_transport':'anatomical_basis_linear',
            'depth':{'plane_offset':plane,'relief':(depth-plane).tolist(),
                     'units':'face width' if frame_role(name)=='head' else 'pelvis-to-neck length',
                     'origin':'Head' if frame_role(name)=='head' else 'Pelvis'},
            'deformations':deformations,'evidence_count':len(rows),
            'parent_surface':rows[0][1]['row']['parent_surface'],
            'source_resolution':[[len(r['grid']['grid_axis_x']),len(r['grid']['grid_axis_y'])] for _,r in rows]}
        if name.split('/')[0] in ('arm','sleeve'):
            settings=[{'bones':[b['bone'] for b in r['row']['bone_sources'] if b['weight']>0],
                       'weights':[b['weight'] for b in r['row']['bone_sources'] if b['weight']>0],
                       'influence_rule':r['influence_rule']} for _,r in rows]
            if any(s!=settings[0] for s in settings):raise ValueError('Reference arm source settings disagree: '+name)
            if any(w!=1. for w in settings[0]['weights']):raise ValueError('Non-unit arm source weight needs explicit native adapter')
            components[name]['bone_binding']=settings[0]
        errors[name]={'depth_max_error_torso_units':[float(np.max(abs(z-depth))) for z in zs],
                      'pose_max_error_frame_units':source_pose_errors}
        vertex_errors=[]
        for src,r in rows:
            d=r['grid'];m=r['matrix']
            original=np.array([[x,y] for y in d['grid_axis_y'] for x in d['grid_axis_x']])@m[:2,:2].T+m[:2,3]
            q=to_frame(original,r['frame'])
            residual=sample(xs,ys,depth,q)[:,0]-r['z']
            vertex_errors.append({'samples':len(q),'maximum':float(np.max(abs(residual))),
                                  'rms':float(np.sqrt(np.mean(residual**2)))})
        errors[name]['depth_at_original_reference_vertices']=vertex_errors
    canonical_frames={}
    for name in sources[0]['frames']:
        origins=[];matrices=[]
        for s in sources:
            f=s['frames'][name];length=s['torso_length'];origin=s['frames']['body']['origin']
            origins.append((np.array(f['origin'])-origin)/length);matrices.append(np.array(f['matrix'])/length)
        canonical_frames[name]={'origin':np.mean(origins,axis=0).tolist(),'matrix':np.mean(matrices,axis=0).tolist()}
    pending=set(components);complete=set()
    while pending:
        ready=sorted(name for name in pending if components[name]['parent_surface'] is None or components[name]['parent_surface'] in complete)
        if not ready:raise ValueError('Reference surface hierarchy contains an unresolved parent or cycle')
        for name in ready:
            c=components[name];xs,ys=c['axis_x'],c['axis_y'];f=canonical_frames[c['frame']]
            query=np.array([[x,y] for y in ys for x in xs]);root=from_frame(query,f);inverse=np.linalg.inv(f['matrix'])
            for parameter,d in c['deformations'].items():
                for i in range(5):
                    for j in range(len(d['axes'][1])):
                        total=evaluate_component({'components':components},name,parameter,i,j,root,canonical_frames)@inverse.T
                        try:fitted,report=fit_positive_cells(query+total,xs,ys)
                        except ValueError as error:
                            d['orientation_fit'].append({'key':[i,j],'rejected':str(error)});continue
                        if report['corrected']:
                            d['values'][i][j]=(np.asarray(d['values'][i][j])+fitted-query-total).tolist()
                            d['orientation_fit'].append({'key':[i,j],**report})
            c['orientation_accepted']=not any('rejected' in x for d in c['deformations'].values() for x in d['orientation_fit'])
            complete.add(name);pending.remove(name)
    core=sources[0]['measured']['core_skeleton']
    if any(s['measured']['core_skeleton']!=core for s in sources):raise ValueError('Core constraints differ')
    support,helpers,support_audit=compile_support(sources,core)
    core_names={b['bone'] for b in core};support_names={b['bone'] for b in support};curve_groups=defaultdict(list)
    for src in sources:
        for d in src['measured']['drivers']:
            if d['bone'] in support_names:curve_groups[d['parameter'],d['bone'],d['property']].append(d)
    curves=[]
    for key,rows in sorted(curve_groups.items()):
        first=rows[0]
        if any(row['axes']!=first['axes'] for row in rows):raise ValueError('Driver axes disagree')
        # Reconcile the hierarchy before blending corresponding local curves.
        # An absent optional node is an identity transform in that reference.
        values=sum(np.asarray(r['values']) for r in rows)/len(sources)
        curves.append({**{k:v for k,v in first.items() if k not in ('values','is_set')},'values':values.tolist()})
    # Never embed per-reference Part displacement arrays in the shared template.
    materials,unmapped={},[]
    template={'schema_version':'rig-registered-reference-template/1','template_count':1,
        'status':'registered_runtime_candidate_pending_render_validation','character_selection':False,
        'components':components,'core_skeleton':core,'bone_curves':curves,'canonical_frames':canonical_frames,
        'facial_controls':compile_controls(sources),
        'support_skeleton':support,'support_bones':helpers,
        'material_corrections':materials,'unmapped_reference_material_corrections':unmapped,
        'part_correction_policy':{'reference_part_displacements':'prohibited',
            'required_inputs':['input PSD geometry','current parent pose','anatomical support'],
            'implementation_status':'required_shape_solver_missing'},
        'bone_z':{name:float(np.mean([s['bone_z'][name] for s in sources])) for name in sorted(core_names)},
        'provenance':{'public_snapshot_sha256':[s['measured']['identity']['public_snapshot_sha256'] for s in sources],
                      'compiler_sha256':digest(Path(__file__))},
        'motion_policy':'Face angles: native projection of fixed registered depth and offsets under reference bone curves; Body: registered residuals and parent support',
        'depth_angle_parameters':list(DEPTH_ANGLE_PARAMETERS),
        'reference_count':len(sources),'semantic_charts':charts,
        'registration':'shared semantic correspondence: eye corners, nose, mouth, torso stations and limb joints'}
    template['content_sha256']=json_digest(template)
    return template,{'template_sha256':template['content_sha256'],'source_fit_errors':errors,
                     'support_paths':support_audit,'visual_acceptance':False}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--capture',action='append',required=True)
    p.add_argument('--out',required=True);p.add_argument('--audit',required=True);a=p.parse_args()
    template,audit=compile_template(a.capture);write_json(a.out,template);write_json(a.audit,audit)
    print('Compiled one registered template:',len(template['components']),'surfaces;',len(template['bone_curves']),'core bone curves')
