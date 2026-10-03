"""Reference-authored facial controls, kept separate from head angle projection."""
import re
import numpy as np
from .assembly import normalized_name
from .reference_materials import mesh_weights
from .data import json_digest,digest
from pathlib import Path


def control_role(name):
    name=normalized_name(name)
    for role,pattern in [('sclera',r'^(sclera|eye_white)'),('upper',r'^lash_upper'),
                         ('lower',r'^lash_lower'),('corner',r'^eye_corner'),('fold',r'^lid_fold'),
                         ('tip',r'^lash_tip'),('iris',r'^iris'),('brow',r'^(brow|eyebrow)'),
                         ('mouth',r'^mouth_base$'),('mouth_outline',r'^mouth_outline$'),
                         ('mouth_tongue',r'^mouth_tongue$'),('mouth_upper_teeth',r'^mouth_teeth_upper$'),
                         ('mouth_lower_teeth',r'^mouth_teeth_lower$')]:
        if re.search(pattern,name):return role
    return None


def compile_controls(sources):
    names=['Eye::'+s+'::'+kind for s in ('L','R') for kind in ('Blink','X-Y')]
    names+=['Eyebrow::L','Eyebrow::R','Mouth::Open']
    result={}
    for name in names:
        groups={};axes=None;observed_sources=[]
        for src in sources:
            rows=[b for b in src['snapshot']['bindings'] if b['parameter']['name']==name]
            if not rows:raise ValueError('Designated reference lacks facial control '+name)
            observed_sources.append(src['measured']['identity']['public_snapshot_sha256'])
            for b in rows:
                if b['name']!='deform' or b['target']['typeId']!='Part':raise ValueError('Unsupported facial binding '+name)
                if b['interpolateMode']!='Linear':raise ValueError('Facial interpolation requires an explicit reference adapter')
                if axes is None:axes=b['axisValues']
                if axes!=b['axisValues']:raise ValueError('Reference facial axes disagree: '+name)
                role=control_role(b['target']['name'])
                if role is None:raise ValueError('Unclassified reference facial Part '+b['target']['name'])
                uid=b['target']['uuid'];node=src['nodes'][uid];m=src['evaluator'].world(uid)
                vertices=np.asarray(node['mesh']['verts']).reshape(-1,2)@m[:2,:2].T+m[:2,3]
                extent=np.ptp(vertices,axis=0)
                if min(extent)<=1e-6:raise ValueError('Degenerate reference facial Part')
                uv=(vertices-vertices.min(0))/extent
                if name=='Mouth::Open':
                    bases=[d for d in src['nodes'].values() if d['type']=='Part' and control_role(d['name'])=='mouth']
                    if len(bases)!=1:raise ValueError('Ambiguous reference mouth base')
                    base=bases[0];bm=src['evaluator'].world(base['uuid'])
                    bv=np.asarray(base['mesh']['verts']).reshape(-1,2)@bm[:2,:2].T+bm[:2,3]
                    width=float(np.ptp(bv[:,0]))
                else:
                    side=name.split('::')[1].lower();landmarks=src['landmarks']['head']
                    width=float(np.linalg.norm(np.asarray(landmarks['eye_'+side+'_outer'])-landmarks['eye_'+side+'_inner']))
                values=np.asarray(b['data']['values']).reshape(len(axes[0]),len(axes[1]),-1,2)@m[:2,:2].T/width
                groups.setdefault(role,[]).append((uv,node['mesh']['indices'],values))
        fields={}
        for role,rows in groups.items():
            count=max(3,int(np.ceil(np.sqrt(max(len(v) for v,_,_ in rows)))))
            axis=np.linspace(0,1,count);query=np.array([[x,y] for y in axis for x in axis]);fields_all=[]
            for vertices,indices,values in rows:
                ids,weights,_=mesh_weights(vertices,indices,query)
                fields_all.append(np.sum(values[:,:,ids,:]*weights[None,None,:,:,None],axis=3))
            fields[role]={'axis_x':axis.tolist(),'axis_y':axis.tolist(),
                          'values':np.mean(fields_all,axis=0).tolist(),'evidence_count':len(rows)}
        result[name]={'axes':axes,'vec2':True,'fields':fields,'references':observed_sources,
                      'units':'feature width','query_space':'neutral Part envelope coordinates',
                      'source':'all designated reference Part bindings; no invented expression curves'}
    return {'parameters':result,'compiler_sha256':digest(Path(__file__)),
            'source_scope':'all designated references; one common facial control definition',
            'content_sha256':json_digest(result)}
