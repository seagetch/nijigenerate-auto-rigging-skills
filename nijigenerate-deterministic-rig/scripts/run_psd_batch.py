"""Sequential PSD-only generation with per-file outcomes and an aggregate exit code."""
import argparse
import os
import subprocess
import sys
from datetime import datetime,timezone
from pathlib import Path
from riglib.data import read_json,write_json,digest
from build_workspace_report import build as build_report


def batch(directory,out,njc,only=None,stop_after=None,resume=False,render_images=False):
    directory=Path(directory).resolve();out=Path(out).resolve()
    if out!=directory:raise ValueError('Use the PSD directory itself; process-specific output directories are forbidden')
    sources=sorted(directory.glob('*.psd'),key=lambda p:p.name.casefold())
    if only:
        wanted=set(only);available={p.name for p in sources}|{p.stem for p in sources}
        if wanted-available:raise ValueError('Unknown PSD selection: '+', '.join(sorted(wanted-available)))
        sources=[p for p in sources if p.name in wanted or p.stem in wanted]
    if not sources:raise ValueError('No PSD files were selected')
    out.mkdir(parents=True,exist_ok=True);entry=Path(__file__).with_name('resume_psd_rig.py' if resume else 'run_psd_rig.py')
    def report_progress():
        try:build_report(directory)
        except (OSError,MemoryError,ValueError) as error:print('Report update deferred: '+type(error).__name__,flush=True)
    report={'started':datetime.now(timezone.utc).isoformat(),'phase':stop_after or 'full','items':[],
            'rig_complete':False,'external_character_inputs':'selected PSDs only'}
    for index,psd in enumerate(sources,1):
        target=out/psd.stem;before=digest(psd)
        row={'psd':str(psd),'psd_sha256':before,'output':str(target),'status':'running','rig_complete':False,'phase':stop_after or 'full'}
        target.mkdir(exist_ok=True)
        report['items'].append(row);write_json(target/'run-status.json',row)
        command=[sys.executable,'-B',str(entry),'--psd',str(psd),'--out',str(target),'--njc',str(njc)]
        if stop_after:command+=['--stop-after',stop_after]
        if render_images:command+=['--render-images']
        print(f'{index}/{len(sources)} {psd.name}',flush=True)
        with (target/'run.log').open('a' if resume else 'w',encoding='utf-8') as log:
            if resume:log.write('\nContinuing remaining stages under the user instruction to record inspection findings without stopping.\n')
            env=dict(os.environ,PYTHONUTF8='1',PYTHONUNBUFFERED='1')
            process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf-8',
                errors='replace',env=env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            for line in process.stdout:
                log.write(line);log.flush();print(line,end='',flush=True)
                if line.startswith(('Running ','Resuming ','Rendered neutral')):report_progress()
            row['exit_code']=process.wait()
        row['source_unchanged']=digest(psd)==before
        row['status']='processed' if row['exit_code']==0 and row['source_unchanged'] else 'execution_error'
        completion=target/'completion-stages.json'
        if not stop_after and completion.exists():
            result=read_json(completion)
            row['numerical_stages_passed']=bool(result.get('numerical_stages_passed'))
            row['visual_review_required']=True
            row['all_stages_attempted']=bool(result.get('all_stages_attempted'))
            row['rendered_images']=result.get('rendered_images',0)
            row['stage_errors']=result.get('stage_errors',[])
            if row['stage_errors']:row['status']='execution_error'
        write_json(target/'run-status.json',row)
        report_progress()
    report['finished']=datetime.now(timezone.utc).isoformat()
    report['phase_passed']=all(r['status']=='processed' for r in report['items'])
    return 0 if report['phase_passed'] else 1


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--directory',required=True);p.add_argument('--out',required=True)
    p.add_argument('--njc',required=True);p.add_argument('--only',nargs='+');p.add_argument('--stop-after',choices=['evidence'])
    p.add_argument('--resume',action='store_true')
    p.add_argument('--render-images',action='store_true',help='Export optional review images for each PSD')
    a=p.parse_args();raise SystemExit(batch(a.directory,a.out,a.njc,a.only,a.stop_after,a.resume,a.render_images))
