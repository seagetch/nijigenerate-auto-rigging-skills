"""Compare saved source and generated neutral renders through NJC only."""
import argparse,time
from pathlib import Path
import numpy as np
from PIL import Image
from riglib.data import read_json,write_json,digest
from riglib.live import Live
from riglib.model import read_model_metadata
from build_native import require_single_rig
from apply_face_template import verify_face_program


def validate(run,njc):
    run=Path(run).resolve();out=run;out.mkdir(exist_ok=True)
    state=read_json(run/'native-state.json');program=read_json(run/'program.json')
    n=Live(njc,out/'neutral-journal')
    def capture(name):
        n.call('ToolCommand_ModelEditMode');n.call('ViewportCommand_ResetParameters')
        from riglib.render_camera import capture as capture_camera
        p=out/name;capture_camera(n,run,p);return p
    source=read_json(run/'registered-neutral.json');a_path=Path(source['file'])
    if not source.get('saved_active_readback_verified',source.get('saved_reopen_equal')) or digest(a_path)!=source['sha256'] or source['public_source_sha256']!=program['psd_import_source']['metadata_sha256']:
        raise ValueError('Registered source screenshot identity mismatch')
    require_single_rig(n,state['rig_root'],state['bones'].values())
    b_path=capture('rig-neutral-saved.png')
    if 'reference_template' not in program and not state.get('shape_controls_sha256'):
        write_json(out/'face-readback.json',verify_face_program(n,read_json(run/'face-template-program.json')))
    a=Image.open(a_path).convert('RGBA');b=Image.open(b_path).convert('RGBA')
    if a.size!=b.size:raise ValueError('Neutral viewport dimensions differ')
    box_a=a.getchannel('A').getbbox();box_b=b.getchannel('A').getbbox()
    aa=np.array(a,float);bb=np.array(b,float);mask=(aa[:,:,3]>0)|(bb[:,:,3]>0)
    rgb=float(np.mean(abs(aa[:,:,:3]*aa[:,:,3:]/255-bb[:,:,:3]*bb[:,:,3:]/255)[mask]))
    alpha=float(np.mean(abs(aa[:,:,3]-bb[:,:,3])[mask]))
    threshold=read_json(Path(__file__).resolve().parents[1]/'structures/humanoid-prior.json')['acceptance']['neutral_pixel_mae']
    fully_visible=all(box[0]>0 and box[1]>0 and box[2]<a.width and box[3]<a.height for box in (box_a,box_b))
    camera=read_json(run/'render-camera.json')['data']
    raster_tolerance=int(np.ceil(1/min(camera['transform']['scale'])))+1
    bbox_error=int(np.max(abs(np.asarray(box_a)-box_b)))
    report={'source_render':str(a_path),'rig_render':str(b_path),'source_sha256':digest(a_path),'rig_sha256':digest(b_path),
            'size':list(a.size),'source_alpha_bbox':box_a,'rig_alpha_bbox':box_b,'full_alpha_bounds_inside_viewport':fully_visible,
            'premultiplied_rgb_mae_on_alpha_union':rgb,'alpha_mae_on_alpha_union':alpha,'threshold':threshold,
            'source_identity_verified':True,'bbox_max_error_pixels':bbox_error,
            'bbox_filter_tolerance_pixels':raster_tolerance,
            'passed':bool(fully_visible and bbox_error<=raster_tolerance and rgb<=threshold and alpha<=threshold)}
    write_json(out/'neutral-comparison.json',report);print(report,flush=True)
    if not report['passed']:print('Recorded neutral comparison differences; continuing work',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--njc',required=True)
    a=p.parse_args();validate(a.run,a.njc)
