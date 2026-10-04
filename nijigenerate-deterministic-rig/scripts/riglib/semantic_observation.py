"""PSD-derived material semantics, stable identities and mechanism observations.

Names supply candidates, ancestry supplies scope, and alpha supplies spatial
side/support. No model names, source UUID order or outside annotation is used.
"""
import re
import numpy as np
from PIL import Image
from .assembly import normalized_name, assemble_model
from .data import read_json, write_json, json_digest, digest


def name_tokens(value):
    name=normalized_name(value.rstrip('\x00').lstrip('*# '))
    name=re.sub(r'(?<=[a-z])(?=\d)|(?<=\d)(?=[a-z])','_',name)
    replacements={'irides':'iris','eyewhite':'sclera','eye_white':'sclera',
                  'eyeslash':'eyelash','innewr':'inner','sholder':'shoulder',
                  'cloths':'clothes','sodenhair':'side_hair'}
    for old,new in replacements.items():
        name=re.sub(r'(?<![a-z])'+old+r'(?![a-z])',new,name)
    return name


def candidate(name, ancestors):
    """Return structural role and optional local mechanism role."""
    n=name_tokens(name);a=[name_tokens(x) for x in ancestors]
    scope='_'.join(a)
    if re.search(r'(^|_)(background|backdrop)(_|$)',n):return 'background',None
    # A face painted on an accessory is not the character's head.
    ornament=bool(re.search(r'fox_decor|plush|baggage|objects',scope+'_'+n))
    if ornament:return 'pelvis_accessory',None
    if re.search(r'(^|_)(mouth|lip|tongue|teeth)(_|$)',n) or any(re.fullmatch(r'mouth(?:_composite)?',v) for v in a):
        if 'tongue' in n:f='mouth_tongue'
        elif 'teeth' in n:f='mouth_upper_teeth' if 'upper' in n else 'mouth_lower_teeth'
        elif 'outline' in n:f='mouth_outline'
        elif 'lip' in n:f='mouth_upper_lip' if 'upper' in n else 'mouth_lower_lip'
        else:f='mouth'
        return 'face_feature',f
    if re.search(r'(^|_)(eyebrow|brow)(_|$)',n):return 'face_feature','brow'
    if re.search(r'(^|_)(sclera|eyeball)(_|$)',n):return 'face_feature','sclera'
    if re.search(r'(^|_)eye_highlight(_|$)',n):return 'face_feature','iris'
    if re.search(r'(^|_)(iris|pupil)(_|$)',n):return 'face_feature','iris'
    if re.search(r'(^|_)(canthus|eye_corner|side_eyelash)(_|$)',n):return 'face_feature','corner'
    if re.search(r'(^|_)(eyelid|eyeline|lid|lash|eyelash|double_eyelid)(_|$)',n):
        return 'face_feature',('lower' if ('lower' in n or 'bottom' in n) else 'fold' if ('double' in n or 'fold' in n) else 'corner' if 'side' in n else 'upper')
    if re.fullmatch(r'nose(?:_\d+)?',n):return 'face_feature','nose'
    if re.fullmatch(r'(face|head_skin)(?:_\d+)?',n):return 'face',None
    if re.fullmatch(r'neck(?:_\d+)?',n):return 'neck',None
    if re.search(r'(^|_)(hair|bang|bangs|braid)(_|$)',n):
        if 'back' in n or n=='hair_ear_back':return 'hair_back',None
        if 'side' in n or 'cheek' in n or 'curl' in n or 'braid' in n:return 'hair_side',None
        return 'hair_front',None
    if re.search(r'earring|earwear',n):return 'headwear',None
    if re.search(r'(^|_)(ear|ears)(_|$)',n):return 'ear',None
    if re.search(r'(^|_)(headwear|headband|cap|forehead|temple|head|hair)_(bow|ribbon|flower|watch|cross)|^(headwear|headband|cap)(_|$)',n):return 'headwear',None
    if re.search(r'(^|_)(shoe|shoes|foot|footwear)(_|$)',n):return 'foot',None
    if re.search(r'(^|_)(hand|palm|finger|thumb)(_|$)',n):return 'hand',None
    if 'handwear' in n:return 'arm',None
    if re.search(r'(^|_)(arm|arms|upperarm|forearm)(_|$)',n):return 'arm',None
    if re.search(r'(^|_)(leg|legs|legwear|thigh|shin|pants|socks)(_|$)',n):return 'leg',None
    if re.search(r'(^|_)(sleeve|cuff|shoulder)(_|$)',n):return 'sleeve',None
    if 'tail' in n:return 'tail',None
    if 'apron' in n:return 'apron',None
    if re.search(r'skirt|bottomwear|train',n):return ('skirt_back' if 'back' in n else 'skirt'),None
    if re.search(r'corset|belt|waistwear',n):return 'waistwear',None
    if re.search(r'clothes|topwear|bodice|collar|parker|pocket',n):return 'bodice',None
    if re.search(r'(^|_)(body|torso|chest|pelvis)(_|$)',n):return 'torso',None
    if re.search(r'waist|hip',n):return 'pelvis_accessory',None
    # Inherit the nearest structural scope, without inheriting facial identity.
    for parent in reversed(a):
        if re.search(r'hand',parent):return 'hand',None
        if re.search(r'arms|arm',parent):return 'sleeve',None
        if re.search(r'legs|leg',parent):return 'leg',None
        if re.search(r'skirt',parent):return 'skirt',None
        if re.search(r'upper_body|torso|body',parent):return 'chest_accessory',None
        if re.search(r'cap|headwear',parent):return 'headwear',None
        if re.search(r'back_head|back_hair',parent):return 'hair_back',None
        if re.search(r'head',parent):return 'headwear',None
    return None,None


