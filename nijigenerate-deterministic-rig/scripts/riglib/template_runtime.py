"""Execute the registered deterministic-rig templates without shape fallbacks.

This is the shared runtime for fitting, depth, and pose corrections. Source
landmarks and material membership are inputs, never template or code constants.
"""
from pathlib import Path
import numpy as np
from .data import read_json,load_template,digest,json_digest,parameters
from .geometry import fit_guide_grid,validate_grid,inverse_grid,evaluate_depth,apply_local_corrections


class TemplateCatalog:
    def __init__(self,directory):
        self.directory=Path(directory).resolve(strict=True)
        self.manifest=read_json(self.directory/'manifest.json')
        self.entries={r['id']:r for r in self.manifest['templates']}
        if len(self.entries)!=len(self.manifest['templates']):raise ValueError('Duplicate template IDs')
        self.templates={}
        for name,entry in self.entries.items():
            path=self.directory/entry['file']
            if path.parent.resolve()!=self.directory:raise ValueError('Template path escapes catalog')
            actual=digest(path)
            if actual!=entry['sha256']:raise ValueError('Template hash mismatch: '+name)
            template=load_template(path)
            if template['id']!=name:raise ValueError('Template identity mismatch: '+name)
            if sorted(set(o['type'] for o in template['geometry']['operators']))!=sorted(entry['operators']):
                raise ValueError('Manifest operator mismatch: '+name)
            self.templates[name]=template

    def get(self,name):
        if name not in self.templates:raise ValueError('Unregistered template: '+str(name))
        return self.templates[name]


def fit_template_chart(catalog,spec):
    template=catalog.get(spec['template'])
    declared={p['id']:p for p in template['landmarks']}
    observed=spec['landmarks']
    missing=[name for name,p in declared.items() if p.get('required') and name not in observed]
    if missing:raise ValueError(f"{spec['id']}: missing semantic landmarks {missing}")
    if set(observed)-set(declared):raise ValueError('Unknown semantic landmark')
    records=[]
    for name,entry in observed.items():
        if entry.get('provenance') not in ('measured','visual_estimate','source_annotation','prior'):
            raise ValueError('Every landmark needs explicit provenance')
        records.append({'id':name,'uv':declared[name]['uv'],'xy':entry['xy']})
    # Coverage constraints are separate from semantic landmarks. They may add
    # boundary support but never overwrite a landmark's material coordinate.
    records.extend(spec.get('coverage_constraints',[]))
    u=[x['u'] for x in template['guide_grid']['columns']]
    v=[x['v'] for x in template['guide_grid']['rows']]
    control=fit_guide_grid(u,v,spec['anatomical_bounds'],records)
    grid_check=validate_grid(control)
    values=parameters(template,spec.get('parameters'))
    frame=np.asarray(spec['chart_to_model'],float)
    if frame.shape!=(3,3) or not np.allclose(frame[2],[0,0,1]):raise ValueError('Invalid chart frame')
    gram=frame[:2,:2].T@frame[:2,:2]
    if not np.allclose(gram,np.eye(2),atol=1e-6) or np.linalg.det(frame[:2,:2])<=0:
        raise ValueError('Chart frame must preserve orientation and model length units')
    scale=float(spec['anatomical_bounds'][2]-spec['anatomical_bounds'][0])
    if scale<=0:raise ValueError('Invalid anatomical depth scale')
    result={'schema_version':'rig-template-chart/1','id':spec['id'],
            'template_id':template['id'],'template_sha256':catalog.entries[template['id']]['sha256'],
            'template':template,'parameters':values,'depth_scale':scale,
            'control':{'u_lines':u,'v_lines':v,'xy':control.tolist()},
            'chart_to_model':frame.tolist(),'landmarks':observed,
            'fit_validation':grid_check,'source_specification_sha256':json_digest(spec),
            'host':spec.get('host'),'depth_orientation':spec.get('depth_orientation',1),
            'depth_origin':spec.get('depth_origin',0),
            'carrier_extension':spec.get('carrier_extension','reject')}
    result['content_sha256']=json_digest(result)
    return result


