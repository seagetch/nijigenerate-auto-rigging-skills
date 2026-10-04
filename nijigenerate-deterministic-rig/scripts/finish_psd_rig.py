"""Finish and verify a compiled PSD-derived rig through NJC."""
import argparse
import subprocess
import sys
from pathlib import Path
from datetime import datetime,timezone
from riglib.data import read_json,write_json,json_digest,digest


def finish(run,njc,start_at=None,refresh_controls=False):
    run=Path(run).resolve();scripts=Path(__file__).resolve().parent
    program=read_json(run/'program.json');state=read_json(run/'native-state.json')
    evidence=read_json(run/'evidence.json');observation=read_json(run/'observation.json')
    if state['program_sha256']!=program['content_sha256'] or program['evidence_sha256']!=json_digest(evidence):
        raise ValueError('Rig and PSD evidence do not belong to this compiled program')
    if program['observation_sha256']!=json_digest(observation):raise ValueError('PSD observation mismatch')
    report={'program_sha256':program['content_sha256'],'stages':[],'rig_complete':False,
            'inspection_policy':'record findings and continue every remaining stage; numerical results are not acceptance'}
    previous=read_json(run/'completion-stages.json') if start_at else None
    if previous and previous['program_sha256']!=program['content_sha256']:raise ValueError('Resume program mismatch')
    started=start_at is None
    def stage(name,*args):
        nonlocal started
        if not started:
            if name==start_at:started=True
            elif refresh_controls and name=='apply_shape_controls.py':pass
            else:
                prior=[r for r in previous['stages'] if r['name']==name]
                if not prior:raise ValueError('Cannot resume past an unattempted stage: '+name)
                report['stages'].append(prior[-1]);return
        print('Running '+name,flush=True)
        provenance={'started':datetime.now(timezone.utc).isoformat(),
                    'script_sha256':digest(scripts/name),
                    'shared_code_sha256':{p.name:digest(p) for p in sorted((scripts/'riglib').glob('*.py'))}}
        with subprocess.Popen([sys.executable,'-B',str(scripts/name),*map(str,args)],
                stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf-8',errors='replace',
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)) as process:
            for line in process.stdout:print(line,end='',flush=True)
            code=process.wait()
        report['stages'].append({'name':name,'exit_code':code,**provenance})
        write_json(run/'completion-stages.json',report)
        if code:print('Recorded stage finding; continuing remaining work: '+name,flush=True)
    if not state.get('source_uv_program_sha256'):stage('preserve_source_uv.py','--run',run,'--njc',njc)
    stage('apply_shape_controls.py','--run',run,'--njc',njc,*(['--replace-owned'] if refresh_controls else []))
    humanoid=evidence['kind']=='humanoid'
    if humanoid:
        stage('validate_depth_inputs.py','--run',run,'--njc',njc)
        stage('bake_depth_angles.py','--run',run,'--njc',njc)
    stage('validate_saved_rig.py','--state',run/'native-state.json','--out',run,'--njc',njc)
    if humanoid:stage('review_head_support.py','--run',run,'--njc',njc)
    stage('validate_neutral.py','--run',run,'--njc',njc)
    if humanoid:
        stage('validate_reference_transfer.py','--run',run,'--njc',njc)
        stage('validate_semantic_reconstruction.py','--template',scripts.parent/'structures/reference-humanoid.registered.json',
            '--program',run/'program.json','--out',run/'semantic-reconstruction.json')
    if not started:raise ValueError('Unknown resume stage')
    report['all_stages_attempted']=True
    report['stage_errors']=[r['name'] for r in report['stages'] if r['exit_code']]
    validation=read_json(run/'validation.json') if (run/'validation.json').is_file() else {}
    neutral=read_json(run/'neutral-comparison.json') if (run/'neutral-comparison.json').is_file() else {}
    report['deformation_findings']=len(validation.get('numerical_failures',[]))
    report['numerical_stages_passed']=bool(not report['stage_errors'] and
        not report['deformation_findings'] and neutral.get('passed'))
    report['rendered_images']=len(validation.get('rendered',[]))
    report['visual_review_required']=True
    write_json(run/'completion-stages.json',report)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--njc',required=True)
    p.add_argument('--from-stage')
    a=p.parse_args();finish(a.run,a.njc,a.from_stage)
