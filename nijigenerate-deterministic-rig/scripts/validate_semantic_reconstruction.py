"""Audit semantic correspondence and mesh reconstruction on real NJC captures."""
import argparse
from pathlib import Path
import numpy as np
from riglib.data import read_json,write_json,json_digest
from riglib.reference_fields import to_frame,from_frame,sample
from riglib.carrier import to_local


def validate(template_path,program_path,out):
    template=read_json(template_path);program=read_json(program_path)
    if program['reference_template']['sha256']!=template['content_sha256']:
        base={k:v for k,v in template.items() if k not in ('content_sha256','facial_controls')}
        if json_digest(base)!=program['reference_template']['sha256']:
            raise ValueError('Reconstruction audit template differs from generated program')
    result={'template_sha256':template['content_sha256'],'program_sha256':program['content_sha256'],
            'references':[],'target_regions':{},'surfaces':[],
            'scope':'signed bundled semantic template and the current PSD program; no external captures'}
    # Reference capture validation belongs to template development. A PSD run
    # consumes only the signed bundled template, never external model captures.
    for region,f in program['reference_template']['frames'].items():
        chart=f['semantic_chart'];canonical=np.asarray(chart['canonical'])[:len(chart['labels'])]
        root=from_frame(canonical,f)
        error=float(np.max(abs(to_frame(root,f)-canonical)))
        if error>1e-6:raise ValueError('Target semantic inverse mismatch')
        result['target_regions'][region]={'landmarks':chart['labels'],'maximum_roundtrip_error':error,
            'minimum_sampled_jacobian':chart['minimum_sampled_jacobian']}
    for d in program['domains']:
        audit=d['resampling']
        result['surfaces'].append({'id':d['id'],**audit})
    f=program['reference_template']['frames']['head'];chart=f['semantic_chart']
    q=np.array([chart['canonical'][chart['labels'].index('nose')]])
    c=template['components']['face'];expected=c['depth']['plane_offset']+sample(c['axis_x'],c['axis_y'],c['depth']['relief'],q)[0,0]
    d=next(d for d in program['domains'] if d.get('semantic_chart',d['id'])=='head/face')
    root=from_frame(q,f);host=next(b['pose_origin_z'] for b in program['scaffold']['bones'] if b['id']=='Head')
    actual=(sample(d['axis_x'],d['axis_y'],d['depth_model_units'],to_local(root,d['carrier_frame']))[0,0]-host)/f['matrix'][0][0]
    result['nose_depth']={'canonical_landmark':q[0].tolist(),'expected_common_face_width_units':float(expected),
        'sampled_mesh_face_width_units':float(actual),'absolute_reconstruction_error_face_width_units':float(abs(actual-expected))}
    result['nose_depth']['inspection_note']='reconstruction difference' if abs(actual-expected)>.005 else None
    result['passed']=bool(abs(actual-expected)<=.005);result['content_sha256']=json_digest(result);write_json(out,result)
    print('Verified semantic landmarks in all regions and resolution reconstruction on',len(result['surfaces']),'surfaces',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('template','program','out'):p.add_argument('--'+name,required=True)
    a=p.parse_args();validate(a.template,a.program,a.out)
