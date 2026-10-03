"""Render the generated rig at exactly the previously captured reference poses."""
import argparse
from pathlib import Path
from PIL import Image,ImageDraw
from riglib.data import read_json,write_json,digest
from riglib.live import Live
from build_native import require_single_rig


def compare(run,njc):
    run=Path(run).resolve();skill=Path(__file__).resolve().parents[1]
    state=read_json(run/'native-state.json');p=read_json(run/'program.json')
    sources=read_json(skill/'references/designated-reference-set.json')['references']
    captures=[Path(s['capture_directory'])/'poses' for s in sources]
    cases=read_json(captures[0]/'verification.json')['cases']
    if any(read_json(f/'verification.json')['cases']!=cases for f in captures):raise ValueError('Reference pose cases differ')
    n=Live(njc,run/'comparison-journal');require_single_rig(n,state['rig_root'],state['bones'].values())
    out=run/'reference-comparison';out.mkdir(exist_ok=True)
    n.call('ToolCommand_ModelEditMode');n.call('ViewportCommand_ResetParameters');n.call('ViewportCommand_FitViewportToModel')
    for case in cases:
        n.call('ViewportCommand_ResetParameters')
        for parameter,value in case['parameters'].items():
            n.call('ParameditCommand_SetParameterKeypoint',context={'parameters':[state['parameters'][parameter]],'parameterValue':value})
        n.call('ViewCommand_SaveScreenshot',filename=str(out/(case['name']+'.png')))
    n.call('ViewportCommand_ResetParameters')
    for family in ('Face','Body'):
        selected=[c for c in cases if c['name']=='neutral' or c['name'].startswith(family+'-')]
        folders=[captures[0],out,captures[1]];labels=[sources[0]['label']+' reference','Generated common template',sources[1]['label']+' reference']
        sheet=Image.new('RGB',(1050,len(selected)*390+40),(242,242,242));draw=ImageDraw.Draw(sheet)
        for col,(folder,label) in enumerate(zip(folders,labels)):
            neutral=Image.open(folder/'neutral.png').convert('RGBA');x0,y0,x1,y1=neutral.getchannel('A').getbbox()
            if family=='Face':
                h=y1-y0;cx=(x0+x1)/2;box=(int(cx-.22*h),int(y0-.01*h),int(cx+.22*h),int(y0+.27*h))
            else:box=(x0-20,y0-20,x1+20,y1+20)
            draw.text((col*350+8,8),label,fill='black')
            for row,case in enumerate(selected):
                im=Image.open(folder/(case['name']+'.png')).convert('RGBA').crop(box);im.thumbnail((340,355))
                x=col*350+(350-im.width)//2;y=40+row*390
                sheet.paste(im,(x,y+(355-im.height)//2),im);draw.text((col*350+8,y+365),case['name'],fill='black')
        sheet.save(out/(family+'-comparison.png'))
    write_json(out/'comparison.json',{'template_sha256':p['reference_template']['sha256'],
        'cases':cases,'generated_frames':len(cases),'references':[s['public_snapshot_sha256'] for s in sources],
        'source_models_opened_or_modified':False,'generated_model_neutral_restored':True,
        'sheets':{f:str(out/(f+'-comparison.png')) for f in ('Face','Body')},'visual_review_required':True,
        'render_hashes':{c['name']:digest(out/(c['name']+'.png')) for c in cases}})
    print('Rendered',len(cases),'matching reference poses; generated rig left neutral',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--run',required=True);parser.add_argument('--njc',required=True)
    a=parser.parse_args();compare(a.run,a.njc)
