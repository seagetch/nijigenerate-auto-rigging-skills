"""PSD-only entry point: generate every intermediate afresh, then verify output."""
import argparse,subprocess,sys
from pathlib import Path
from riglib.live import Live
from riglib.data import digest,write_json,read_json


def run(psd,out,njc,stop_after=None):
    psd=Path(psd).resolve();out=Path(out).resolve();out.mkdir(parents=True,exist_ok=True)
    if out!=psd.parent/psd.stem:raise ValueError('Outputs must stay directly in the PSD-named sibling directory')
    scripts=Path(__file__).resolve().parent
    # A repeated run regenerates each intermediate from the PSD. An owned
    # output directory is reusable; none of its old geometry is an input.
    origin=out/'run-origin.json'
    if any(out.iterdir()):
        if origin.is_file():
            previous=read_json(origin)
            if (Path(previous['external_character_input']).resolve()!=psd or
                    previous['psd_sha256']!=digest(psd)):
                raise ValueError('Output belongs to a different PSD input')
        elif {p.name for p in out.iterdir()}-{'run.log','run-status.json'}:
            raise ValueError('Output directory is not owned by this PSD generator')
    # Retire current-generation manifests before constructing new UUIDs. Old
    # pictures cannot be counted as evidence for this fresh model.
    for name in ('program.json','native-state.json','completion-stages.json','validation.json',
                 'neutral-comparison.json','visual-review.json','head-support-review.json',
                 'hierarchy-applied.json','hierarchy-readback.json','depth-angle-program.json',
                 'reference-transfer-readback.json','shape-corrections-program.json',
                 'shape-corrections-pending.json','shape-controls-program.json',
                 'source-uv-program.json','source-uv-applied-check.json','head-drive-observation.json'):
        (out/name).unlink(missing_ok=True)
    skill=scripts.parent
    sources=sorted([*scripts.rglob('*.py'),* (skill/'structures').glob('*.json'),* (skill/'templates').rglob('*.json')])
    write_json(out/'run-origin.json',{'external_character_input':str(psd),'psd_sha256':digest(psd),
        'starting_point':'fresh PSD extraction and NJC import; no existing model or observation input',
        'code_and_rules':{str(p.relative_to(skill)):digest(p) for p in sources}})
    def command(name,*args):
        print('Running',name,flush=True)
        with subprocess.Popen([sys.executable,'-B',str(scripts/name),*map(str,args)],
                stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf-8',errors='replace',
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)) as process:
            for line in process.stdout:print(line,end='',flush=True)
            code=process.wait()
            if code:raise subprocess.CalledProcessError(code,process.args)
    command('rig.py','prepare-psd','--psd',psd,'--out',out)
    n=Live(njc,out/'import-journal')
    n.call('FileCommand_ImportPSD',path=str(psd),keepStructure=True,layerGroupNodeType='DynamicComposite')
    command('prepare_live_psd.py','--manifest',out/'psd-source.json','--out',out,'--njc',njc)
    command('derive_psd_evidence.py','--run',out)
    if stop_after=='evidence':return
    command('prepare_part_meshes.py','--run',out,'--njc',njc)
    if read_json(out/'evidence.json')['kind']!='humanoid':
        command('build_local.py','--run',out,'--njc',njc)
        command('finish_psd_rig.py','--run',out,'--njc',njc)
        return
    command('build_native.py','--observation',out/'observation.json','--assembly',out/'assembly.json',
            '--evidence',out/'evidence.json','--program',out/'program.json','--apply','--njc',njc,
            '--source',out/'automeshed.inx','--out',out/'rigged.inx','--journal',out/'build-journal')
    command('finish_psd_rig.py','--run',out,'--njc',njc)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--psd',required=True);p.add_argument('--out',required=True);p.add_argument('--njc',required=True)
    p.add_argument('--stop-after',choices=['evidence'])
    a=p.parse_args();run(a.psd,a.out,a.njc,a.stop_after)
