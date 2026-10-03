"""Compile anatomical containment separately from already-baked bone motion.

All grouping nodes are identity frames. They express support and ownership;
skeletal transforms are baked once into each surface, never inherited twice.
"""
from .data import json_digest
import numpy as np


def compile_hierarchy(domains,evidence):
    groups=[('Body',None),('Pelvis','Body'),('UpperBody','Body'),
            ('Neck','UpperBody'),('Head','Neck'),('Hair','Head'),
            ('Headwear','Head'),('Ears','Head'),('Clothing','Pelvis'),
            ('Tail','Pelvis'),('ChestAttachments','UpperBody'),
            ('PelvisAttachments','Pelvis'),('References',None)]
    for side in ('L','R'):
        groups += [(f'Arm.{side}','UpperBody'),(f'Hand.{side}',f'Arm.{side}'),
                   (f'Leg.{side}','Pelvis'),(f'Foot.{side}',f'Leg.{side}')]
    parent={}
    for d in domains:
        owner=d['owner'];label=d['id'].split('/',1)[1]
        if owner=='head':
            target='Hair' if label.startswith('hair') else ('Ears' if label.startswith('ear') else ('Headwear' if label=='headwear' else 'Head'))
        elif owner=='torso':
            targets={'body':'UpperBody','topwear_front':'UpperBody','topwear_waist':'UpperBody','neck':'Neck','skirt':'Clothing','skirt_back':'Clothing',
                     'apron':'Clothing','tail':'Tail','attachment:chest':'ChestAttachments','attachment:pelvis':'PelvisAttachments'}
            if label.startswith('skirt_back:'):target='Clothing'
            elif label not in targets:raise ValueError('Unsupported torso attachment/hierarchy role: '+label)
            else:target=targets[label]
        else:
            family,tag=owner.split(':');side=evidence['side_mapping'][tag]
            if family=='arm':target=f'Hand.{side}' if label=='hand' else f'Arm.{side}'
            elif family=='leg':target=f'Foot.{side}' if label in ('foot','attachment:ankle') else f'Leg.{side}'
            else:raise ValueError('Unsupported anatomical hierarchy owner')
        parent[d['id']]=target
    result={'schema_version':'rig-anatomical-hierarchy/1',
            'groups':[{'id':name,'parent':parent_id} for name,parent_id in groups],
            'surface_parents':parent,'transform_policy':'identity grouping; bone motion baked into each surface exactly once'}
    result['content_sha256']=json_digest(result)
    return result


def validate_hierarchy(client,state,program):
    parents={};nodes={}
    def visit(node,parent=None):
        if node['typeId'] in ('Parameter','Binding'):return
        nodes[node['uuid']]=node;parents[node['uuid']]=parent
        for child in node.get('children') or []:visit(child,node['uuid'])
    for node in client.find('*')['items']:visit(node)
    spec=program['hierarchy'];groups=state['groups'];root=program['source_root']
    bindings={b['target']:b for b in client.read(state['rig_root'])['item']['data']['bindings']}
    for group in spec['groups']:
        uid=groups[group['id']];expected=groups[group['parent']] if group['parent'] else root
        if parents.get(uid)!=expected:raise ValueError('Anatomical group parent mismatch: '+group['id'])
        data=client.read(uid)['item']['data'];t=data['transform']
        if t['trans']!=[0,0,0] or t['rot']!=[0,0,0] or t['scale']!=[1,1] or data.get('zsort',0)!=0:
            raise ValueError('Grouping node would add an unintended transform/draw offset')
    for d in program['domains']:
        uid=state['grids'][d['id']]
        if parents.get(uid)!=groups[spec['surface_parents'][d['id']]]:raise ValueError('Surface anatomical owner mismatch')
        for part in d['parts']:
            if parents.get(part['uuid'])!=uid:raise ValueError('Part escaped its compiled surface')
        data=client.read(uid)['item']['data']
        carrier=d['carrier_frame'];transform=data['transform']
        if not np.allclose(transform['trans'][:2],carrier['origin'],atol=.001) or not np.allclose(transform['rot'],[0,0,carrier['rotation']],atol=1e-6):
            raise ValueError('Surface anatomical carrier frame mismatch: '+d['id'])
        if set(bindings[uid]['sourceBoneUuids'])!={state['bones'][name] for name in d['bone_sources']}:
            raise ValueError('Surface has incorrect anatomical driving bones: '+d['id'])
        # DepthRig source identity is independently checked by build_native.
        if data.get('type')!='GridDeformer':raise ValueError('Missing compiled material surface')
    return {'passed':True,'group_count':len(groups),'surface_count':len(program['domains']),
            'hierarchy_sha256':spec['content_sha256'],'all_parts_have_compiled_surface_parent':True,
            'identity_group_transforms_verified':True,'surface_bone_sources_verified':True}
