"""Audit all real PSD material domains without opening or mutating a model."""
import argparse
from collections import defaultdict
from pathlib import Path
import numpy as np
from riglib.data import read_json,write_json,json_digest
from riglib.anatomy import solve_scaffold
from riglib.reference_fields import make_frames
from riglib.reference_compile import component_role
from riglib.semantic_registration import facial_landmarks,observed_landmarks,install_charts
from riglib.resampling import choose_grid
from riglib.part_mesh import METHOD
from riglib.carrier import make_carrier,to_local,local_frames,bounds_corners


def audit(run,evidence_path,out):
    run=Path(run);skill=Path(__file__).resolve().parents[1]
    observation=read_json(run/'observation.json');assembly=read_json(run/'assembly.json')
    evidence=read_json(evidence_path);prior=read_json(skill/'structures/humanoid-prior.json')
    if not evidence.get('part_mesh_generation',{}).get('saved_readback_verified'):
        raise ValueError('Geometry preflight requires saved NJC AutoMesh readback')
    if any(m.get('method')!=METHOD for m in evidence['part_meshes'].values()):
        raise ValueError('Non-AutoMesh Part geometry is not an accepted preflight input')
    template=read_json(skill/'structures/reference-humanoid.registered.json')
    signature=json_digest(observation)
    if any(d['observation_sha256']!=signature for d in (assembly,evidence)):
        raise ValueError('PSD observation provenance mismatch')
    signed=dict(template);digest=signed.pop('content_sha256')
    if json_digest(signed)!=digest:raise ValueError('Shared template hash mismatch')
    scaffold=solve_scaffold(evidence,prior);bones={b['id']:b for b in scaffold['bones']}
    nodes={n['uuid']:n for n in observation['nodes']}
    boxes=np.array([nodes[uid]['bounds']['nominal_world_xy'] for uid in evidence['face_parts']['face']])
    face_bounds=np.r_[boxes[:,:2].min(0),boxes[:,2:].max(0)]
    frames=make_frames(bones,face_bounds)
    materials=[(n['name'],np.asarray(n['bounds']['nominal_world_xy']).reshape(2,2))
               for n in observation['nodes'] if n['type']=='Part']
    landmarks=observed_landmarks(bones,facial_landmarks(materials))
    install_charts(frames,landmarks,template['semantic_charts'])
    torso=float(np.linalg.norm(np.array(bones['Neck']['head'])-bones['Pelvis']['head']))
    pad=scaffold['body_height']*prior['bounds_padding_body_height']
    groups=defaultdict(list);owners={}
    for material in assembly['materials']:
        role=evidence.get('material_overrides',{}).get(str(material['part']),material)
        groups[role['chart']].append(nodes[material['part']]);owners[role['chart']]=role['owner']
    report={'template_sha256':digest,'observation_sha256':signature,'evidence_sha256':json_digest(evidence),
            'scope':'Grid construction inputs only; not NJC pose or visual acceptance',
            'domains':[],'passed':False}
    for chart,parts in sorted(groups.items(),key=lambda row:(owners[row[0]]!='head',row[0])):
        name=component_role({'id':chart,'owner':owners[chart]},evidence);c=template['components'][name]
        boxes=np.array([n['bounds']['nominal_world_xy'] for n in parts])
        carrier=make_carrier(owners[chart],frames[c['frame']])
        field_frames=local_frames(frames,carrier)
        support=np.concatenate([to_local(bounds_corners(b),carrier) for b in boxes])
        lower=support.min(0)-pad;upper=support.max(0)+pad
        unit=face_bounds[2]-face_bounds[0] if c['depth']['units']=='face width' else torso
        counts=[max(r[k] for r in c['source_resolution']) for k in (0,1)]
        try:
            xs,ys,xy,z,fields,checks=choose_grid(template,name,field_frames,lower,upper,unit,counts,
                to_local([landmarks[c['frame']][label] for label in c['vertex_landmarks']],carrier).tolist())
            row={'domain':chart,'component':name,'passed':True,'sampling':checks,
                 'axis_x':xs.tolist(),'axis_y':ys.tolist()}
        except ValueError as error:
            row={'domain':chart,'component':name,'passed':False,'error':str(error)}
        report['domains'].append(row);write_json(out,report)
        print(chart, 'PASS' if row['passed'] else 'FAIL',flush=True)
    report['passed']=all(row['passed'] for row in report['domains'])
    write_json(out,report)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--evidence',required=True);p.add_argument('--out',required=True)
    a=p.parse_args();r=audit(a.run,a.evidence,a.out)
    print(sum(row['passed'] for row in r['domains']),'/',len(r['domains']),'domains passed')
    raise SystemExit(0 if r['passed'] else 1)
