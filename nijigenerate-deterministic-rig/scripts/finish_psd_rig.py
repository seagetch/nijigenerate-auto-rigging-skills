"""Finish and verify a compiled PSD-derived rig through NJC."""
import argparse
import subprocess
import sys
from pathlib import Path
from riglib.data import read_json,write_json,json_digest


def finish(run,njc,start_at=None):
    run=Path(run).resolve();scripts=Path(__file__).resolve().parent
    program=read_json(run/'program.json');state=read_json(run/'native-state.json')
    evidence=read_json(run/'evidence.json');observation=read_json(run/'observation.json')
    if state['program_sha256']!=program['content_sha256'] or program['evidence_sha256']!=json_digest(evidence):
        raise ValueError('Rig and PSD evidence do not belong to this compiled program')
    if program['observation_sha256']!=json_digest(observation):raise ValueError('PSD observation mismatch')
    report={'program_sha256':program['content_sha256'],'stages':[],'rig_complete':False}
    previous=read_json(run/'completion-stages.json') if start_at else None
    if previous and previous['program_sha256']!=program['content_sha256']:raise ValueError('Resume program mismatch')
    started=start_at is None
    def stage(name,*args):
        nonlocal started
        if not started:
            if name==start_at:started=True
            else:
                prior=[r for r in previous['stages'] if r['name']==name]
                if not prior or prior[-1]['exit_code']!=0:raise ValueError('Cannot skip an incomplete stage: '+name)
                report['stages'].append(prior[-1]);return
        print('Running '+name,flush=True)
        with subprocess.Popen([sys.executable,'-B',str(scripts/name),*map(str,args)],
                stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf-8',errors='replace',
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)) as process:
            for line in process.stdout:print(line,end='',flush=True)
            code=process.wait()
        report['stages'].append({'name':name,'exit_code':code})
        write_json(run/'completion-stages.json',report)
        if code:raise subprocess.CalledProcessError(code,name)
    stage('apply_facial_controls.py','--run',run,'--njc',njc)
    stage('bake_depth_angles.py','--run',run,'--njc',njc)
    stage('preserve_source_uv.py','--run',run,'--njc',njc)
    from riglib.reference_materials import require_shape_based_part_solver
    try:
        require_shape_based_part_solver()
    except RuntimeError as error:
        report['blocked_stage']='shape_based_part_corrections'
        report['error']=str(error)
        write_json(run/'completion-stages.json',report)
        raise
    stage('validate_saved_rig.py','--state',run/'native-state.json','--out',run/'validation','--njc',njc)
    stage('validate_neutral.py','--run',run,'--njc',njc)
    stage('validate_reference_transfer.py','--run',run,'--njc',njc)
    stage('validate_semantic_reconstruction.py','--template',scripts.parent/'structures/reference-humanoid.registered.json',
        '--program',run/'program.json','--out',run/'validation/semantic-reconstruction.json')
    if not started:raise ValueError('Unknown resume stage')
    report['numerical_stages_passed']=True
    report['visual_review_required']=True
    write_json(run/'completion-stages.json',report)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--njc',required=True)
    p.add_argument('--from-stage')
    a=p.parse_args();finish(a.run,a.njc,a.from_stage)
