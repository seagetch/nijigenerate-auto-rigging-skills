"""Readable per-parameter sheets from already captured native renders."""
import argparse
from pathlib import Path
from PIL import Image,ImageDraw
from riglib.data import read_json


def create(run):
    run=Path(run).resolve();out=run;report=read_json(out/'validation.json')
    state=read_json(run/'native-state.json');neutral=Image.open(out/'neutral.png').convert('RGBA')
    box=neutral.getchannel('A').getbbox();x0,y0,x1,y1=box
    humanoid=state.get('kind','humanoid')=='humanoid';groups={'core':[],'body':[],'face-angles':[],'head-body-yaw':[]}
    for row in report['rendered']:
        if row['label']=='neutral':continue
        if 'Body::Yaw-Pitch' in row['pose'] and len(row['pose'])==1:groups['head-body-yaw'].append(row)
        if row['label']=='combined' or any(k.startswith(('Body::','Face::')) for k in row['pose']):
            groups['core'].append(row)
            if row['label']=='combined' or any(k.startswith('Body::') for k in row['pose']):groups['body'].append(row)
            if any(k.startswith('Face::') for k in row['pose']):groups['face-angles'].append(row)
        else:
            name=next(iter(row['pose']));groups.setdefault(name.replace('::','-'),[]).append(row)
    for name,rows in groups.items():
        if not rows:continue
        rows=[{'file':str(out/'neutral.png'),'label':'neutral'},*rows]
        columns=4;tile_w=400;tile_h=320;sheet=Image.new('RGB',(columns*tile_w,((len(rows)+columns-1)//columns)*tile_h),(35,35,35));draw=ImageDraw.Draw(sheet)
        if name in ('core','body') or not humanoid:
            bounds=[Image.open(row['file']).convert('RGBA').getchannel('A').getbbox() for row in rows]
            bounds=[b for b in bounds if b]
            crop=(min(b[0] for b in bounds),min(b[1] for b in bounds),max(b[2] for b in bounds),max(b[3] for b in bounds))
        else:crop=(int((x0+x1)/2-(y1-y0)*.16),y0,int((x0+x1)/2+(y1-y0)*.16),int(y0+(y1-y0)*.25))
        for i,row in enumerate(rows):
            image=Image.open(row['file']).convert('RGBA').crop(crop);image.thumbnail((tile_w,tile_h-25))
            x=(i%columns)*tile_w;y=(i//columns)*tile_h
            sheet.paste(image,(x+(tile_w-image.width)//2,y),image)
            pose=row.get('pose',{})
            label=row['label'] if not pose or len(pose)>1 else next(iter(pose))+': '+str(next(iter(pose.values())))
            draw.text((x+8,y+tile_h-20),label,fill='white')
        sheet.save(out/('body-sheet.jpg' if name=='body' else 'review-'+name+'.jpg'))
    from depth_review import create as create_depth_review
    create_depth_review(run)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);a=p.parse_args();create(a.run)
