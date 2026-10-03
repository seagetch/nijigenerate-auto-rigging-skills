"""Measure a front humanoid from registered PSD alpha and declared shared priors.

Semantic name candidates require a saved visual review; no coordinates are
accepted from that review. Hidden joints use the explicit ratios below.
"""
import argparse,re
from pathlib import Path
import numpy as np
from PIL import Image
from riglib.data import read_json,write_json,json_digest,digest
from riglib.assembly import assemble_model,normalized_name

POLICY = {'version':'1.1', 'alpha_threshold':32, 'section_band':0.025,
          'arm_elbow_fraction':0.52, 'leg_knee_fraction':0.47,
          'hidden_hip_between_waist_and_leg_root':0.5,
          'volume_quantiles':[0.01,0.99]}


def derive(run, skill):
    run=Path(run).resolve(); skill=Path(skill).resolve()
    src=read_json(run/'source/psd-source.json'); reg=read_json(run/'registration.json')
    obs=read_json(run/'observation.json'); spec=read_json(skill/'structures/material-roles.json')
    if src['source']['sha256']!=reg['psd_sha256']:raise ValueError('PSD registration hash mismatch')
    layers={r['id']:r for r in src['layers']}; nodes={r['uuid']:r for r in obs['nodes']}
    assembly=assemble_model(obs,spec)
    points={}; materials=[]; roles={}; offsets=[]
    for pair in reg['mapping']:
        layer=layers[pair['layer_id']]; node=nodes[pair['part']]
        asset=layer['asset']; im=Image.open(run/'source'/asset['path']).convert('RGBA')
        a=np.asarray(im)[:,:,3]; y,x=np.nonzero(a>POLICY['alpha_threshold'])
        points[pair['part']]=np.c_[x+layer['bounds'][0]+.5,y+layer['bounds'][1]+.5]
        b=np.array(node['bounds']['nominal_world_xy']); source=np.array(layer['bounds'])
        offsets.append((b[:2]+b[2:])/2-(source[:2]+source[2:])/2)
        matrix=[[float((b[2]-b[0])/max(1,im.width-1)),0,float(b[0])],
                [0,float((b[3]-b[1])/max(1,im.height-1)),float(b[1])],[0,0,1]]
        materials.append({'part':pair['part'],'layer_id':pair['layer_id'],'name':pair['name'],
            'file':str(run/'source'/asset['path']),'sha256':asset['sha256'],'pixel_to_model':matrix,
            'source_bbox':layer['bounds'],'model_bounds':b.tolist(),'size':list(im.size)})
    translation=np.median(offsets,axis=0)
    if np.max(np.abs(np.array(offsets)-translation))>1:raise ValueError('Import is not a common pixel-scale translation')
    transform=np.eye(3);transform[:2,2]=translation
    for m in assembly['materials']:
        if 'role' in m:roles.setdefault(m['role']['rule'],[]).append(m)
    # Resolve ambiguous support semantically, retaining the source and rationale.
    unknown=[m for m in assembly['materials'] if m['state']=='unassigned']
    semantic=[]
    for m in unknown:
        if not re.search(spec['hanging_attachment_pattern'],normalized_name(m['name'])):
            raise ValueError('Unresolved semantic candidate: '+m['name'])
        p=points[m['part']];root=p[p[:,1]<=np.quantile(p[:,1],.05)].mean(axis=0)
        candidates=[]
        for support in assembly['materials']:
            role=support.get('role',{})
            if role.get('usage') not in ('garment','covering','free_surface','attachment'):continue
            cloud_support=points[support['part']]
            if not len(cloud_support):continue
            distance=float(np.min(np.linalg.norm(cloud_support-root,axis=1)))
            candidates.append((distance,str(support['part']),support))
        if not candidates:raise ValueError('No observed support for hanging attachment')
        candidates.sort(key=lambda row:row[:2]);support=candidates[0][2]
        semantic.append({'part':m['part'],'role':support['role']['rule'],'side_tag':support['role']['side_tag'],
                         'provenance':'source_annotation','reason':'generic hanging-attachment name candidate; support ranked by proximal alpha distance',
                         'support_part':support['part'],'support_candidates':[{'part':x[2]['part'],'distance':x[0]} for x in candidates]})
    sem={'schema_version':'rig-semantic-evidence/1','observation_sha256':json_digest(obs),'materials':semantic}
    assembly=assemble_model(obs,spec,sem); roles={}
    for m in assembly['materials']:roles.setdefault(m['role']['rule'],[]).append(m)
    def cloud(role,tag=None):
        rows=[m for m in roles.get(role,[]) if tag is None or m['role']['side_tag']==tag]
        if not rows:raise ValueError('Missing measured role '+role)
        return np.concatenate([points[m['part']] for m in rows])
    def section(p,f):
        lo,hi=np.quantile(p[:,1],[.01,.99]); y=lo+f*(hi-lo)
        q=p[np.abs(p[:,1]-y)<=max(1,(hi-lo)*POLICY['section_band'])]
        return np.array([np.median(q[:,0]),y])
    face=cloud('face'); neck=cloud('neck')
    torso=np.concatenate([cloud(r) for r in ('bodice','waistwear') if r in roles])
    landmarks={}; supports={}
    def put(name,p,provenance='measured',method='alpha horizontal section median'):
        landmarks[name]={'xy':np.asarray(p).tolist(),'provenance':provenance,'weight':1,
                         'method':method,'source_sha256':src['source']['sha256']}
    put('head_top',section(face,0));put('head_root',section(face,1));put('neck_base',section(neck,.9))
    for name,fraction in [('waist',.9),('chest',.4)]:
        put(name,section(torso,fraction),method='garment alpha section; longitudinal station evidence only')
        landmarks[name]['constraint_scope']='longitudinal_torso_station'
    tags=sorted({m['role']['side_tag'] for m in roles['arm']},key=lambda t:np.median(cloud('arm',t)[:,0]))
    if len(tags)!=2:raise ValueError('Expected two independently observed arm sides')
    side_mapping={tags[0]:'R',tags[1]:'L'}
    limb_radii={}
    for tag,side in side_mapping.items():
        arm=cloud('arm',tag); hand=cloud('hand',tag); leg=cloud('leg',tag); foot=cloud('foot',tag)
        put('shoulder.'+side,section(arm,.02));put('elbow.'+side,section(arm,POLICY['arm_elbow_fraction']),'prior','alpha centerline with declared elbow fraction')
        wrist=(section(arm,.94)+section(hand,.06))/2
        put('wrist.'+side,wrist,'prior','mean of overlapping arm distal and hand proximal sections')
        put('hand_tip.'+side,section(hand,.98))
        hip=section(leg,.01); hip[1]=(hip[1]+landmarks['waist']['xy'][1])/2
        put('hip.'+side,hip,'prior','hidden hip between observed waist and proximal leg')
        put('knee.'+side,section(leg,POLICY['leg_knee_fraction']),'prior','alpha centerline with declared knee fraction')
        put('ankle.'+side,section(foot,.08));put('foot_tip.'+side,section(foot,.98))
        for family,p in [('arm',arm),('leg',leg)]:
            widths=[]
            for f in np.linspace(.15,.85,15):
                center=section(p,f);q=p[abs(p[:,1]-center[1])<2]
                if len(q):widths.append(np.ptp(q[:,0]))
            limb_radii[family+':'+tag]=float(np.median(widths)/2)
    put('pelvis',(np.array(landmarks['hip.L']['xy'])+landmarks['hip.R']['xy'])/2,'prior','paired hidden hip midpoint')
    volumes={}
    lo,hi=np.quantile(face,[.01,.99],axis=0)
    volumes['head']={'center':((lo+hi)/2).tolist(),'radii':((hi-lo)/2).tolist()}
    top=np.array(landmarks['neck_base']['xy']);bottom=np.array(landmarks['pelvis']['xy'])
    shoulder_width=np.linalg.norm(np.array(landmarks['shoulder.L']['xy'])-landmarks['shoulder.R']['xy'])
    volumes['torso']={'center':((top+bottom)/2).tolist(),'radii':[float(shoulder_width*.45),float(np.linalg.norm(bottom-top)/2)]}
    overrides={}
    # Front/side hair must remain in front of the face where their observed
    # opaque pixels overlap. These are PSD measurements, not authored offsets.
    face_pixels={tuple(p) for p in face}
    hair_samples={}
    for material in assembly['materials']:
        if material['role']['rule'] not in ('hair_front','hair_side'):continue
        chart=material['chart']
        overlap=[p for p in points[material['part']] if tuple(p) in face_pixels]
        hair_samples.setdefault(chart,[]).extend(overlap)
    depth_order=[]
    for chart,samples in sorted(hair_samples.items()):
        if not samples:continue
        xy=np.unique(np.array(samples),axis=0)+translation
        depth_order.append({'front':chart,'back':'head/face','xy_model':xy.tolist(),
            'method':'intersection of PSD face and front/side hair alpha above shared threshold'})
    eyes=[]
    features={role:[m['part'] for m in assembly['materials'] if re.search(pattern,normalized_name(m['name']))]
              for role,pattern in spec['facial_feature_patterns'].items()}
    sclera=sorted(features['sclera'],key=lambda uid:float(np.median(points[uid][:,0])))
    if len(sclera)!=2:raise ValueError('Two resolved eye-white regions are required')
    eye_centers=np.array([points[uid].mean(axis=0) for uid in sclera])
    for eye_index,sclera_id in enumerate(sclera):
        side='R' if eye_index==0 else 'L';ids={'sclera':sclera_id}
        for role in ('upper','lower','iris','corner','fold','tip'):
            candidates=[uid for uid in features[role] if np.argmin(np.linalg.norm(eye_centers-points[uid].mean(axis=0),axis=1))==eye_index]
            if len(candidates)>1 or (not candidates and role in ('upper','lower','iris')):raise ValueError('Unresolved eye feature role: '+role)
            if candidates:ids[role]=candidates[0]
        p=points[ids['sclera']];xl,xr=np.quantile(p[:,0],[.01,.99]); centers=[]
        for x in (xl,xr):
            edge=p[abs(p[:,0]-x)<2];centers.append([x,float(np.median(edge[:,1]))])
        eyes.append({'side':side,'parts':ids,'canthi_model':(np.array(centers)+translation).tolist(),
                     'method':'sclera alpha lateral quantile sections; PSD source side resolved spatially'})
    if len(features['mouth'])!=1 or len(features['nose'])!=1:raise ValueError('Unresolved facial feature evidence')
    mouth_id=features['mouth'][0];p=points[mouth_id];lo,hi=np.quantile(p,[.01,.99],axis=0)
    axis=np.array([[lo[0],(lo[1]+hi[1])/2],[hi[0],(lo[1]+hi[1])/2]])+translation
    evidence={'observation_sha256':json_digest(obs),'psd_sha256':src['source']['sha256'],
        'source_to_model':transform.tolist(),'landmarks':landmarks,'volumes':volumes,
        'side_mapping':side_mapping,'limb_radii':limb_radii,'material_overrides':overrides,
        'depth_order_constraints':depth_order,
        'eyes':eyes,'mouth':{'part':mouth_id,'axis_model':axis.tolist()},
        'face_parts':{'face':[m['part'] for m in roles['face']],'nose':features['nose'],'mouth':features['mouth']},
        'policy':POLICY,'generator_sha256':digest(Path(__file__)),
        'semantic_review':{'status':'visual_review_required','method':'name candidates and spatial support ranking; no automatic visual approval','suffix_policy':'opaque identifiers'},
        'limitations':['Hidden joints and thickness are declared priors, not observed truth.',
                        'Name-assisted candidates; this run does not establish anonymous-layer recognition.']}
    capture={'psd_sha256':src['source']['sha256'],'observation_sha256':json_digest(obs),'materials':materials}
    for name,value in [('assembly',assembly),('evidence',evidence),('capture',capture),('semantic-selection',sem)]:write_json(run/(name+'.json'),value)
    print('Generated source-linked scaffold evidence:',assembly['coverage'],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True)
    a=p.parse_args();derive(a.run,Path(__file__).resolve().parents[1])