def source_materials(run, observation, manifest, registration):
    layers={r['id']:r for r in manifest['layers']}
    nodes={r['uuid']:r for r in observation['nodes']}
    result=[]
    for pair in sorted(registration['mapping'],key=lambda r:layers[r['layer_id']]['index_path']):
        layer=layers[pair['layer_id']];node=nodes[pair['part']]
        node['source_layer_id']=layer['id'];node['source_index_path']=layer['index_path'];node['source_order']=layer['flat_order']
        if not layer['asset']:continue
        image=Image.open(run/layer['asset']['path']).convert('RGBA')
        alpha=np.asarray(image)[:,:,3];y,x=np.nonzero(alpha>32)
        if not len(x):continue
        # Bounded deterministic sampling avoids quadratic cloud operations on
        # 5000px layers while keeping complete masks for geometric compilation.
        stride=max(1,int(np.ceil(len(x)/40000)));x=x[::stride];y=y[::stride]
        cloud=np.c_[x+layer['bounds'][0]+.5,y+layer['bounds'][1]+.5]
        parents=[];parent=layer['parent_id']
        while parent is not None:
            parents.insert(0,layers[parent]['name']);parent=layers[parent]['parent_id']
        role,feature=candidate(layer['name'],parents)
        landmark_cloud=None
        if feature == 'sclera':
            # Eye endpoints describe the main connected eye-white patch.
            # Detached paint specks remain in the artwork/AutoMesh coverage,
            # but cannot become an eye corner. Mouths and noses may contain
            # multiple intentional disconnected strokes and retain all pixels.
            from scipy.ndimage import label
            regions,count=label(alpha>32,structure=np.ones((3,3)))
            if count:
                sizes=np.bincount(regions.ravel());sizes[0]=0
                fy,fx=np.nonzero(regions==int(sizes.argmax()))
                step=max(1,int(np.ceil(len(fx)/40000)))
                landmark_cloud=np.c_[fx[::step]+layer['bounds'][0]+.5,fy[::step]+layer['bounds'][1]+.5]
        result.append({'part':node['uuid'],'layer_id':layer['id'],'layer':layer,'node':node,
                       'cloud':cloud,'role':role,'feature':feature,'ancestors':parents,
                       'active':layer['visible_effective'], 'name':node['name']})
        if landmark_cloud is not None:result[-1]['landmark_cloud']=landmark_cloud
    return result


