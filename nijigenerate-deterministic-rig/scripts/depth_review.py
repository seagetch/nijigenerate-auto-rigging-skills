"""Draw stored NJC Grid depth as a wireframe; never modify the live model."""
from pathlib import Path
import argparse
import numpy as np
from PIL import Image,ImageDraw
from riglib.data import read_json


def create(run):
    run=Path(run).resolve();path=run/'native-depth-bake-observed.json'
    if not path.is_file():return
    observed=read_json(path);program=read_json(run/'program.json');state=read_json(run/'native-state.json')
    if observed['program_sha256']!=program['content_sha256']:return
    fixed=observed['fixed_inputs'];root=fixed[str(state['rig_root'])]
    bindings={b['target']:b for b in root['bindings']}
    columns=3;w=520;h=390
    sheet=Image.new('RGB',(columns*w,70+((len(program['domains'])+columns-1)//columns)*h),(24,30,40))
    draw=ImageDraw.Draw(sheet)
    draw.text((15,12),'NJC stored Grid depth / equal model-unit scale on X, Y and Z',fill='white')
    draw.text((15,32),'Static local wireframes; translation centered for display; this is not a posed render or acceptance test.',fill='#b7c6d8')
    yaw,pitch=np.radians([35.,20.])
    projection=np.array([[np.cos(yaw),-np.sin(yaw)*np.sin(pitch)],
                         [0.,np.cos(pitch)],
                         [np.sin(yaw),np.cos(yaw)*np.sin(pitch)]])
    for index,domain in enumerate(program['domains']):
        uid=state['grids'][domain['id']];node=fixed[str(uid)]
        xs=np.asarray(node['grid_axis_x']);ys=np.asarray(node['grid_axis_y']);raw=np.asarray(node['depths'])
        xy=np.array([[x,y] for y in ys for x in xs])
        settings={(s['depthScale'],s['depthOffset']) for s in bindings[uid]['sourceSettings']}
        surfaces=[]
        for scale,offset in sorted(settings):
            z=(raw*scale+offset)*program['native_depth_scale']
            surfaces.append(np.c_[xy,z])
        cloud=np.concatenate(surfaces);center=(cloud.min(0)+cloud.max(0))/2
        projected=[(s-center)@projection for s in surfaces];all2=np.concatenate(projected)
        bounds=np.ptp(all2,axis=0);factor=min((w-45)/max(bounds[0],1e-9),(h-95)/max(bounds[1],1e-9))
        middle=(all2.min(0)+all2.max(0))/2
        x=(index%columns)*w;y=70+(index//columns)*h
        draw.text((x+12,y+5),domain['id'],fill='white')
        for points in projected:
            pixels=((points-middle)*factor+[x+w/2,y+(h-45)/2+18]).reshape(len(ys),len(xs),2)
            for row in pixels:draw.line([tuple(p) for p in row],fill='#75cce3',width=1)
            for row in pixels.transpose(1,0,2):draw.line([tuple(p) for p in row],fill='#75cce3',width=1)
        spans=np.ptp(cloud,axis=0)
        draw.text((x+12,y+h-44),'X / Y / Z span: '+ ' / '.join(f'{v:.2f}' for v in spans),fill='#d3dce8')
        draw.text((x+12,y+h-24),f'Native AutoMesh: {len(xs)} x {len(ys)}; Grid {uid}',fill='#b7c6d8')
    sheet.save(run/'depth-sheet.jpg',quality=90)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);create(p.parse_args().run)
