"""Render designated, captured references at their actual existing keys via NJC."""
import argparse
from pathlib import Path
from PIL import Image, ImageDraw
from riglib.data import read_json, write_json, json_digest
from riglib.live import Live
from capture_reference import capture


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--capture', required=True)
    p.add_argument('--njc', required=True)
    a = p.parse_args()
    folder = Path(a.capture).resolve()
    identity = read_json(folder/'identity.json')
    snapshot = read_json(folder/'snapshot.json')
    if json_digest(snapshot) != identity['public_snapshot_sha256']:
        raise ValueError('Capture fingerprint differs')
    n = Live(a.njc)
    n.open(identity['source_path'])
    if json_digest(capture(n)) != identity['public_snapshot_sha256']:
        raise ValueError('NJC-opened reference differs from captured source')
    params = {p['name']:p['uuid'] for p in snapshot['parameters']}
    axes = {b['parameter']['name']:b['axisValues'] for b in snapshot['bindings']}
    cases = [('neutral', {})]
    for family in ('Face','Body'):
        name = family+'::Yaw-Pitch'
        for tag,key in [('yaw-minus',[-1,0]),('yaw-plus',[1,0]),
                        ('pitch-minus',[0,-1]),('pitch-plus',[0,1]),
                        ('diagonal',[-1,1]),('middle',[.5,.5])]:
            cases.append((family+'-'+tag,{name:key}))
        cases.extend((family+'-roll-'+tag,{family+'::Roll':[value]})
                     for tag,value in [('minus',-1),('plus',1)])
    cases.append(('combined',{'Face::Yaw-Pitch':[-1,.5], 'Body::Yaw-Pitch':[.5,-.5]}))
    out=folder/'poses';out.mkdir(exist_ok=True)
    n.call('ViewportCommand_ResetParameters')
    n.call('ViewportCommand_FitViewportToModel')
    try:
        for tag,values in cases:
            n.call('ViewportCommand_ResetParameters')
            for name,key in values.items():
                actual=key if len(key)==2 else [key[0],axes[name][1][0]]
                if any(not any(abs(v-q)<1e-6 for q in axis) for v,axis in zip(actual,axes[name])):
                    raise ValueError('Requested pose is absent from reference axes: '+name)
                n.call('ParameditCommand_SetParameterKeypoint',context={'parameters':[params[name]],'parameterValue':actual})
            n.call('ViewCommand_SaveScreenshot',filename=str(out/(tag+'.png')))
            print('Rendered '+tag,flush=True)
    finally:
        n.call('ViewportCommand_ResetParameters')
    neutral=Image.open(out/'neutral.png').convert('RGBA')
    bbox=neutral.getchannel('A').getbbox()
    if bbox is None:raise ValueError('Empty neutral render')
    for family in ('Face','Body'):
        selected=[(tag,values) for tag,values in cases if tag=='neutral' or tag.startswith(family+'-')]
        sheet=Image.new('RGB',(1200,1500),(242,242,242));draw=ImageDraw.Draw(sheet)
        x0,y0,x1,y1=bbox
        if family=='Face':
            # Consistent crop from neutral alpha envelope, never per-pose fit.
            h=y1-y0;cx=(x0+x1)/2;crop=(int(cx-h*.28),int(y0-h*.03),int(cx+h*.28),int(y0+h*.32))
        else:crop=(x0-30,y0-30,x1+30,y1+30)
        for i,(tag,_) in enumerate(selected):
            im=Image.open(out/(tag+'.png')).convert('RGBA').crop(crop)
            im.thumbnail((390,465))
            x=(i%3)*400;y=(i//3)*500
            sheet.paste(im,(x+(400-im.width)//2,y+(465-im.height)//2),im)
            draw.text((x+8,y+475),tag,fill=(0,0,0))
        sheet.save(out/(family+'-sheet.png'))
    after=capture(n)
    unchanged=json_digest(after)==identity['public_snapshot_sha256']
    write_json(out/'verification.json',{'cases':[{'name':tag,'parameters':v} for tag,v in cases],
        'source_snapshot_sha256':identity['public_snapshot_sha256'],
        'serialized_public_state_unchanged':unchanged,'source_saved':False,
        'neutral_restored':True,'visual_acceptance':None})
    if not unchanged:raise ValueError('Reference serialized state changed during pose observation')


if __name__=='__main__':main()
