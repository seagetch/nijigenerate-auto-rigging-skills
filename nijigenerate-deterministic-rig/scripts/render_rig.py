"""Inspect and render the expected live rig exclusively through NJC."""
import argparse
from pathlib import Path
from PIL import Image, ImageDraw
from riglib.data import read_json,write_json
from riglib.live import Live
from riglib.model import read_model_metadata
from build_native import require_single_rig
import numpy as np


def inspect_live(client):
    data,source=read_model_metadata(client=client,require_parameters=False)
    nodes={}
    def visit(node):
        nodes[node['uuid']]=node
        for c in node.get('children',[]):visit(c)
    visit(data['nodes'])
    stats={}
    resources=client.binding_resources()
    for resource in resources:
        uri=resource.get('uri','')
        if not uri.startswith('resource://nijigenerate/bindings/get?'):continue
        item=client.invoke(['resources','read',uri]).get('item')
        if not isinstance(item,dict):raise ValueError('NJC binding resource is missing')
        parameter=item['parameter']
        record=stats.setdefault(parameter['uuid'],{'name':parameter['name'],'grid_bindings':[]})
        if item['name']=='deform':
            binding=item['data']
            node=nodes.get(item['target']['uuid'])
            if not node or node['type']!='GridDeformer':continue
            xs=node['grid_axis_x'];ys=node['grid_axis_y']
            if len(xs)<2 or len(ys)<2 or min(np.diff(xs))<=0 or min(np.diff(ys))<=0:
                raise ValueError('Invalid NJC Grid axes')
            base=np.array([[x,y] for y in ys for x in xs]).reshape(len(ys),len(xs),2)
            minimum=None;neutral_max=None;committed=0
            for i,col in enumerate(binding['values']):
                for j,values in enumerate(col):
                    if not binding['isSet'][i][j]:continue
                    off=np.asarray(values).reshape(base.shape)
                    if not np.isfinite(off).all():raise ValueError('NJC returned non-finite binding values')
                    q=base+off
                    dx=q[:-1,1:]-q[:-1,:-1];dy=q[1:,:-1]-q[:-1,:-1]
                    dx2=q[1:,1:]-q[1:,:-1];dy2=q[1:,1:]-q[:-1,1:]
                    denom=np.diff(ys)[:,None]*np.diff(xs)[None,:]
                    ratio=np.stack([(a[:,:,0]*b[:,:,1]-a[:,:,1]*b[:,:,0])/denom
                                    for a,b in ((dx,dy),(dx2,dy2),(dx,dy2),(dx2,dy))])
                    committed+=1
                    minimum=float(ratio.min()) if minimum is None else min(minimum,float(ratio.min()))
                    if abs(item['axisValues'][0][i])<1e-6 and abs(item['axisValues'][1][j])<1e-6:
                        neutral_max=float(abs(off).max())
            record['grid_bindings'].append({'target':node['name'],'minimum_cell_area_ratio':minimum,
                                           'neutral_max_offset':neutral_max,'committed_keys':committed,
                                           'neutral_key_observed':neutral_max is not None})
    return {'source':source,'node_count':len(nodes),'parameter_count':source['parameter_count_observed'],
            'parameters':list(stats.values()),'scope':'live NJC nodes and exposed binding grids',
            'saved_file_verified':False,'complete_parameter_properties_verified':False}


def render(n,state,destination):
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    n.call('ViewportCommand_ResetParameters')
    n.call('ViewportCommand_FitViewportToModel')
    cases=[('neutral',{})]
    for name in ['Face::Yaw-Pitch','Body::Yaw-Pitch']:
        for tag,value in [('left',[-1,0]),('right',[1,0]),('up',[0,-1]),('down',[0,1]),('diagonal',[1,1]),('middle',[.5,.5])]:
            cases.append((name.split('::')[0]+'-'+tag,{name:value}))
    cases += [('combined',{'Face::Yaw-Pitch':[-1,.5],'Body::Yaw-Pitch':[.5,-.5],'Body::Roll':[.5]})]
    for name in state['parameters']:
        if name.startswith(('Arm::','Elbow::','Leg::','Knee::')):cases.append((name.replace('::','-'),{name:[1]}))
    for label,values in cases:
        n.call('ViewportCommand_ResetParameters')
        for name,value in values.items():
            n.call('ParameditCommand_SetParameterKeypoint',context={'parameters':[state['parameters'][name]],'parameterValue':value})
        n.call('ViewCommand_SaveScreenshot',filename=str((destination/(label+'.png')).resolve()))
        print('Rendered '+label,flush=True)
    n.call('ViewportCommand_ResetParameters')
    for family in ('Face','Body'):
        names=['neutral']+[family+'-'+x for x in ['left','right','up','down','diagonal','middle']]+['combined']
        sheet=Image.new('RGB',(4*400,2*480),(35,35,35));draw=ImageDraw.Draw(sheet)
        for k,label in enumerate(names):
            im=Image.open(destination/(label+'.png')).convert('RGBA')
            if family=='Face':
                # Fixed crop derived once from this actual neutral render's alpha bounds.
                neutral=Image.open(destination/'neutral.png').convert('RGBA')
                bbox=neutral.getchannel('A').getbbox()
                if bbox:
                    x0,y0,x1,y1=bbox;cy=y0+(y1-y0)*.1;cx=(x0+x1)/2
                    size=(y1-y0)*.27
                    im=im.crop((int(cx-size),int(cy-size*.45),int(cx+size),int(cy+size*1.25)))
            im.thumbnail((400,450));tile=Image.new('RGB',(400,450),(50,50,50));tile.paste(im,((400-im.width)//2,(450-im.height)//2),im)
            x=(k%4)*400;y=(k//4)*480
            sheet.paste(tile,(x,y));draw.text((x+8,y+454),label,fill='white')
        sheet.save(destination/(family+'-sheet.jpg'))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--state',required=True);p.add_argument('--njc',required=True);p.add_argument('--out',required=True)
    a=p.parse_args();s=read_json(a.state)
    n=Live(a.njc,Path(a.out)/'journal')
    require_single_rig(n,s['rig_root'],s['bones'].values())
    report=inspect_live(n);write_json(Path(a.out)/'live-inspection.json',report)
    render(n,s,a.out)
