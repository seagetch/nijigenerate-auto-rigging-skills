"""Audit semantic correspondence and mesh reconstruction on real NJC captures."""
import argparse
from pathlib import Path
import numpy as np
from compile_registered_reference import source
from riglib.data import read_json,write_json,json_digest
from riglib.semantic_registration import install_charts
from riglib.reference_fields import to_frame,from_frame,sample


def validate(template_path,program_path,out):
    template=read_json(template_path);program=read_json(program_path)
    if program['reference_template']['sha256']!=template['content_sha256']:
        base={k:v for k,v in template.items() if k not in ('content_sha256','facial_controls')}
        if json_digest(base)!=program['reference_template']['sha256']:
            raise ValueError('Reconstruction audit template differs from generated program')
    spec=read_json(Path(__file__).resolve().parents[1]/'references/designated-reference-set.json')
    result={'template_sha256':template['content_sha256'],'program_sha256':program['content_sha256'],
            'references':[],'target_regions':{},'surfaces':[],
            'scope':'real reference captures and one real PSD; not a multi-PSD generalization acceptance'}
    for row in spec['references']:
        s=source(row['capture_directory']);install_charts(s['frames'],s['landmarks'],template['semantic_charts'])
        errors={}
        for region,f in s['frames'].items():
            chart=template['semantic_charts'][region]
            expected=np.asarray(chart['canonical'])[:len(chart['labels'])]
            observed=np.asarray([s['landmarks'][region][k] for k in chart['labels']])
            reconstructed=from_frame(expected,f)
            errors[region]={'landmarks':chart['labels'],'maximum_position_error_model':float(np.max(abs(reconstructed-observed))),
                            'maximum_roundtrip_error':float(np.max(abs(to_frame(reconstructed,f)-expected)))}
            if errors[region]['maximum_position_error_model']>1e-6:raise ValueError('Semantic landmark mismatch')
        result['references'].append({'label':row['label'],'regions':errors})
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
    d=next(d for d in program['domains'] if d['id']=='head/face')
    root=from_frame(q,f);host=next(b['pose_origin_z'] for b in program['scaffold']['bones'] if b['id']=='Head')
    actual=(sample(d['axis_x'],d['axis_y'],d['depth_model_units'],root)[0,0]-host)/f['matrix'][0][0]
    result['nose_depth']={'canonical_landmark':q[0].tolist(),'expected_common_face_width_units':float(expected),
        'sampled_mesh_face_width_units':float(actual),'absolute_reconstruction_error_face_width_units':float(abs(actual-expected))}
    if abs(actual-expected)>.005:raise ValueError('Nose depth lost during remeshing')
    result['passed']=True;result['content_sha256']=json_digest(result);write_json(out,result)
    print('Verified semantic landmarks in all regions and resolution reconstruction on',len(result['surfaces']),'surfaces',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('template','program','out'):p.add_argument('--'+name,required=True)
    a=p.parse_args();validate(a.template,a.program,a.out)
