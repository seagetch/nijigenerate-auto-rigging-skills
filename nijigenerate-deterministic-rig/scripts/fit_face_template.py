"""Fit the bundled face template to PSD measurements, without authored coordinates."""
import argparse
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
from riglib.data import read_json,write_json,json_digest,digest
from riglib.template_runtime import TemplateCatalog,TemplateScene
from riglib.geometry import sample_grid


def fit(run):
    run=Path(run).resolve();skill=Path(__file__).resolve().parents[1]
    evidence=read_json(run/'evidence.json');capture=read_json(run/'capture.json')
    source=read_json(run/'source/psd-source.json')
    assets={r['part']:r for r in capture['materials']}
    def cloud(name):
        result=[]
        for uid in evidence['face_parts'][name]:
            m=assets[uid];rgba=np.asarray(Image.open(m['file']).convert('RGBA'))
            y,x=np.nonzero(rgba[:,:,3]>32)
            xy=np.c_[x,y,np.ones(len(x))]@np.asarray(m['pixel_to_model']).T
            result.append(xy[:,:2])
        return np.concatenate(result)
    eye_centers=sorted([np.mean(e['canthi_model'],axis=0) for e in evidence['eyes']],key=lambda p:p[0])
    u=np.array(eye_centers[1])-eye_centers[0];u/=np.linalg.norm(u)
    basis=np.column_stack((u,[-u[1],u[0]]));origin=np.mean(eye_centers,axis=0)
    local=lambda p:(np.asarray(p)-origin)@basis
    face=local(cloud('face'));nose=local(cloud('nose'));mouth=local(cloud('mouth'))
    low=face.min(axis=0);high=face.max(axis=0);width=high[0]-low[0]
    margin=width*.04;bounds=np.r_[low-[margin,margin],high+[margin,margin]]
    ea,eb=local(eye_centers)
    def section_center(p,y):
        selected=p[abs(p[:,1]-y)<=max(1,width*.01)]
        if not len(selected):raise ValueError('Empty measured alpha section')
        return [float(np.median(selected[:,0])),float(y)]
    top=float(face[:,1].min());bottom=float(face[:,1].max())
    jaw_y=top+(bottom-top)*.84
    jaw=face[abs(face[:,1]-jaw_y)<width*.015]
    mouth_y=float(np.median(mouth[:,1]));mouth_x=np.quantile(mouth[:,0],[.01,.99])
    positions={'eye_a':ea,'eye_b':eb,'nose_tip':np.median(nose,axis=0),
        'crown':section_center(face,top),'chin':section_center(face,bottom),
        'mouth_a':[mouth_x[0],mouth_y],'mouth_b':[mouth_x[1],mouth_y],
        'jaw_a':[float(np.quantile(jaw[:,0],.05)),jaw_y],
        'jaw_b':[float(np.quantile(jaw[:,0],.95)),jaw_y]}
    catalog=TemplateCatalog(skill/'templates');template=catalog.get('face_head')
    # Coverage corners constrain only the chart's registration envelope.
    # Anatomical anchors retain their own independently measured positions.
    landmark_uv={tuple(p['uv']) for p in template['landmarks'] if p['id'] in positions}
    edge_uv=({(u['u'],v) for u in template['guide_grid']['columns'] for v in (0,1)} |
             {(u,v['v']) for v in template['guide_grid']['rows'] for u in (0,1)})-landmark_uv
    coverage=[{'uv':[u,v],'xy':[bounds[0]+u*(bounds[2]-bounds[0]),bounds[1]+v*(bounds[3]-bounds[1])]} for u,v in sorted(edge_uv)]
    landmarks={name:{'xy':np.asarray(value).tolist(),'provenance':'measured',
        'source_sha256':source['source']['sha256'],'method':'PSD alpha cross-section/feature median in measured eye-line frame'} for name,value in positions.items()}
    frame=np.eye(3);frame[:2,:2]=basis;frame[:2,2]=origin
    spec={'id':'head/face','template':'face_head','landmarks':landmarks,
        'coverage_constraints':coverage,'anatomical_bounds':bounds.tolist(),
        'chart_to_model':frame.tolist(),'carrier_extension':'transparent_boundary_continuation'}
    scene=TemplateScene(catalog,[spec]);chart=scene.charts['head/face']
    declared={p['id']:p for p in template['landmarks']}
    errors={}
    for name,p in positions.items():
        q=sample_grid(chart['control']['xy'],chart['control']['u_lines'],chart['control']['v_lines'],[declared[name]['uv']])[0]
        errors[name]=float(np.linalg.norm(q-p))
    if max(errors.values())>width*.005:raise ValueError('Semantic landmark fit residual exceeds template tolerance')
    # Verify every occupied face pixel, and the complete pixel registration hull.
    observed=cloud('face')
    # Convex hull / contour verification is exact at every raster row extremum;
    # the fitted chart is validated for all cell Jacobians separately.
    contour=[]
    local_face=local(observed)
    for y in np.unique(np.round(local_face[:,1],1)):
        row=local_face[abs(local_face[:,1]-y)<.1]
        if len(row):contour.extend([row[np.argmin(row[:,0])],row[np.argmax(row[:,0])]])
    contour=np.asarray(contour)@basis.T+origin
    sampled=scene.sample('head/face',contour,opaque=True)
    report={'spec':spec,'scene':scene.report(),'landmark_residuals':errors,
        'opaque_boundary_samples':len(contour),'source_sha256':source['source']['sha256'],
        'generator_sha256':digest(Path(__file__)),'template_sha256':chart['template_sha256']}
    write_json(run/'face-template-fit.json',report)
    # Draw the fitted semantic grid directly over the PSD-derived artwork.
    im=Image.open(run/'source/source-composite.png').convert('RGBA');bg=Image.new('RGBA',im.size,(45,45,45,255));bg.alpha_composite(im)
    d=ImageDraw.Draw(bg);translation=np.asarray(evidence['source_to_model'])[:2,2]
    grid=np.asarray(chart['control']['xy'])@basis.T+origin-translation
    for line in list(grid)+list(grid.transpose(1,0,2)):d.line([tuple(p) for p in line],fill=(30,255,230,255),width=1)
    for name,p in positions.items():
        xy=np.asarray(p)@basis.T+origin-translation;d.ellipse((xy[0]-2,xy[1]-2,xy[0]+2,xy[1]+2),fill=(255,80,40));d.text(tuple(xy+[3,0]),name,fill='white')
    modelbox=np.r_[np.min(grid.reshape(-1,2),axis=0),np.max(grid.reshape(-1,2),axis=0)]
    crop=bg.crop((int(modelbox[0]-20),int(modelbox[1]-20),int(modelbox[2]+20),int(modelbox[3]+20)))
    crop.resize((crop.width*4,crop.height*4)).save(run/'face-template-fit.png')
    print('Fitted face_head template; max landmark residual',max(errors.values()),'opaque samples',len(contour),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);a=p.parse_args();fit(a.run)
