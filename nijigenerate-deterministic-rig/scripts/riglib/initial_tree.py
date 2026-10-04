"""Place the compiled material tree once, before any animation bindings."""
import math
import numpy as np
from .carrier import rotation
from .live import created_id


class InitialTree:
    def __init__(self,n,program,state):
        self.n=n;self.program=program;self.state=state
        self.spec=program['hierarchy'];self.source=self.spec['source_nodes']
        self.world={int(u):np.array(row['matrix'],float) for u,row in self.source.items()}
        self.z={int(u):row['zsort'] for u,row in self.source.items()}
        self.parents={int(u):row['parent'] for u,row in self.source.items()}

    def resolve(self,ref):return ref['node'] if 'node' in ref else self.state['groups'][ref['group']]

    def place(self,uid,parent,world=None,zsort=None,move=True):
        world=self.world[uid] if world is None else np.array(world,float)
        zsort=self.z[uid] if zsort is None else zsort
        if move:self.n.call('NodeCommand_MoveNode',newParent=parent,index=0,context={'nodes':[uid]})
        local=np.linalg.solve(self.world[parent],world);scale=np.linalg.norm(local[:2,:2],axis=0)
        angle=math.atan2(local[1,0],local[0,0])
        if not np.allclose(local[:2,:2],rotation(angle)@np.diag(scale),atol=1e-6):raise ValueError('Initial parent placement requires affine shear')
        self.n.call('Inspector_Apply_LockToRoot',value=False,context={'nodes':[uid]})
        for axis,value in zip('XYZ',local[:3,3]):self.n.call('Inspector_Apply_Translation'+axis,value=float(value),context={'nodes':[uid]})
        self.n.call('Inspector_Apply_RotationZ',value=angle,context={'nodes':[uid]})
        for axis,value in zip('XY',scale):self.n.call('Inspector_Apply_Scale'+axis,value=float(value),context={'nodes':[uid]})
        self.n.call('Inspector_Apply_ZSort',value=float(zsort-self.z[parent]),context={'nodes':[uid]})
        self.world[uid]=world;self.z[uid]=zsort;self.parents[uid]=parent

    def prepare_units(self,domain):
        # DynamicComposite is a deformation endpoint. An origin Part hosting
        # downstream anatomy must sit behind a propagating Composite instead.
        # Conversion preserves its native blend/masks and existing UUID.
        hosted={g['parent'].get('node') for g in self.spec['groups']}
        hosted.update(r.get('node') for r in self.spec['surface_parents'].values())
        hosted.add(self.spec['face_origin'])
        for unit in domain['render_units']:
            if self.source[str(unit)]['type']!='DynamicComposite':continue
            contains=False
            for origin in hosted:
                cursor=origin
                while cursor is not None and str(cursor) in self.source:
                    if cursor==unit:contains=True;break
                    cursor=self.source[str(cursor)]['parent']
            if not contains:continue
            before=self.n.read(unit)['item']['data']
            self.n.call('Node_ConvertTo_Composite',context={'nodes':[unit]})
            after=self.n.read(unit)['item']['data']
            if after['uuid']!=unit or after['type']!='Composite' or not after.get('propagate_meshgroup'):
                raise ValueError('Origin composite did not preserve identity and propagate deformation')
            for key in ('blend_mode','opacity','masks'):
                if before.get(key)!=after.get(key):raise ValueError('Origin composite conversion changed '+key)
            self.state.setdefault('origin_composites',[]).append(unit)

    def set_carrier(self,gid,domain,parent):
        world=np.eye(4);world[:2,:2]=rotation(domain['carrier_frame']['rotation']);world[:2,3]=domain['carrier_frame']['origin']
        self.place(gid,parent,world,self.z[parent],move=False)
        for unit in domain['render_units']:self.place(unit,gid)

    def assemble(self):
        # All grids and their intact rendering units exist now. This is still
        # initial construction: no parameters, depth bake or correction exists.
        for group in self.spec['groups']:
            parent=self.resolve(group['parent'])
            uid=created_id(self.n.call('NodeCommand_AddNode',className='Node',_suffix='::Origin',context={'nodes':[parent]}))
            self.n.call('NodeCommand_SetNodeName',newNames=[group['id']],context={'nodes':[uid]})
            world=np.eye(4);world[:2,3]=group['origin']
            self.place(uid,parent,world,0.,move=False);self.state['groups'][group['id']]=uid
        for d in self.program['domains']:
            self.place(self.state['grids'][d['id']],self.resolve(self.spec['surface_parents'][d['id']]))
        for uid,receiver in self.spec['clipping_receivers'].items():self.place(int(uid),receiver)
        face=self.spec['face_origin']
        if face is not None:
            d=next(d for d in self.program['domains'] if d['semantic_chart']=='head/face')
            grid=self.state['grids'][d['id']]
            # Gather every off-path facial branch beneath the origin Part,
            # including branches inside an intact source compositing unit.
            cursor=face;branches=[]
            while cursor!=grid:
                parent=self.parents[cursor]
                branches.extend(u for u,p in self.parents.items() if p==parent and u!=cursor)
                cursor=parent
            for branch in branches:self.place(branch,face)
        self.state['structure_version']=2
        self.state['origin_bones']={self.state['groups'][g['id']]:self.state['bones'][g['bone']] for g in self.spec['groups']}
