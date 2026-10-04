"""Measured PSD regions and shared priors, independent of source Part counts."""
from pathlib import Path
import numpy as np
from .data import read_json,write_json,json_digest,digest
from .semantic_observation import observe_semantics

POLICY={'version':'2.2','alpha_threshold':32,'elbow_fraction':.52,'knee_fraction':.47,
        'merged_hand_start':.82,'section_band':.025,
        'arm_anatomy_support':'skin arm when present; sleeve only when the arm is concealed',
        'hip_support':'proximal leg alpha; garment hem is not a hip observation',
        'concealed_torso_stations':{'chest':.35,'waist':.75},
        'provenance':'joint fractions are shared priors; silhouette positions are PSD measurements'}


def section(cloud,fraction,axis=None):
    p=np.asarray(cloud,float)
    if not len(p):raise ValueError('Empty material region')
    axis=np.asarray([0.,1.] if axis is None else axis,float);axis/=np.linalg.norm(axis)
    perpendicular=np.array([axis[1],-axis[0]])
    t=p@axis;lo,hi=np.quantile(t,[.01,.99]);station=lo+fraction*(hi-lo)
    q=p[abs(t-station)<=max(1.,(hi-lo)*POLICY['section_band'])]
    if not len(q):q=p[np.argsort(abs(t-station))[:max(1,len(p)//100)]]
    return np.median(q@perpendicular)*perpendicular+station*axis


def derive(run,skill):
    run=Path(run).resolve();skill=Path(skill).resolve()
    src=read_json(run/'psd-source.json');reg=read_json(run/'registration.json')
    obs=read_json(run/'observation.json');spec=read_json(skill/'structures/material-roles.json')
    if src['source']['sha256']!=reg['psd_sha256']:raise ValueError('PSD registration hash mismatch')
    materials,assembly,semantics=observe_semantics(run,obs,src,reg,spec)
    write_json(run/'observation.json',obs)
    active=[m for m in materials if m['active'] and not m.get('rig_static')]
    capture=[];offsets=[]
    for m in materials:
        layer=m['layer'];asset=layer['asset'];b=np.array(m['node']['bounds']['nominal_world_xy']);s=np.array(layer['bounds'])
        offsets.append((b[:2]+b[2:])/2-(s[:2]+s[2:])/2)
        w,h=asset['size']
        scale=(b[2:]-b[:2])/np.maximum(s[2:]-s[:2],1)
        affine=np.eye(3);affine[0,0],affine[1,1]=scale;affine[:2,2]=b[:2]-scale*s[:2]
        capture.append({'part':m['part'],'layer_id':m['layer_id'],'name':m['name'],
                        'source_to_model':affine.tolist(),
                        'file':str(run/asset['path']),'sha256':asset['sha256'],
                        'pixel_to_model':[[(b[2]-b[0])/max(1,w-1),0,float(b[0])],
                                          [0,(b[3]-b[1])/max(1,h-1),float(b[1])],[0,0,1]],
                        'source_bbox':layer['bounds'],'model_bounds':b.tolist(),'size':[w,h]})
    translation=np.median(offsets,axis=0)
    # Nested native PSD imports round group pivots and odd texture dimensions.
    # Register each measured source rectangle to its own public native frame.
    # Keep the common translation as the scaffold's coordinate convention.
    for m,c in zip(materials,capture):
        a=np.asarray(c['source_to_model'])
        if min(a[0,0],a[1,1])<=0:raise ValueError('Degenerate imported material bounds')
        m['cloud']=m['cloud']@a[:2,:2].T+a[:2,2]-translation
        if 'landmark_cloud' in m:
            m['landmark_cloud']=m['landmark_cloud']@a[:2,:2].T+a[:2,2]-translation
    transform=np.eye(3);transform[:2,2]=translation
    evidence={'observation_sha256':json_digest(obs),'psd_sha256':src['source']['sha256'],
              'source_to_model':transform.tolist(),'kind':semantics['kind'],
              'semantic_materials':semantics['materials'],'static_materials':semantics.get('static_materials',[]),'policy':POLICY,'generator_sha256':digest(Path(__file__)),
              'semantic_review':{'status':'visual_review_required','method':'PSD names, ancestry and alpha support; decisions recorded'},
              'material_overrides':{},'depth_order_constraints':[]}
    write_json(run/'capture.json',{'psd_sha256':src['source']['sha256'],'observation_sha256':json_digest(obs),'materials':capture})
    def select(roles=None,features=None):
        return [m for m in active if (roles is None or m['role'] in roles) and (features is None or m['feature'] in features)]
    def joined(rows):return np.concatenate([m['cloud'] for m in rows]) if rows else np.empty((0,2))
    def feature_cloud(rows):return np.concatenate([m.get('landmark_cloud',m['cloud']) for m in rows])
    face_rows=select({'face'});face=joined(face_rows)
    if assembly is not None:
        # Order constraints are measured where opaque hair actually overlaps
        # face pixels. Preserve separate native composite scopes in the IDs.
        from PIL import Image
        roles={row['part']:row for row in assembly['materials']}
        nodes={row['uuid']:row for row in obs['nodes']}
        captures={row['part']:row for row in capture}
        def domain_id(m):
            parent=nodes[m['node']['parent']]
            return roles[m['part']]['chart']+'@'+parent.get('source_layer_id','root')
        for hair in select({'hair_front','hair_side'}):
            world=hair['cloud']+translation
            for skin in face_rows:
                c=captures[skin['part']];a=np.asarray(c['source_to_model'])
                pixels=(world-a[:2,2])@np.linalg.inv(a[:2,:2]).T-c['source_bbox'][:2]
                xy=np.floor(pixels).astype(int);alpha=np.asarray(Image.open(c['file']).convert('RGBA'))[:,:,3]
                valid=(xy[:,0]>=0)&(xy[:,1]>=0)&(xy[:,0]<alpha.shape[1])&(xy[:,1]<alpha.shape[0])
                keep=np.flatnonzero(valid);keep=keep[alpha[xy[keep,1],xy[keep,0]]>32]
                if not len(keep):continue
                keep=keep[::max(1,int(np.ceil(len(keep)/256)))]
                evidence['depth_order_constraints'].append({'front':domain_id(hair),'back':domain_id(skin),
                    'xy_model':world[keep].tolist(),'source':'overlapping PSD alpha and semantic front/side hair support'})
    center=float(np.median(face[:,0])) if len(face) else float(np.median(joined(active)[:,0]))
    features={f:select(features={f}) for f in {m['feature'] for m in active if m['feature']}}
    eyes=[]
    for side in ('R','L'):
        rows=[m for m in features.get('sclera',[]) if (np.median(m['cloud'][:,0])<center)==(side=='R')]
        if not rows:continue
        cloud=feature_cloud(rows);lo,hi=np.quantile(cloud[:,0],[.01,.99]);axis=[]
        for x in (lo,hi):
            q=cloud[abs(cloud[:,0]-x)<=max(2,(hi-lo)*.015)]
            axis.append([x,float(np.median(q[:,1]))])
        groups={'sclera':[m['part'] for m in rows]}
        for f in ('iris','upper','lower','corner','fold','brow'):
            groups[f]=[m['part'] for m in features.get(f,[]) if (np.median(m['cloud'][:,0])<center)==(side=='R')]
        eyes.append({'side':side,'part_groups':groups,'parts':{k:v[0] for k,v in groups.items() if v},
                     'canthi_model':(np.asarray(axis)+translation).tolist(),
                     'method':'alpha lateral quantile sections; feature groups, no fixed Part count'})
    evidence['eyes']=eyes
    mouth_rows=[m for m in active if (m['feature'] or '').startswith('mouth')]
    if mouth_rows:
        bases=features.get('mouth',[]) or features.get('mouth_outline',[]) or mouth_rows
        p=feature_cloud(bases);u=np.array([1.,0.])
        if len(eyes)==2:
            centers=[np.mean(e['canthi_model'],axis=0) for e in eyes];u=centers[1]-centers[0];u/=np.linalg.norm(u)
        v=np.array([-u[1],u[0]]);lo,hi=np.quantile(p@u,[.01,.99]);mid=float(np.median(p@v))
        axis=np.array([lo*u+mid*v,hi*u+mid*v])+translation
        evidence['mouth']={'part':bases[0]['part'],'parts':[m['part'] for m in mouth_rows],
                           'part_groups':{f:[m['part'] for m in mouth_rows if m['feature']==f] for f in sorted({m['feature'] for m in mouth_rows})},
                           'axis_model':axis.tolist()}
    evidence['face_parts']={'face':[m['part'] for m in face_rows],
                            'nose':[m['part'] for m in features.get('nose',[])],
                            'mouth':[m['part'] for m in mouth_rows]}
    face_landmarks={}
    for eye in eyes:
        side=eye['side'].lower();a,b=eye['canthi_model']
        face_landmarks['eye_'+side+'_outer']=a if side=='r' else b
        face_landmarks['eye_'+side+'_inner']=b if side=='r' else a
    if features.get('nose'):face_landmarks['nose']=(np.median(feature_cloud(features['nose']),axis=0)+translation).tolist()
    if mouth_rows:
        a,b=evidence['mouth']['axis_model'];face_landmarks.update(mouth_r=a,mouth_l=b,mouth=np.mean([a,b],axis=0).tolist())
    evidence['facial_landmarks_model']=face_landmarks
    if evidence['kind']!='humanoid':
        write_json(run/'evidence.json',evidence)
        write_json(run/'assembly.json',{'kind':evidence['kind'],'observation_sha256':json_digest(obs),
                                       'materials':semantics['materials'],'content_sha256':json_digest(semantics)})
        print('Derived local structure:',evidence['kind'],flush=True);return
    torso=joined(select({'torso','bodice','waistwear'}))
    if not len(face) or not len(torso):raise ValueError('Humanoid needs observed head and torso support regions')
    face_top=section(face,0);face_root=section(face,1)
    neck=joined(select({'neck'}));neck_base=section(neck,.9) if len(neck) else section(torso,.02)
    landmarks={};radii={};regions=[]
    def put(name,p,provenance='measured',method='PSD alpha section'):
        landmarks[name]={'xy':np.asarray(p).tolist(),'provenance':provenance,'weight':1.,'method':method,'source_sha256':src['source']['sha256']}
    put('head_top',face_top);put('head_root',face_root);put('neck_base',neck_base,'measured' if len(neck) else 'prior','neck alpha or proximal torso support')
    put('chest',section(torso,.4));put('waist',section(torso,.9))
    for side in ('R','L'):
        tag=side.lower()
        def sided(roles):
            p=joined(select(roles))
            if not len(p):return p
            return p[p[:,0]<center] if side=='R' else p[p[:,0]>=center]
        # A shoulder-spanning garment can extend to the neck or across both
        # arms. Its silhouette is coverage, not the anatomical arm centerline.
        # Measure visible arm skin when available; clothing remains assigned
        # to its original render/support domain and is not removed or cropped.
        skin_arm=sided({'arm'});hand=sided({'hand'})
        arm=sided({'arm','hand'}) if len(skin_arm) else sided({'sleeve','hand'})
        leg=sided({'leg'});foot=sided({'foot'})
        if not len(arm) or not len(leg):raise ValueError('Unresolved limb region '+side)
        arm_start=section(arm,.01);arm_end=section(hand,.99) if len(hand) else section(arm,.99)
        arm_axis=arm_end-arm_start;arm_axis/=np.linalg.norm(arm_axis)
        put('shoulder.'+side,section(arm,.02,arm_axis))
        put('elbow.'+side,section(arm,POLICY['elbow_fraction'],arm_axis),'prior','alpha centerline; common elbow fraction')
        wrist=section(hand,.03,arm_axis) if len(hand) else section(arm,POLICY['merged_hand_start'],arm_axis)
        put('wrist.'+side,wrist,'measured' if len(hand) else 'prior','separate hand alpha or merged arm distal region')
        put('hand_tip.'+side,arm_end)
        hip=section(leg,.01)
        put('hip.'+side,hip,'prior','proximal observed leg support; hidden attachment estimated without using garment hem')
        distal=section(foot,.98) if len(foot) else section(leg,.98)
        leg_axis=distal-hip;leg_axis/=np.linalg.norm(leg_axis)
        put('knee.'+side,section(leg,POLICY['knee_fraction'],leg_axis),'prior','alpha centerline; common knee fraction')
        put('ankle.'+side,section(foot,.08,leg_axis) if len(foot) else section(leg,.87,leg_axis),'measured' if len(foot) else 'prior')
        put('foot_tip.'+side,distal)
        for family,p,axis in [('arm',arm,arm_axis),('leg',leg,leg_axis)]:
            v=np.array([axis[1],-axis[0]]);t=p@axis;lo,hi=np.quantile(t,[.01,.99]);widths=[]
            for f in np.linspace(.15,.85,15):
                q=p[abs(t-(lo+f*(hi-lo)))<=max(1,(hi-lo)*.025)]
                if len(q):widths.append(np.ptp(q@v))
            radii[family+':'+tag]=max(1.,float(np.median(widths))/2)
            regions.append({'owner':family+':'+tag,'source_layers':[m['layer_id'] for m in select({'arm','sleeve','hand'} if family=='arm' else {'leg','foot'})],
                            'spatial_partition':'left of head center' if side=='R' else 'right of head center','longitudinal_axis':axis.tolist()})
    pelvis=(np.array(landmarks['hip.L']['xy'])+landmarks['hip.R']['xy'])/2;put('pelvis',pelvis,'prior','paired inferred hip midpoint')
    axis=pelvis-neck_base;length=np.linalg.norm(axis);unit=axis/length
    station_fractions=[]
    for role,f in [('chest',.35),('waist',.75)]:
        measured=np.asarray(landmarks[role]['xy']);t=float((measured-neck_base)@unit/length)
        station_fractions.append(t)
    gap=read_json(skill/'structures/humanoid-prior.json')['torso_axis']['minimum_station_gap']
    valid=bool(select({'torso'})) and min(np.diff([0,*station_fractions,1]))>gap
    for (role,f),t in zip([('chest',.35),('waist',.75)],station_fractions):
        if not valid:put(role,neck_base+f*axis,'prior','common ordered torso stations; garment sections fall outside anatomical station constraints')
        else:put(role,neck_base+t*axis,'prior','observed garment station projected onto the shared anatomical torso axis')
    lo,hi=np.quantile(face,[.01,.99],axis=0)
    shoulder=np.linalg.norm(np.asarray(landmarks['shoulder.L']['xy'])-landmarks['shoulder.R']['xy'])
    evidence.update(landmarks=landmarks,volumes={'head':{'center':((lo+hi)/2).tolist(),'radii':((hi-lo)/2).tolist()},
                    'torso':{'center':((neck_base+pelvis)/2).tolist(),'radii':[float(shoulder*.45),float(length/2)]}},
                    side_mapping={'r':'R','l':'L','both':'Both'},limb_radii=radii,material_regions=regions)
    for family in ('arm','leg'):
        radii[family+':both']=(radii[family+':r']+radii[family+':l'])/2
    write_json(run/'assembly.json',assembly);write_json(run/'evidence.json',evidence)
    print('Derived PSD scaffold and grouped facial mechanisms:',assembly['coverage'],flush=True)
