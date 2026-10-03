"""Compile a measured, error-bounded transfer from the real fitted face chart."""
import argparse
from pathlib import Path
import numpy as np
from PIL import Image
from riglib.data import read_json,write_json,json_digest,digest
from riglib.template_runtime import TemplateCatalog,TemplateScene
from riglib.geometry import evaluate_depth,apply_local_corrections,sample_grid
from riglib.face_transfer import adaptive_axes,preserve_orientation,interpolate_grid,minimum_ratio,adaptive_mesh


def compile_transfer(run,seed=None):
    run=Path(run).resolve();skill=Path(__file__).resolve().parents[1]
    previous=seed if seed is not None else read_json(run/'face-template-program.json');state=read_json(run/'native-state.json')
    program=read_json(run/'program.json');fit=read_json(run/'face-template-fit.json')
    if seed is None and previous['content_sha256']!=state['face_template_program_sha256']:raise ValueError('Face source program identity mismatch')
    scene=TemplateScene(TemplateCatalog(skill/'templates'),[fit['spec']]);chart=scene.charts['head/face']
    frame=np.array(chart['chart_to_model']);width=chart['depth_scale'];params=chart['parameters']
    capture=read_json(run/'capture.json');assembly=read_json(run/'assembly.json')
    face_ids={m['part'] for m in assembly['materials'] if m.get('role',{}).get('rule')=='face'}
    material=next(m for m in capture['materials'] if m['part'] in face_ids)
    rgba=np.array(Image.open(material['file']).convert('RGBA'));y,x=np.nonzero(rgba[:,:,3]>32)
    pixels=(np.c_[x,y,np.ones(len(x))]@np.array(material['pixel_to_model']).T)[:,:2]
    landmarks=np.array([l['xy'] for l in fit['spec']['landmarks'].values()])@frame[:2,:2].T+frame[:2,2]
    query=np.r_[pixels,landmarks]
    cached_path=run/'face-transfer-sampling.json'
    cached=read_json(cached_path) if cached_path.exists() else None
    if cached is not None and cached['fit_sha256']==json_digest(fit) and np.array_equal(cached['query'],query):
        truth=np.array(cached['truth'])
    else:
        sample=scene.sample('head/face',query,opaque=True)
        truth=evaluate_depth(sample['uv'],chart['template']['geometry']['operators'],params)*width
    print('Measured opaque template depth at',len(query),'positions',flush=True)
    cache={}
    def sample_depth(points):
        missing=sorted({tuple(p) for p in points}-cache.keys())
        if missing:
            s=scene.sample('head/face',missing)
            z=evaluate_depth(s['uv'],chart['template']['geometry']['operators'],params)*width
            cache.update(zip(missing,z))
        return np.array([cache[tuple(p)] for p in points])
    # Keep actual feature coordinates as axes; intermediate refinement follows
    # measured interpolation residuals rather than a guessed global density.
    def merge(base,anchors):
        values=list(anchors)
        for v in base:
            if not values or min(abs(np.array(values)-v))>width*.002:values.append(v)
        return np.unique(np.round(sorted(values),4))
    old=previous['grid'];xs=merge(old['axis_x'],landmarks[:,0]);ys=merge(old['axis_y'],landmarks[:,1])
    sampling_key=json_digest({'version':1,'initial_x':xs.tolist(),'initial_y':ys.tolist(),'fit_sha256':json_digest(fit)})
    if cached is not None and cached.get('sampling_key')==sampling_key:
        xs=np.array(cached['xs']);ys=np.array(cached['ys']);z=np.array(cached['depth']);trials=cached['trials']
    else:xs,ys,z,trials=adaptive_axes(xs,ys,sample_depth,query,truth,width)
    print('Depth transfer',trials[-1],flush=True)
    write_json(run/'face-transfer-sampling.json',{'xs':xs.tolist(),'ys':ys.tolist(),'depth':z.tolist(),'trials':trials,'query':query.tolist(),'truth':truth.tolist(),'fit_sha256':json_digest(fit),'sampling_key':sampling_key})
    # Separate local facial relief from the shared head's Z placement. The
    # eye/mouth plane is the local reference, anchored at the front of the
    # scaffold head volume. This is translation, never a relief multiplier.
    reference_names=['eye_a','eye_b','mouth_a','mouth_b']
    reference_xy=np.array([fit['spec']['landmarks'][name]['xy'] for name in reference_names])@frame[:2,:2].T+frame[:2,2]
    reference_depth=float(np.mean(scene.sample('head/face',reference_xy)['depth']))
    prior=read_json(skill/'structures/humanoid-prior.json')
    head_front=float(program['scaffold']['volumes']['head']['radii'][0]*prior['depth_ratios']['head'])
    offset=head_front-reference_depth
    z=z+offset;truth=truth+offset
    depth_frame={'reference_landmarks':reference_names,'template_reference_plane':reference_depth,
                 'shared_head_front_plane':head_front,'z_offset_model':offset,
                 'composition':'absolute Z = template relief - reference plane + shared head front plane',
                 'relief_scale':1.0,'prior_sha256':json_digest(prior)}
    points=np.array([[x,y] for y in ys for x in xs]);s=scene.sample('head/face',points);uv=s['uv'];local=(points-frame[:2,2])@frame[:2,:2]
    protected=np.zeros(len(uv),bool)
    for patch in chart['template']['guide_grid']['patches']:
        region=patch['region'];protected|=((uv[:,0]>=region['u'][0])&(uv[:,0]<=region['u'][1])&(uv[:,1]>=region['v'][0])&(uv[:,1]<=region['v'][1]))
    specs={s['name']:s for s in program['parameters']};operations=[];checks=[]
    for cal in previous['calibration']:
        m=np.array(cal['matrix']);q=np.c_[points,z,np.ones(len(points))]@m
        if cal['name']=='Face::Yaw-Pitch':
            angles={b['axis']:b['degrees'] for b in specs[cal['name']]['bindings']}
            pose={'yaw':cal['key'][0]*angles['y']*previous['axis_calibration']['yaw_sign'],
                  'pitch':cal['key'][1]*angles['x']*previous['axis_calibration']['pitch_sign']}
            q+=(apply_local_corrections(local,uv,pose,chart['template']['correction_rules'],params,scale=width)-local)@frame[:2,:2].T
        try:q,correction=preserve_orientation(q,xs,ys,uv,m[2],width,protected)
        except ValueError as error:raise ValueError(str((cal['name'],cal['key']))+': '+str(error)) from error
        off=np.round(q-points,3)
        if all(k==0 for k in cal['key']):off[:]=0
        ratio=minimum_ratio(points+off,xs,ys)
        if ratio<.05:raise ValueError('Quantized projection folds')
        checks.append({'parameter':cal['name'],'key':cal['key'],'minimum_area_ratio':ratio,'contour_projection':correction})
        operations.append({'parameter':cal['parameter'],'target':old['target'],'key':cal['key'],'values':off.ravel().tolist()})
    pose_values=[np.array(op['values']).reshape(-1,2) for op in operations]
    fields=np.column_stack([z,*pose_values])
    def field(q):return interpolate_grid(xs,ys,fields,q)
    c=chart['control'];us=np.array(c['u_lines']);vs=np.array(c['v_lines'])
    us=np.sort(np.r_[us,(us[:-1]+us[1:])/2]);vs=np.sort(np.r_[vs,(vs[:-1]+vs[1:])/2])
    seed_uv=np.array([[u,v] for v in vs for u in us])
    seed_xy=sample_grid(c['xy'],c['u_lines'],c['v_lines'],seed_uv)@frame[:2,:2].T+frame[:2,2]
    obs=read_json(run/'observation.json');nodes={x['uuid']:x for x in obs['nodes']};meshes=[]
    decorations={m['part'] for m in assembly['materials'] if m.get('role',{}).get('usage')=='decoration'}
    for part in next(d for d in program['domains'] if d['id']=='head/face')['parts']:
        node=nodes[part['uuid']]
        if part['uuid'] not in face_ids and part['uuid'] not in decorations:continue
        transform=node['transform']
        if not np.allclose(transform['rot'],0) or not np.allclose(transform['scale'],1):raise ValueError('Unresolved mesh registration transform')
        translation=np.array(transform['trans'][:2]);bounds=np.array(node['mesh']['local_bounds_xy'])+np.tile(translation,2)
        vertices,triangles,mesh_trials=adaptive_mesh(bounds,np.r_[seed_xy,landmarks],query,field,width*.0025,axes=(xs,ys))
        meshes.append({'target':part['uuid'],'vertices':np.round(vertices-translation,4).ravel().tolist(),
                       'indices':triangles.ravel().tolist(),'transfer_trials':mesh_trials})
        print('Adaptive mesh',node['name'],mesh_trials[-1],flush=True)
    report={'generator_sha256':digest(Path(__file__)),'transfer_kernel_sha256':digest(skill/'scripts/riglib/face_transfer.py'),
            'source_face_program_sha256':previous['content_sha256'],'source_program_sha256':program['content_sha256'],
            'fit_sha256':json_digest(fit),'template_sha256':chart['template_sha256'],'template_parameters':params,'depth_frame':depth_frame,
            'calibration':previous['calibration'],'axis_calibration':previous['axis_calibration'],
            'grid':{'target':old['target'],'axis_x':xs.tolist(),'axis_y':ys.tolist(),'depths':np.round(z/program['native_depth_scale'],6).tolist()},
            'operations':operations,'checks':checks,'sampling_trials':trials,
            'depth_transfer':{'opaque_samples':len(pixels),'landmark_samples':len(landmarks),'tolerance_model':width*.005,
                              'max_error_model':float(max(abs(interpolate_grid(xs,ys,z,query)[:,0]-truth)))},
            'meshes':meshes,'depth_constraint_policy':'template defaults preserved; no depth reduction; explicit outer-contour pose correction'}
    report['content_sha256']=json_digest(report);write_json(run/'face-transfer-program.json',report)
    print('Compiled',len(xs),len(ys),'grid; min Jacobian',min(c['minimum_area_ratio'] for c in checks),
          'maximum contour correction',max(c['contour_projection']['maximum_correction'] for c in checks),flush=True)
    return report,state


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);args=p.parse_args();compile_transfer(args.run)
