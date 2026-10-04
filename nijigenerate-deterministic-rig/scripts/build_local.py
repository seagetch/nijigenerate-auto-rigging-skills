"""Construct PSD-local mechanisms without inventing missing body anatomy."""
import argparse
from pathlib import Path
from riglib.data import read_json,write_json,json_digest
from riglib.live import Live,created_id
from riglib.model import read_model_metadata
from build_native import model_structure,require_single_rig


def build(run,njc):
    run=Path(run).resolve();e=read_json(run/'evidence.json');o=read_json(run/'observation.json')
    if e['kind'] not in ('mouth','local','face'):raise ValueError('Expected a local mechanism PSD')
    if not e['part_mesh_generation']['saved_readback_verified']:raise ValueError('Native mesh readback is required')
    n=Live(njc,run/'local-build-journal')
    identity=n.ensure_source(run/'automeshed.inx',e['part_mesh_source']['metadata_sha256'])
    if identity['metadata_sha256']!=e['part_mesh_source']['metadata_sha256']:raise ValueError('Local build source identity mismatch')
    if any(t in ('DepthRigRoot','DepthBone') for _,t,_ in model_structure(n)[0]):raise ValueError('Source already has a rig')
    roots=[r['uuid'] for r in o['nodes'] if r['parent'] is None]
    if len(roots)!=1:raise ValueError('Expected one source root')
    p={'schema_version':'rig-local-program/1','kind':e['kind'],'source':e['part_mesh_source'],
       'psd_import_source':o['source'],'observation_sha256':json_digest(o),'evidence_sha256':json_digest(e),
       'domains':[{'id':'local','parts':[{'uuid':m['part']} for m in e['semantic_materials']]}]}
    p['content_sha256']=json_digest(p);write_json(run/'program.json',p)
    root=created_id(n.call('DepthBoneCommand_CreateDepthRigRoot',parent=roots[0],name='Rig::Local'))
    state={'kind':e['kind'],'program_sha256':p['content_sha256'],'output':str(run/'rigged.inx'),
           'rig_root':root,'bones':{},'grids':{},'groups':{},'parameters':{}}
    n.save(state['output']);require_single_rig(n,root,[])
    write_json(run/'native-state.json',state)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--njc',required=True)
    a=p.parse_args();build(a.run,a.njc)
