"""A fixed NJC camera shared by source and saved-rig comparisons."""
import numpy as np
from PIL import Image
from .live import created_id
from .data import read_json

NAME='Validation::PSD'


def create(n,root,manifest,observation,pairs,source_directory):
    nodes={v['uuid']:v for v in observation['nodes']};boxes=[]
    for layer,item in pairs:
        if layer['is_group'] or not layer['visible_effective'] or not layer['asset']:continue
        alpha=Image.open(source_directory/layer['asset']['path']).convert('RGBA').getchannel('A');box=alpha.getbbox()
        if not box:continue
        source=np.asarray(layer['bounds'],float);native=np.asarray(nodes[item['uuid']]['bounds']['nominal_world_xy'])
        factor=(native[2:]-native[:2])/np.maximum(source[2:]-source[:2],1)
        boxes.append(np.r_[native[:2]+factor*np.asarray(box[:2]),native[:2]+factor*np.asarray(box[2:])])
    a=np.asarray(boxes);lo=a[:,:2].min(0);hi=a[:,2:].max(0);center=(lo+hi)/2
    scale=max((hi[0]-lo[0])/1920,(hi[1]-lo[1])/1080)*1.3
    uid=created_id(n.call('NodeCommand_AddNode',className='Camera',_suffix='',context={'nodes':[root]}))
    n.call('NodeCommand_SetNodeName',newNames=[NAME],context={'nodes':[uid]})
    for axis,i in [('X',0),('Y',1)]:
        n.call('Inspector_Apply_Translation'+axis,value=float(center[i]),context={'nodes':[uid]})
        n.call('Inspector_Apply_Scale'+axis,value=float(scale),context={'nodes':[uid]})
    return {'uuid':uid,'name':NAME,'data':n.read(uid)['item']['data']}


def capture(n,run,path):
    expected=read_json(run/'render-camera.json')
    if n.read(expected['uuid'])['item']['data']!=expected['data']:raise ValueError('Validation camera changed')
    n.call('FileCommand_ExportPNG',file=str(path),cameraName=expected['name'],transparency=True,postprocessing=False)
