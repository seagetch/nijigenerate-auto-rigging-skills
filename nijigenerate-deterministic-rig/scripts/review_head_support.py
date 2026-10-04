"""Capture attachment, signed yaw and compound poses without loading a model."""
import argparse
from pathlib import Path
from PIL import Image,ImageDraw
from riglib.live import Live
from riglib.data import read_json,write_json,digest
from riglib.render_camera import capture
from build_native import require_single_rig

POSES=[('neutral',{}),
 ('face-minus',{'Face::Yaw-Pitch':[-1,0]}),('face-plus',{'Face::Yaw-Pitch':[1,0]}),
 ('body-minus',{'Body::Yaw-Pitch':[-1,0]}),('body-plus',{'Body::Yaw-Pitch':[1,0]}),
 ('body-pitch-minus',{'Body::Yaw-Pitch':[0,-1]}),('body-pitch-plus',{'Body::Yaw-Pitch':[0,1]}),
 ('face-pitch-minus',{'Face::Yaw-Pitch':[0,-1]}),('face-pitch-plus',{'Face::Yaw-Pitch':[0,1]}),
 ('roll-minus',{'Body::Roll':[-1]}),('roll-plus',{'Body::Roll':[1]}),
 ('combined-minus',{'Body::Yaw-Pitch':[-1,-.5],'Face::Yaw-Pitch':[-1,.5]}),
 ('combined-plus',{'Body::Yaw-Pitch':[1,.5],'Face::Yaw-Pitch':[1,-.5]})]


def review(run,njc):
    run=Path(run).resolve();s=read_json(run/'native-state.json');p=read_json(run/'program.json')
    n=Live(njc,run/'head-support-review-journal');require_single_rig(n,s['rig_root'],s['bones'].values())
    rows=[]
    for label,pose in POSES:
        n.call('ViewportCommand_ResetParameters')
        for name,value in pose.items():
            n.call('ParameditCommand_SetParameterKeypoint',context={'parameters':[s['parameters'][name]],'parameterValue':value})
        path=run/('support-after-'+label+'.png');capture(n,run,path)
        rows.append({'label':label,'pose':pose,'file':str(path),'sha256':digest(path)})
    n.call('ViewportCommand_ResetParameters');n.save(s['output'])
    neutral=Image.open(rows[0]['file']).convert('RGBA');x0,y0,x1,y1=neutral.getchannel('A').getbbox()
    h=y1-y0;cx=(x0+x1)/2;crop=(int(cx-h*.34),int(y0-h*.03),int(cx+h*.34),int(y0+h*.40))
    w,th,columns=450,350,3
    sheet=Image.new('RGB',(w*columns,th*((len(rows)+columns-1)//columns)),(32,38,48));draw=ImageDraw.Draw(sheet)
    for i,row in enumerate(rows):
        im=Image.open(row['file']).convert('RGBA').crop(crop);im.thumbnail((w,th-48))
        x=(i%columns)*w;y=(i//columns)*th;sheet.paste(im,(x+(w-im.width)//2,y),im)
        draw.text((x+5,y+th-44),row['label'],fill='white')
        for k,(name,value) in enumerate(row['pose'].items()):draw.text((x+5,y+th-30+12*k),name+' '+str(value),fill='white')
    sheet.save(run/'review-head-support.jpg')
    write_json(run/'head-support-review.json',{'program_sha256':p['content_sha256'],'rendered':rows,
        'sheet_sha256':digest(run/'review-head-support.jpg'),'visually_reviewed':False,
        'scope':'native saved active model, signed yaw, pitch, roll and combined attachment views; no reload'})
    print('Captured native head/body attachment review',flush=True)


if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--run',required=True);a.add_argument('--njc',required=True)
    v=a.parse_args();review(v.run,v.njc)
