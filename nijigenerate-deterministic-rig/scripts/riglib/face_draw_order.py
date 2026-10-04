"""Place independent facial mechanisms above their PSD skin backing.

Some PSD ear assets also contain a complete painted face. Detect their alpha
coverage rather than naming a character or editing its texture. Keep that
backing behind the separate skin and facial mechanisms with static draw order.
"""
import numpy as np
from PIL import Image


def plan(evidence, capture, nodes):
    materials={m['part']:m for m in capture['materials']}
    alpha={}
    def image(uid):
        if uid not in alpha:alpha[uid]=np.asarray(Image.open(materials[uid]['file']).convert('RGBA'))[:,:,3]
        return alpha[uid]
    def cloud(uid):
        y,x=np.nonzero(image(uid)>128);stride=max(1,len(x)//10000)
        return np.c_[x[::stride],y[::stride]]+np.asarray(materials[uid]['source_bbox'][:2])+.5
    def coverage(uid,points):
        a=image(uid);p=np.floor(points-np.asarray(materials[uid]['source_bbox'][:2])).astype(int)
        valid=(p[:,0]>=0)&(p[:,1]>=0)&(p[:,0]<a.shape[1])&(p[:,1]<a.shape[0])
        hit=np.zeros(len(p),bool);hit[valid]=a[p[valid,1],p[valid,0]]>128
        return float(hit.mean()) if len(hit) else 0.
    def z(uid):
        node=nodes[uid]
        return float(node.get('draw_properties',{}).get('zsort',0.))+sum(
            float(nodes[p].get('draw_properties',{}).get('zsort',0.)) for p in node.get('ancestors',[]))
    def scope(uid):
        return tuple(p for p in nodes[uid].get('ancestors',[]) if 'Composite' in nodes[p]['type'])
    features={uid for eye in evidence.get('eyes',[]) for ids in eye['part_groups'].values() for uid in ids}
    features.update((evidence.get('mouth') or {}).get('parts',[]))
    faces=[m['part'] for m in evidence['semantic_materials'] if m['role']=='face']
    ears=[m['part'] for m in evidence['semantic_materials'] if m['role']=='ear']
    operations=[];observations=[];desired={uid:z(uid) for uid in materials}
    for face in faces:
        supported=[uid for uid in sorted(features) if coverage(face,cloud(uid))>.5 and scope(uid)==scope(face)]
        if not supported:continue
        # Smaller zSort renders later. Existing correct order stays untouched.
        target=max(desired[face],max(desired[uid] for uid in supported)+.25)
        if target!=desired[face]:
            operations.append({'target':face,'absolute_zsort':target,'reason':'skin behind independent facial mechanisms','supported_parts':supported})
            desired[face]=target
        points=cloud(face)
        for ear in ears:
            overlap=coverage(ear,points)
            if overlap<=.5 or scope(ear)!=scope(face):continue
            observations.append({'ear':ear,'face':face,'face_alpha_coverage':overlap})
            target=max(desired[ear],desired[face]+.25)
            if target!=desired[ear]:
                operations.append({'target':ear,'absolute_zsort':target,'reason':'ear artwork covering skin stays behind the separate skin','face':face,'face_alpha_coverage':overlap})
                desired[ear]=target
    for op in operations:
        uid=op['target'];op['relative_zsort']=op['absolute_zsort']-(z(uid)-float(nodes[uid]['draw_properties']['zsort']))
    return {'operations':operations,'overlapping_ear_backings':observations,'source':'PSD alpha coverage, semantic role and existing composite scope; static Part draw order only'}
