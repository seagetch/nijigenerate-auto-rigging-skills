"""Detect descending, white-overlapping lash branches from PSD alpha.

All analysis uses the eye's measured tangent/normal frame. Part names and
character identities do not select the closure mechanism.
"""
import numpy as np
from PIL import Image
from scipy import ndimage


def thin(mask):
    """Topology-preserving two-subiteration thinning of an 8-connected mask."""
    a = np.pad(mask.astype(bool), 1)
    for _ in range(max(mask.shape)):
        changed = False
        for step in (0, 1):
            p = [a[:-2,1:-1], a[:-2,2:], a[1:-1,2:], a[2:,2:],
                 a[2:,1:-1], a[2:,:-2], a[1:-1,:-2], a[:-2,:-2]]
            neighbors = sum(q.astype(np.uint8) for q in p)
            transitions = sum((~p[k] & p[(k+1)%8]).astype(np.uint8) for k in range(8))
            if step == 0:
                connected = ~(p[0]&p[2]&p[4]) & ~(p[2]&p[4]&p[6])
            else:
                connected = ~(p[0]&p[2]&p[6]) & ~(p[0]&p[4]&p[6])
            remove = a[1:-1,1:-1] & (neighbors >= 2) & (neighbors <= 6) & (transitions == 1) & connected
            if remove.any(): a[1:-1,1:-1][remove] = False; changed = True
        if not changed: break
    return a[1:-1,1:-1]


def detect(materials, groups, origin, basis):
    ids = sorted({u for role in ('upper','corner') for u in groups.get(role,[])})
    if not ids: return None
    source = {}
    resolution = []
    for uid in [*ids, *groups.get('sclera',[])]:
        m = materials[uid]
        with Image.open(m['file']) as im: alpha = np.asarray(im.convert('RGBA'))[:,:,3]
        transform = np.asarray(m['source_to_model'],float)
        resolution.append(np.linalg.svd(transform[:2,:2],compute_uv=False).min())
        y,x = np.nonzero(alpha > 32)
        points = np.c_[x+.5,y+.5]+np.asarray(m['source_bbox'][:2])
        local = (points@transform[:2,:2].T+transform[:2,2]-origin)@basis
        source[uid] = (alpha,transform,np.asarray(m['source_bbox'][:2]),local)
    step = float(min(resolution))
    cloud = np.concatenate([source[u][3] for u in source])
    lo = np.floor(cloud.min(0)/step)*step-2*step
    size = np.ceil((cloud.max(0)-lo)/step).astype(int)+3
    y,x = np.indices(size[::-1]); query = np.c_[x.ravel(),y.ravel()]*step+lo
    world = query@basis.T+origin
    masks = {}
    for uid,(alpha,transform,bbox,_) in source.items():
        pixel = (world-transform[:2,2])@np.linalg.inv(transform[:2,:2]).T-bbox-.5
        masks[uid] = ndimage.map_coordinates(alpha.astype(float),[pixel[:,1],pixel[:,0]],order=1,mode='constant').reshape(size[::-1]) > 32
    lashes = np.logical_or.reduce([masks[u] for u in ids])
    white = np.logical_or.reduce([masks[u] for u in groups['sclera']])
    skeleton = thin(lashes)
    radius = ndimage.distance_transform_edt(lashes)
    points = set(map(tuple,np.argwhere(skeleton)))
    graph = {p:[(p[0]+dy,p[1]+dx) for dy in (-1,0,1) for dx in (-1,0,1)
                if (dy or dx) and (p[0]+dy,p[1]+dx) in points
                and not (dy and dx and ((p[0]+dy,p[1]) in points or (p[0],p[1]+dx) in points))] for p in points}
    stroke_radius=float(np.median(radius[skeleton]))
    paths = []
    for tip in sorted(p for p in points if len(graph[p]) == 1):
        path = [tip]; previous = None; here = tip
        while True:
            following = [p for p in graph[here] if p != previous]
            if len(following) != 1: break
            previous,here = here,following[0]; path.append(here)
        if len(graph[here]) < 3: continue
        end,root = np.array(tip),np.array(here)
        extent = end-root
        length = np.linalg.norm(np.diff(np.asarray(path),axis=0),axis=1).sum()
        # A genuine descending side has more normal than tangent travel and
        # extends beyond the thickness of the upper junction, not a pixel spur.
        if extent[0] <= abs(extent[1]) or length <= 2*max(radius[here],stroke_radius): continue
        paths.append({'pixels':path,'root':here,'hinge':float((here[0]+radius[here])*step+lo[1]),
                      'length':float(length*step)})
    if not paths:
        return {'branches':[], 'classification':'upper_stroke_without_descending_attached_side'}
    labels = np.zeros(lashes.shape,int)
    for index,path in enumerate(paths,1):
        for p in path['pixels'][:-1]: labels[p]=index
    nearest = ndimage.distance_transform_edt(~skeleton,return_distances=False,return_indices=True)
    ownership = labels[tuple(nearest)]
    branches=[]
    for index,path in enumerate(paths,1):
        region=(ownership==index)&lashes
        overlap=int(np.count_nonzero(region&white))
        if not overlap: continue
        below=(y*step+lo[1])>path['hinge']
        # The upper stroke can overlap the side at the junction without
        # containing the descending limb. Follow the limb to its endpoint:
        # only its material owners receive compression. Junction overlap
        # alone must never turn a separate upper Part into a mixed Part.
        tip=path['pixels'][0]
        parts=[uid for uid in ids if masks[uid][tip] and np.any(region&masks[uid]&below)]
        if not parts: continue
        part_modes={}
        for uid in parts:
            extent=np.ptp(source[uid][3],axis=0)
            has_upper=extent[0]>extent[1] and np.any(masks[uid]&skeleton&(labels==0))
            part_modes[str(uid)]='upper_and_side_in_same_part' if has_upper else 'side_component'
        branches.append({'label':index,'hinge':path['hinge'],'length':path['length'],
                         'junction_local':(np.array(path['root'][::-1])*step+lo).tolist(),
                         'white_overlap_pixels':overlap,'parts':parts,'part_modes':part_modes,
                         'junction_overlap_parts':[uid for uid in ids if uid not in parts and np.any(region&masks[uid])],
                         'pixels':int(region.sum())})
    valid={b['label'] for b in branches}
    ownership[~np.isin(ownership,list(valid))]=0
    joined=any('upper_and_side_in_same_part' in b['part_modes'].values() for b in branches)
    classification=('connected_side_within_upper_part' if joined else 'separate_connected_side_part') if branches else 'no_white_overlapping_side'
    return {'branches':branches, 'classification':classification,
            'origin':origin, 'basis':basis, 'raster_origin':lo,'raster_step':step,
            'ownership':ownership, 'materials':source}


def side_compression(detection, uid, world, closure, remaining_height):
    result=np.zeros(len(world))
    if not detection or not detection['branches'] or not closure: return result
    points=(world-detection['origin'])@detection['basis']
    sample=(points-detection['raster_origin'])/detection['raster_step']
    for branch in detection['branches']:
        if uid not in branch['parts']: continue
        field=(detection['ownership']==branch['label']).astype(float)
        weight=ndimage.map_coordinates(field,[sample[:,1],sample[:,0]],order=1,mode='nearest')
        result-=closure*(1-remaining_height)*weight*np.maximum(points[:,1]-branch['hinge'],0.)
    return result


def report(detection):
    if detection is None:
        return {'classification':'no_upper_lash_alpha', 'branches':[]}
    return {'classification':detection['classification'], 'branches':detection['branches']}
