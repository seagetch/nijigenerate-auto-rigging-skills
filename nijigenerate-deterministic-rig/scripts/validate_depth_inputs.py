"""Measure effective depth from NJC nodes; this is not visual acceptance."""
import argparse
from pathlib import Path
import numpy as np
from riglib.live import Live
from riglib.data import read_json,write_json,json_digest
from riglib.model import observe_model


def validate(run,njc):
    run=Path(run).resolve();program=read_json(run/'program.json');state=read_json(run/'native-state.json')
    n=Live(njc,run/'depth-input-journal')
    n.call('ToolCommand_ModelEditMode');n.call('ViewportCommand_ResetParameters')
    observation=observe_model(client=n,require_parameters=False)
    nodes={v['uuid']:v for v in observation['nodes']}
    root=n.read(state['rig_root'])['item']['data']
    root_inverse=np.linalg.inv(np.asarray(nodes[state['rig_root']]['nominal_world_matrix']))
    bindings={b['target']:b for b in root['bindings']};meshes={};all_points=[]
    for domain in program['domains']:
        uid=state['grids'][domain['id']];data=n.read(uid)['item']['data']
        xy=np.array([[x,y,0.,1.] for y in data['grid_axis_y'] for x in data['grid_axis_x']])
        transform=root_inverse@np.asarray(nodes[uid]['nominal_world_matrix'])
        points=xy@transform.T;all_points.extend(points[:,:2])
        meshes[uid]=(data,points)
    span=np.ptp(np.asarray(all_points),axis=0)
    scale=max(1.,float(span.max())*.42/2.9)
    scale_error=abs(scale-program['native_depth_scale'])
    report={'program_sha256':program['content_sha256'],'native_depth_scale_observed':scale,
            'compiled_depth_scale':program['native_depth_scale'],'scale_difference':scale_error,'surfaces':[],
            'visual_volume_accepted':False,'scope':'NJC raw depth, native unit and source settings; not a claim of anatomical or visual correctness'}
    for domain in program['domains']:
        uid=state['grids'][domain['id']];data,points=meshes[uid]
        raw=np.asarray(data['depths']);expected=np.asarray(domain['depths'])
        if raw.shape!=expected.shape or abs(raw-expected).max()>1e-7:
            raise ValueError('Stored Grid depth differs from compiled depth: '+domain['id'])
        if not np.isfinite(raw).all():raise ValueError('Native depth contains non-finite values: '+domain['id'])
        sources=[]
        for source in bindings[uid]['sourceSettings']:
            effective=(raw*source['depthScale']+source['depthOffset'])*scale+points[:,2]
            sources.append({'bone':source['bone'],'depth_scale':source['depthScale'],
                            'depth_offset':source['depthOffset'],'source_rotation':source['rotation'],
                            'effective_z_range_model':list(map(float,[effective.min(),effective.max()])),
                            'effective_relief_model':float(np.ptp(effective))})
        report['surfaces'].append({'id':domain['id'],'grid':uid,'native_vertices':len(raw),
            'constant_depth_observed':bool(np.ptp(raw)<=1e-7),
            'raw_depth_range':list(map(float,[raw.min(),raw.max()])),
            'surface_xy_span_model':np.ptp(points[:,:2],axis=0).tolist(),'bone_sources':sources})
    report['depth_units_verified']=bool(scale_error<=max(.001,scale*1e-5));report['content_sha256']=json_digest(report)
    write_json(run/'depth-input-validation.json',report)
    print('Verified native depth units and stored relief on',len(report['surfaces']),'Grids; visual volume acceptance remains required',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--njc',required=True)
    a=p.parse_args();validate(a.run,a.njc)
