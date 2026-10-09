"""Derive support constraints from PSD observations and anatomical scaffold.

Names supply semantic candidates only. Numeric anchors, extents and protection
come from current PSD alpha and shared anatomical evidence. No source UUIDs or
character-specific coordinates are embedded in this implementation.
"""
from pathlib import Path
import re
import numpy as np
from PIL import Image
from scipy.ndimage import binary_erosion
from scipy.spatial import cKDTree
from .data import read_json, json_digest, digest
from .physics_fields import frame, field_weight, segment_distance
from .assembly import normalized_name, _classification


def psd_materials(run, evidence):
    run = Path(run)
    source_root=run/'source' if (run/'source/psd-source.json').is_file() else run
    manifest = read_json(source_root/'psd-source.json')
    registration = read_json(run/'registration.json')
    if manifest['source']['sha256'] != evidence['psd_sha256'] or registration['psd_sha256'] != evidence['psd_sha256']:
        raise ValueError('Physics PSD provenance mismatch')
    layers = {r['id']:r for r in manifest['layers']}; result = {}
    affine = np.asarray(evidence['source_to_model'], float)
    for row in registration['mapping']:
        layer = layers[row['layer_id']]; path = source_root/layer['asset']['path']
        if digest(path) != layer['asset']['sha256']:raise ValueError('PSD alpha asset changed')
        rgba = np.asarray(Image.open(path).convert('RGBA'))
        mask = rgba[:, :, 3]>evidence['policy']['alpha_threshold']
        y, x = np.nonzero(mask)
        pixels = np.c_[x+layer['bounds'][0]+.5, y+layer['bounds'][1]+.5]
        points = pixels@affine[:2, :2].T+affine[:2, 2]
        edge_y, edge_x = np.nonzero(mask & ~binary_erosion(mask))
        boundary = np.c_[edge_x+layer['bounds'][0]+.5, edge_y+layer['bounds'][1]+.5]@affine[:2, :2].T+affine[:2, 2]
        result[row['part']] = {'points':points, 'boundary':boundary, 'rgba':rgba, 'mask':mask,
                             'layer':layer, 'asset_sha256':layer['asset']['sha256']}
    return result


