"""Render independent eye and mouth expression cases through NJC."""
import argparse,time
from pathlib import Path
from PIL import Image,ImageDraw
from riglib.data import read_json,write_json
from riglib.live import Live
from build_native import require_single_rig


def render(run,njc):
    run=Path(run).resolve();out=run/'facial-control-renders';out.mkdir(exist_ok=True)
    state=read_json(run/'native-state.json');n=Live(njc,out/'journal')
    require_single_rig(n,state['rig_root'],state['bones'].values())
    n.call('ToolCommand_ModelEditMode');n.call('ViewportCommand_ResetParameters');n.call('ViewportCommand_FitViewportToModel')
    cases=[('neutral',None,None)]
    for side in ('L','R'):
        for y in (-1,0,1):cases.append((f'Blink-{side}-expression-{y}',f'Eye::{side}::Blink',[1,y]))
        cases.append((f'Gaze-{side}',f'Eye::{side}::X-Y',[1,0]))
        cases.append((f'Brow-{side}',f'Eyebrow::{side}',[1,1]))
    for x in (0,.5,1):
        for y in (-1,0,1):cases.append((f'Mouth-{x}-{y}','Mouth::Open',[x,y]))
    for label,name,value in cases:
        n.call('ViewportCommand_ResetParameters')
        if name:n.call('ParameditCommand_SetParameterKeypoint',context={'parameters':[state['parameters'][name]],'parameterValue':value})
        time.sleep(.15);n.call('ViewCommand_SaveScreenshot',filename=str(out/(label+'.png')))
        print('Rendered '+label,flush=True)
    n.call('ViewportCommand_ResetParameters');n.save(state['output'])
    neutral=Image.open(out/'neutral.png').convert('RGBA');x0,y0,x1,y1=neutral.getchannel('A').getbbox()
    h=y1-y0;cx=(x0+x1)/2;crop=(int(cx-h*.19),y0,int(cx+h*.19),int(y0+h*.26))
    sheet=Image.new('RGB',(1500,((len(cases)+4)//5)*330),(235,235,235));draw=ImageDraw.Draw(sheet)
    for k,(label,_,_) in enumerate(cases):
        im=Image.open(out/(label+'.png')).convert('RGBA').crop(crop);im.thumbnail((300,295))
        x=k%5*300;y=k//5*330;sheet.paste(im,(x+(300-im.width)//2,y),im);draw.text((x+5,y+300),label,fill='black')
    sheet.save(out/'facial-controls-sheet.png')
    write_json(out/'cases.json',{'cases':[{'label':l,'parameter':n,'value':v} for l,n,v in cases],
        'saved_model':state['output'],'transport':'njc','visual_review_required':True})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--njc',required=True)
    a=p.parse_args();render(a.run,a.njc)
