"""PSD-only entry point: generate every intermediate afresh, then verify output."""
import argparse,subprocess,sys
from pathlib import Path
from riglib.live import Live
from riglib.data import digest,write_json,read_json


def run(psd,out,njc):
    psd=Path(psd).resolve();out=Path(out).resolve();out.mkdir(parents=True,exist_ok=True)
    scripts=Path(__file__).resolve().parent
    # A repeated run regenerates each intermediate from the PSD. An owned
    # output directory is reusable; none of its old geometry is an input.
    origin=out/'run-origin.json'
    if any(out.iterdir()):
        if not origin.is_file():raise ValueError('Output directory is not owned by this PSD generator')
        previous=read_json(origin)
        if (Path(previous['external_character_input']).resolve()!=psd or
                previous['psd_sha256']!=digest(psd)):
            raise ValueError('Output belongs to a different PSD input')
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
    command('rig.py','prepare-psd','--psd',psd,'--out',out/'source')
    n=Live(njc,out/'import-journal')
    n.call('FileCommand_ImportPSD',path=str(psd),keepStructure=True,layerGroupNodeType='Node')
    command('prepare_live_psd.py','--manifest',out/'source/psd-source.json','--out',out,'--njc',njc)
    command('derive_psd_evidence.py','--run',out)
    command('prepare_part_meshes.py','--run',out,'--njc',njc)
    command('build_native.py','--observation',out/'observation.json','--assembly',out/'assembly.json',
            '--evidence',out/'evidence.json','--program',out/'program.json','--apply','--njc',njc,
            '--source',out/'automeshed.inx','--out',out/'rigged.inx','--journal',out/'build-journal')
    command('finish_psd_rig.py','--run',out,'--njc',njc)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--psd',required=True);p.add_argument('--out',required=True);p.add_argument('--njc',required=True)
    a=p.parse_args();run(a.psd,a.out,a.njc)