def _inverse_with_extension(chart,points):
    """Register chart points; declared carrier continuation is fully reported.

    Semantic/opaque coverage is checked separately by the compiler. Extending
    transparent rectangular carrier corners must not add anatomical landmarks
    or replace the template field inside its fitted domain.
    """
    c=chart['control'];grid=np.asarray(c['xy']);u=np.asarray(c['u_lines']);v=np.asarray(c['v_lines'])
    # Boundary continuation uses the nearest boundary segment's UV. It is only
    # enabled by an explicit source specification and returns an outside flag.
    result=np.empty((len(points),2));outside=np.zeros(len(points),bool)
    for k,point in enumerate(points):
        try:result[k]=inverse_grid(grid,u,v,[point])[0]
        except ValueError as error:
            if chart['carrier_extension']!='transparent_boundary_continuation' or 'lies outside fitted grid' not in str(error):raise
            candidates=[]
            for side in ('top','bottom','left','right'):
                if side in ('top','bottom'):
                    yy=0 if side=='top' else -1;line=grid[yy];coords=np.c_[u,np.full(len(u),0 if yy==0 else 1)]
                else:
                    xx=0 if side=='left' else -1;line=grid[:,xx];coords=np.c_[np.full(len(v),0 if xx==0 else 1),v]
                for a,b,ua,ub in zip(line[:-1],line[1:],coords[:-1],coords[1:]):
                    t=np.clip(np.dot(point-a,b-a)/np.dot(b-a,b-a),0,1)
                    candidates.append((float(np.linalg.norm(point-a-t*(b-a))),ua+t*(ub-ua)))
            result[k]=min(candidates,key=lambda x:x[0])[1];outside[k]=True
    return result,outside


class TemplateScene:
    def __init__(self,catalog,specs):
        self.catalog=catalog
        self.charts={}
        self.specs={s['id']:s for s in specs}
        if len(self.specs)!=len(specs):raise ValueError('Duplicate chart ID')
        active=set()
        def visit(name):
            if name in self.charts:return
            if name in active:raise ValueError('Cyclic host relationship')
            if name not in self.specs:raise ValueError('Unknown host '+name)
            active.add(name);spec=self.specs[name]
            if spec.get('host'):visit(spec['host'])
            self.charts[name]=fit_template_chart(catalog,spec);active.remove(name)
        for name in sorted(self.specs):visit(name)

    def sample(self,name,model_xy,*,opaque=False):
        chart=self.charts[name]
        model=np.asarray(model_xy,float);frame=np.asarray(chart['chart_to_model'])
        local=(model-frame[:2,2])@frame[:2,:2]
        uv,outside=_inverse_with_extension(chart,local)
        if opaque and outside.any():raise ValueError(f'{name}: {outside.sum()} opaque samples outside fitted template chart')
        operators=chart['template']['geometry']['operators']
        scale=chart['depth_scale'];host=None
        if any(op['type']=='host_offset' for op in operators):
            if not chart['host']:raise ValueError('Host-dependent template lacks host')
            host=self.sample(chart['host'],model,opaque=opaque)['depth']/scale
        depth=evaluate_depth(uv,operators,chart['parameters'],host_depth=host)*scale
        if chart['template']['geometry']['depth_mode']=='residual':
            if not chart['host']:raise ValueError('Residual template requires a registered host')
            depth+=self.sample(chart['host'],model,opaque=opaque)['depth']
        depth=depth*chart['depth_orientation']+chart['depth_origin']
        return {'uv':uv,'depth':depth,'outside':outside,'template_id':chart['template_id'],
                'template_sha256':chart['template_sha256'],'operator_count':len(operators)}

    def correction(self,name,model_xy,pose):
        chart=self.charts[name];frame=np.asarray(chart['chart_to_model'])
        sampled=self.sample(name,model_xy)
        local=(np.asarray(model_xy)-frame[:2,2])@frame[:2,:2]
        result=apply_local_corrections(local,sampled['uv'],pose,chart['template']['correction_rules'],chart['parameters'],scale=chart['depth_scale'])
        return (result-local)@frame[:2,:2].T

    def report(self):
        return {'schema_version':'rig-template-scene/1','charts':self.charts,
                'catalog_sha256':json_digest(self.catalog.manifest),
                'no_shape_fallback':True}