def observe_semantics(run,observation,manifest,registration,spec,prepare_groups=None):
    materials=source_materials(run,observation,manifest,registration)
    from .static_materials import classify
    static=classify(run,materials)
    for m in materials:
        if m['part'] in static:m['rig_static']=True;m['role']='background'
    active=[m for m in materials if m['active'] and not m.get('rig_static')]
    faces=[m for m in active if m['role']=='face']
    mouths=[m for m in active if (m['feature'] or '').startswith('mouth')]
    structural={m['role'] for m in active}
    kind='humanoid' if faces and structural&{'torso','bodice','leg','arm'} else 'face' if faces else 'mouth' if mouths and len(mouths)==len(active) else 'local'
    center=float(np.median(np.concatenate([m['cloud'] for m in faces or active])[:,0]))
    layer_lookup={m['layer_id']:m for m in materials}
    # Clipped decorations share their receiver's physical support and motion.
    for m in active:
        base=layer_lookup.get(m['layer']['clipping_base_id'])
        if base is not None:
            m['role']=base['role'];m['feature']=m['feature'] or base['feature'];m['receiver']=base['part']
    known=[m for m in active if m['role'] is not None]
    unresolved=[]
    for m in active:
        if m['role'] is None:
            if kind=='local':m['role']='local'
            elif known:
                # Unlabelled ornaments follow the closest observed support;
                # persist all candidates so ambiguity remains reviewable.
                from scipy.spatial import cKDTree
                q=m['cloud'];root=q[q[:,1]<=np.quantile(q[:,1],.05)]
                ranked=[]
                for support in known:
                    dist=float(np.median(cKDTree(support['cloud']).query(root)[0]))
                    ranked.append((dist,tuple(support['layer']['index_path']),support))
                ranked.sort(key=lambda v:v[:2]);support=ranked[0][2]
                m['role']=support['role'];m['support_part']=support['part']
                m['support_candidates']=[{'layer_id':x[2]['layer_id'],'distance_pixels':x[0]} for x in ranked[:4]]
                m['semantic_source']='alpha_proximal_support_candidate'
            else:unresolved.append(m['layer_id'])
        m['side']='r' if np.median(m['cloud'][:,0])<center else 'l'
        if m['role'] in ('arm','hand','leg','foot','sleeve'):
            left=float(np.mean(m['cloud'][:,0]<center))
            if .15<left<.85:
                m['side']='both'
        m['semantic_source']=m.get('semantic_source','PSD_name_and_ancestry_candidate; side_from_alpha')
    if unresolved:
        write_json(run/'semantic-diagnostics.json',{'unresolved':unresolved,'kind':kind})
        raise ValueError('No structural candidates for PSD layers: '+', '.join(unresolved))
    if prepare_groups is not None: prepare_groups(materials)
    # Partial mechanisms do not instantiate a humanoid body.
    if kind!='humanoid':
        assembly=None
    else:
        annotations=[]
        for m in active:
            annotations.append({'part':m['part'],'role':m['role'],'side_tag':m['side'],
                                'provenance':'PSD_computed_candidate','reason':m['semantic_source']})
        sem={'schema_version':'rig-semantic-evidence/1','observation_sha256':json_digest(observation),'materials':annotations,
             'static_parts':[{'part':uid,'provenance':'PSD_computed_candidate',**record} for uid,record in static.items()]}
        assembly=assemble_model(observation,spec,sem)
        for row in assembly['materials']:
            m=next(m for m in active if m['part']==row['part'])
            row['source_layer_id']=m['layer_id'];row['feature']=m['feature']
            row['semantic_source']=m['semantic_source']
            row['spatial_sides']=['r','l'] if m['side']=='both' else [m['side']]
        assembly['content_sha256']=json_digest({k:v for k,v in assembly.items() if k!='content_sha256'})
        write_json(run/'semantic-selection.json',sem)
    report={'schema_version':'rig-PSD-semantics/1','kind':kind,'source_sha256':manifest['source']['sha256'],
            'observation_sha256':json_digest(observation),'generator_sha256':digest(__file__),
            'materials':[{k:m[k] for k in ('part','layer_id','name','role','feature','side','semantic_source','receiver','support_part','support_candidates') if k in m} for m in active],
            'review_required':True,'unresolved':unresolved,'static_materials':[{'part':uid,**record} for uid,record in static.items()],
            'numeric_policy':'all geometry measured from PSD alpha; no external coordinates'}
    write_json(run/'semantics.json',report)
    return materials,assembly,report