def compile_structure(run, policy):
    run = Path(run); evidence = read_json(run/'evidence.json'); assembly = read_json(run/'assembly.json')
    observation = read_json(run/'observation.json'); program = read_json(run/'program.json')
    if assembly['observation_sha256'] != json_digest(observation) or evidence['observation_sha256'] != json_digest(observation):
        raise ValueError('Physics observation provenance mismatch')
    if program['evidence_sha256'] != json_digest(evidence):raise ValueError('Physics anatomical evidence changed')
    assets = psd_materials(run, evidence)
    affine = np.asarray(evidence['source_to_model']); joints = {
        k: np.asarray(v['xy'])@affine[:2, :2].T+affine[:2, 2] for k,v in evidence['landmarks'].items()}
    current_roles=read_json(Path(__file__).resolve().parents[2]/'structures/physics-material-roles.json')
    materials = {m['part']:dict(m,role=dict(m['role'])) for m in assembly['materials']}; inventory = []; candidates = []
    receivers={m['part']:m['receiver'] for m in evidence['semantic_materials'] if m.get('receiver')}
    for uid,m in materials.items():
        current_role,_=_classification(normalized_name(m['name'].rstrip('\0')),current_roles)
        if uid in receivers or current_role and current_role['usage']=='decoration':
            m['role']['usage']='decoration'
    for uid, m in sorted(materials.items()):
        role = m['role']; usage = role['usage']; p = assets[uid]['points']; name=m['name'].casefold()
        row = {'target':uid, 'name':m['name'], 'owner':m['owner'], 'chart':m['chart'], 'decision':'exclude'}
        inventory.append(row)
        if not len(p):row['reason']='Empty alpha';continue
        mixed = usage=='anatomy' and m['owner'].startswith('arm:') and bool(re.search(r'(sleeve|cloth|frill)',name))
        current_role,_=_classification(normalized_name(m['name'].rstrip('\0')),current_roles)
        if current_role and current_role['usage'] in ('anatomy','terminal','feature') and not mixed:
            row['reason']='Human body/terminal/feature candidate protected by current anatomy rules, including stale garment classifications'
            continue
        if usage in ('anatomy','terminal','feature') and not mixed:
            row['reason']='Human body, joints, hands/fingers, feet/shoes or face: skeleton motion only'
            continue
        if usage=='decoration':row['reason']='Receiver decoration handled with its supported surface';continue
        rule=role['rule']; profile='hanging'; pattern='one_end'; limb=None; support_axis=None
        side=evidence['side_mapping'].get(role.get('side_tag')); owner=m['owner']
        if owner.startswith(('arm:','leg:')) and side not in ('L','R'):
            row['decision']='unresolved';row['reason']='Shared or unknown limb side requires separate structural support regions'
            continue
        if owner.startswith('arm:'):
            a,b,c=[joints[k+'.'+side] for k in ('shoulder','elbow','wrist')]
            radius=evidence['limb_radii'][owner]*policy['limb_protection_radius_scale']
            hand_tip=joints.get('hand_tip.'+side)
            chain=[a,b,c]+([hand_tip] if hand_tip is not None else [])
            distance=np.minimum.reduce([segment_distance(p,start,end) for start,end in zip(chain[:-1],chain[1:])])
            if np.all(distance<=radius*1.2):
                row['reason']='Human body or fitted limb surface: entire alpha lies within the measured anatomical chain protection region'
                row['structural_authority']={'joints':[q.tolist() for q in chain], 'measured_radius':radius,
                    'max_alpha_distance':float(distance.max()),'source':'Current PSD alpha and anatomical landmarks; independent of Part name'}
                continue
            limb={'joints':[a.tolist(),b.tolist(),c.tolist()], 'radius':radius, 'side':side,
                  'authority':'Measured arm alpha radius and anatomical shoulder/elbow/wrist prior'}
            if rule=='shoulder' or 'cuff' in name:
                fixed=a if rule=='shoulder' else c;profile='frill';bone='UpperArm.'+side if rule=='shoulder' else 'Hand.'+side
                if 'cuff' in name and not re.search(r'(bow|tassel|ribbon)',name):support_axis=c-b
            elif rule=='sleeve' or mixed:
                fixed=a;pattern='two_ends';profile='sleeve';bone='UpperArm.'+side
            else:row['reason']='Unresolved arm accessory material';row['decision']='unresolved';continue
        elif owner.startswith('leg:'):
            if rule=='thigh_accessory':row['reason']='Fitted thigh band';continue
            if not re.search(r'(bow|ribbon|tassel|frill)', name):row['reason']='Fitted ankle covering';continue
            fixed=joints['ankle.'+side];bone='Foot.'+side
            support_axis=joints['ankle.'+side]-joints['knee.'+side]
        elif usage=='covering':
            row['reason']='Fitted torso/neck covering; no automatic chest/body sway';continue
        elif owner=='head':
            bone='Head'
            if rule.startswith('hair'):
                fixed=joints['head_top'];profile='hair'
            elif rule=='ear':
                fixed=joints['head_top'];profile='ear'
                # Upward ears can share a Part with their lower support band.
                # The scalp/neck axis defines base-to-tip, independently of
                # the alpha centroid or nearest point to head_top.
                support_axis=joints['head_top']-joints['neck_base']
                upward=support_axis/np.linalg.norm(support_axis)
                if np.quantile((p-fixed)@upward,.95)<=0:
                    row['reason']='Human body/head side ear without a verified protruding free region; skeleton motion only'
                    continue
            elif re.search(r'(bow|ribbon|tassel|frill)', name):fixed=joints['head_top']
            else:row['reason']='Rigid fitted head covering';continue
        elif owner=='torso':
            if rule in ('skirt','skirt_back','apron'):
                fixed=joints['waist'];profile='sheet';bone='Pelvis'
            elif rule=='tail':fixed=joints['pelvis'];profile='hanging';bone='Pelvis'
            elif rule in ('chest_accessory','pelvis_accessory') and re.search(r'(bow|ribbon|tassel|chain)',name):
                fixed=joints['neck_base'] if rule=='chest_accessory' else joints['waist'];bone='Chest' if rule=='chest_accessory' else 'Pelvis'
            else:row['reason']='Rigid or unresolved torso accessory';continue
        else:row['decision']='unresolved';row['reason']='No anatomical support';continue
        if re.search(r'(chain|tassel|ribbon|bow)', name):profile='hanging';pattern='one_end'
        # Root is the proximal alpha section relative to the anatomical host,
        # not the screen-top point. This also reverses upward ear/tail roots.
        distances=np.linalg.norm(p-fixed,axis=1)
        proximal=p[distances<=np.quantile(distances,.05)]
        root=proximal.mean(axis=0)
        direction=p.mean(axis=0)-root
        if np.linalg.norm(direction)<1e-6:row['decision']='unresolved';row['reason']='No free direction';continue
        direction/=np.linalg.norm(direction); projection=(p-root)@direction
        free=p[projection>=np.quantile(projection,.95)].mean(axis=0)
        if support_axis is not None:
            # A worn band is attached on its proximal side, even when the
            # estimated wrist/ankle lies closer to the hanging distal ribbon.
            direction=support_axis/np.linalg.norm(support_axis);s=p@direction
            if profile!='ear':root=p[s<=np.quantile(s,.05)].mean(axis=0)
            free=p[s>=np.quantile(s,.95)].mean(axis=0)
        if pattern=='two_ends':
            # Attachment locations are fitted to proximal/distal cloth sections
            # along the shoulder-to-wrist frame, protecting both observed ends.
            direction=(c-a)/np.linalg.norm(c-a);s=(p-a)@direction
            root=p[s<=np.quantile(s,.05)].mean(axis=0);free=p[s>=np.quantile(s,.95)].mean(axis=0)
        spec={'id':m['chart']+'/'+str(uid), 'name':'Physics::'+m['chart']+'::'+str(uid),
              'target':uid,'parent_bone':bone,'profile':profile,'pattern':pattern,
              'fixed':root.tolist(),'free':free.tolist(),'limb':limb,'owner':owner,
              'semantic_authority':'PSD role candidate and spatial anatomy; visual verification required',
              'protected_pixels':[], 'protection_margin':1., 'asset_sha256':assets[uid]['asset_sha256']}
        if limb:
            anatomical=np.minimum(segment_distance(p,a,b),segment_distance(p,b,c))<=radius*1.2
            hand_tip=joints.get('hand_tip.'+side)
            if hand_tip is not None:
                anatomical|=segment_distance(p,c,hand_tip)<=radius*1.2
                limb['joints'].append(hand_tip.tolist())
            # Only structural evidence is used. RGB, luminance and any assumed
            # flesh colour are deliberately irrelevant to this decision.
            protected=p[anatomical] if mixed else np.empty((0,2))
            spec['protected_pixels']=protected[::max(1,len(protected)//20000)].tolist()
            spec['protection_margin']=max(1.,limb['radius']*.08)
            spec['region_authority']='Anatomical tube/joints and PSD alpha; no RGB or luminance classification'
            spec['mixed_anatomy_cloth']=mixed
            if mixed:
                row['decision']='unresolved'
                row['reason']='Combined body/cloth lacks resolved anatomical surface boundary; protect entire Part until structural region recognition is verified'
                continue
        o,t,n,length=frame(root,free)
        spec['frame']={'space':'neutral model XY from current PSD registration; Y down','O':o.tolist(),'T':t.tolist(),'N':n.tolist()}
        spec['length']=length
        w=field_weight(spec,p[::max(1,len(p)//10000)],policy)
        if np.mean(w>1e-6)<policy['minimum_free_fraction']:
            row['decision']='unresolved';row['reason']='No supported free cloth outside protected anatomy/joints';continue
        # Apparent attachment does not prove whether chain pendants are rigid.
        if 'chain' in name:
            row['decision']='unresolved';row['reason']='Chain/rigid pendant segmentation and multiple anchors not yet resolved';continue
        row.update(decision='include',reason='Anatomical support with local free region',pattern=pattern,profile=profile)
        candidates.append(spec)
    # Receiver shadows belong to one primary supported surface, never to every
    # accessory that happens to have the same chart label.
    for spec in candidates:
        spec['targets']=[spec['target']]
    for uid,other in materials.items():
        if other['role']['usage']!='decoration':continue
        receiver=receivers.get(uid);visited=set()
        while receiver in materials and materials[receiver]['role']['usage']=='decoration' and receiver not in visited:
            visited.add(receiver)
            if receiver not in receivers:break
            receiver=receivers[receiver]
        possible=[s for s in candidates if (s['target']==receiver if receiver is not None else
                  materials[s['target']]['chart']==other['chart'] and s['profile'] in ('sheet','hair','sleeve'))]
        if possible:
            spec=max(possible,key=lambda s:len(assets[s['target']]['points']))
            spec['targets'].append(uid)
            next(r for r in inventory if r['target']==uid).update(decision='carried',reason='Primary observed receiver field',carrier=spec['id'])
    # Skirt and apron share one field when both attach to the waist. Do not
    # merge arbitrary chart members or left/right rear panels by hierarchy.
    fronts=[s for s in candidates if materials[s['target']]['role']['rule'] in ('skirt','apron') and s['profile']=='sheet']
    if fronts:
        base=fronts[0];cloud=np.concatenate([assets[s['target']]['points'] for s in fronts]);y=np.quantile(cloud[:,1],.05)
        root=cloud[cloud[:,1]<=y].mean(axis=0);free=cloud[cloud[:,1]>=np.quantile(cloud[:,1],.95)].mean(axis=0)
        base.update(fixed=root.tolist(),free=free.tolist(),name='Physics::WaistCloth',id='waist-cloth')
        base['length']=frame(root,free)[3];base['targets']=sorted({u for s in fronts for u in s['targets']})
        o,t,n,_=frame(root,free);base['frame'].update(O=o.tolist(),T=t.tolist(),N=n.tolist())
        for other in fronts[1:]:candidates.remove(other)
    # Build one acyclic support graph from observed alpha proximity. A child
    # receives its host field in addition to its own relative flex. The entire
    # local anchor band is carried rigidly, so a joined Part does not detach.
    for child in candidates:
        child_material=materials[child['target']];child_name=child_material['name'].casefold()
        if not re.search(r'(bow|tassel|ribbon)',child_name):continue
        choices=[]
        for host in candidates:
            if host is child:continue
            if child['owner']!=host['owner']:continue
            host_material=materials[host['target']];host_name=host_material['name'].casefold()
            # Alpha overlap with hair does not attach a head ornament to hair.
            # Constrain proximity by the semantic support topology first.
            if child['owner']=='head':
                compatible=('tassel' in child_name and 'bow' in host_name
                            and host_material['role']['rule']=='headwear')
            else:
                compatible=(host['profile'] in ('sheet','sleeve','frill')
                            and host_material['chart']==child_material['chart'])
            if not compatible:continue
            distance=float(cKDTree(assets[host['target']]['points']).query(child['fixed'])[0])
            if distance<=max(host['length']*policy['attachment_distance_fraction'],child['length']*.15):
                choices.append((distance,host['id'],host))
        if choices:
            _,_,host=min(choices,key=lambda r:r[:2]);child['support_group']=host['id']
            child['support_anchor']=child['fixed']
            next(r for r in inventory if r['target']==child['target'])['support_group']=host['id']
    result={'schema_version':'rig-physics-structure/1','inventory':inventory,'groups':candidates,
            'psd_sha256':evidence['psd_sha256'],'program_sha256':program['content_sha256'],
            'policy_sha256':json_digest(policy),'material_roles_sha256':json_digest(current_roles),'compiler_sha256':digest(Path(__file__)),
            'limitations':['Names remain semantic candidates, not complete visual segmentation.',
                          'Mixed anatomy/cloth without resolved regions and chain/pendant topology remain unresolved.',
                          'No collision or hidden-artwork generation.']}
    result['content_sha256']=json_digest(result)
    return result,assets
