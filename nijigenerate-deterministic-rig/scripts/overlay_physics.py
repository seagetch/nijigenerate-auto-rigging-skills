"""Show spring-pendulum support and actual authored mesh endpoint fields."""
import argparse
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageChops
from riglib.data import read_json,write_json
from riglib.physics_fields import frame


def arrow(draw,a,b,colour,width=2):
    a=np.asarray(a);b=np.asarray(b);v=b-a;length=np.linalg.norm(v)
    draw.line([tuple(a),tuple(b)],fill=colour,width=width)
    if length>1:
        v/=length;n=np.array([-v[1],v[0]])
        draw.polygon([tuple(b),tuple(b-v*8+n*4),tuple(b-v*8-n*4)],fill=colour)


def overlay_plan(n,plan,assets,out,nodes=None,transforms=None):
    from apply_physics import census,matrices,sample_authored_host
    from verify_physics import capture
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    groups=plan['groups'];targets=[g['target'] for g in groups]
    n.call('ViewportCommand_ResetParameters');n.call('ViewportCommand_FitViewportToModel')
    if nodes is None:
        nodes,parents=census(n);transforms=matrices(nodes,parents)
    capture(n,out/'physics-overlay-neutral.png')
    base=Image.open(out/'physics-overlay-neutral.png').convert('RGBA');overview=base.copy();draw=ImageDraw.Draw(overview)
    ledger=[]
    for index,g in enumerate(groups):
        uid=g['target'];data=nodes[uid];v=np.asarray(data['mesh']['verts']).reshape(-1,2)
        n.call('ViewCommand_CaptureLiveScreenshot',overlayObjects=[{'uuid':uid,'overlay':'mesh'}])
        meta=n.last_envelope['result'].get('_meta',{})
        mappings={int(r['uuid']):r for r in meta['overlayMappings']}
        p=v@transforms[uid][:2,:2].T+transforms[uid][:2,2]
        row=mappings[uid];image=np.asarray([q['image'] for q in row['points']])
        if len(image)!=len(p):raise ValueError('Overlay vertex correspondence differs')
        # This capture's homologous rest mesh calibrates the overlay; no affine
        # from a prior viewport is reused. Residual is recorded and bounded.
        affine=np.linalg.lstsq(np.c_[p,np.ones(len(p))],image,rcond=None)[0]
        residual=float(np.linalg.norm(np.c_[p,np.ones(len(p))]@affine-image,axis=1).max())
        if residual>.5:raise ValueError('Neutral overlay projection is not affine')
        def screen(q):return np.r_[q,1]@affine
        a=screen(g['fixed']);b=screen(g['free'])
        draw.line([tuple(a),tuple(b)],fill='#00e5ff',width=2)
        draw.ellipse((a[0]-4,a[1]-4,a[0]+4,a[1]+4),fill='#00e5ff')
        draw.text(tuple(b),str(index+1),fill='#ffd166',stroke_width=1,stroke_fill='black')
        mask=Image.new('RGBA',base.size);ld=ImageDraw.Draw(mask)
        all_values=[np.asarray(o['values']).reshape(-1,2) for o in g['operations'] if o['target']==uid]
        fixed=np.max(abs(np.stack(all_values)),axis=(0,2))<=1e-7
        for face in np.asarray(data['mesh']['indices']).reshape(-1,3):
            ld.polygon([tuple(image[q]) for q in face],fill=(0,170,255,75) if fixed[face].all() else (255,160,50,60))
        # Clip diagnostic face colours to the actual source alpha when the
        # preserved source UVs establish an affine homologous correspondence.
        # This is display masking only, never colour-based classification.
        rgba=assets[uid]['rgba'];uv=np.asarray(data['mesh']['uvs']).reshape(-1,2)
        source_pixels=uv*np.array([rgba.shape[1],rgba.shape[0]])
        uv_affine=np.linalg.lstsq(np.c_[source_pixels,np.ones(len(uv))],image,rcond=None)[0]
        uv_residual=float(np.linalg.norm(np.c_[source_pixels,np.ones(len(uv))]@uv_affine-image,axis=1).max())
        alpha_clipped=False
        if uv_residual<=.5 and abs(np.linalg.det(uv_affine[:2]))>1e-9:
            projection=np.eye(3);projection[:2,:]=uv_affine.T
            inverse=np.linalg.inv(projection)
            alpha=Image.fromarray(rgba[:,:,3]).transform(base.size,Image.Transform.AFFINE,
                tuple(inverse[:2].reshape(-1)),resample=Image.Resampling.BILINEAR)
            mask.putalpha(ImageChops.multiply(mask.getchannel('A'),alpha));alpha_clipped=True
        # Dense masks are shown with a consistent translucent blue legend.
        layer=Image.alpha_composite(base,mask)
        ld=ImageDraw.Draw(layer)
        if g.get('limb'):
            limb=g['limb'];j=[screen(q) for q in limb['joints']]
            ld.line([tuple(q) for q in j],fill='#47a9ff',width=3)
            for q in j:ld.ellipse((q[0]-4,q[1]-4,q[0]+4,q[1]+4),outline='#47a9ff',width=2)
        cloud=assets[uid]['points'];o,t,normal,length=frame(g['fixed'],g['free']);s=(cloud-o)@normal/length
        cord=[]
        for lo,hi in zip(np.linspace(0,1,9)[:-1],np.linspace(0,1,9)[1:]):
            selected=cloud[(s>=lo)&(s<=hi)]
            if len(selected):cord.append(np.median(selected,axis=0))
        cord=np.asarray(cord)
        if len(cord)<2:cord=np.array([g['fixed'],g['free']])
        poses=[]
        for key,colour in [((-1,0),'#ff6577'),((1,0),'#ffad66'),((0,-1),'#b695ff'),((0,1),'#80e0a8')]:
            delta=np.array([sample_authored_host(g,key,q,nodes,transforms) for q in cord])
            curve=np.c_[cord+delta,np.ones(len(cord))]@affine
            ld.line([tuple(q) for q in curve],fill=colour,width=2)
            moved=int(np.argmax(np.linalg.norm(delta,axis=1)))
            arrow(ld,screen(cord[moved]),curve[moved],colour)
            poses.append({'key':list(key),'curve_model_xy':(cord+delta).tolist()})
        neutral=np.c_[cord,np.ones(len(cord))]@affine;ld.line([tuple(q) for q in neutral],fill='#ffe066',width=3)
        ld.ellipse((a[0]-5,a[1]-5,a[0]+5,a[1]+5),fill='#00e5ff')
        arrow(ld,a,b,'#00e5ff')
        if g['pattern']=='two_ends':
            ld.ellipse((b[0]-5,b[1]-5,b[0]+5,b[1]+5),fill='#47a9ff')
            spring_end=screen((np.asarray(g['fixed'])+g['free'])*.5)
        else:spring_end=b
        # A compact zigzag identifies the solver spring, separate from the
        # authored material curve. Pendulum angle and spring length both vary.
        vv=spring_end-a;nn=np.array([-vv[1],vv[0]])/max(np.linalg.norm(vv),1)
        zig=[a+vv*f+nn*(3 if k%2 else -3) for k,f in enumerate(np.linspace(.2,.7,10))]
        ld.line([tuple(q) for q in zig],fill='#ffffff',width=1)
        spread=np.vstack([image,a,b,*[np.c_[np.asarray(q['curve_model_xy']),np.ones(len(cord))]@affine for q in poses]])
        mn=np.maximum(np.floor(spread.min(axis=0)-30),[0,0]).astype(int)
        mx=np.minimum(np.ceil(spread.max(axis=0)+30),base.size).astype(int)
        crop=layer.crop(tuple(np.r_[mn,mx])).convert('RGB')
        scale=min(720/crop.width,650/crop.height)
        crop=crop.resize((max(1,round(crop.width*scale)),max(1,round(crop.height*scale))),Image.Resampling.LANCZOS)
        canvas=Image.new('RGB',(max(720,crop.width),crop.height+130),'#20252d')
        canvas.paste(crop,((canvas.width-crop.width)//2,0));cd=ImageDraw.Draw(canvas)
        support='two fixed ends, flexible middle' if g['pattern']=='two_ends' else 'fixed root, free tip'
        text=[f'{index+1}. {data["name"]} | SpringPendulum / XY',
              f'{support} | Length {g["length"]:.1f} | Frequency {plan["policy"]["profiles"][g["profile"]]["frequency"]:.2f}',
              'orange: moving mesh / blue: fixed mesh / cyan: support span / yellow: neutral',
              'red/orange: X -/+ / purple/green: Y -/+ | curves: authored keys, not runtime trajectory',
              'host: '+g.get('support_group','anatomical skeleton')]
        for k,line in enumerate(text):cd.text((10,crop.height+8+k*22),line,fill='white')
        path=out/f'physics-overlay-{index+1:02d}-{uid}.png';canvas.save(path)
        ledger.append({'index':index+1,'name':data['name'],'target':uid,'solver':'SpringPendulum','map_mode':'XY',
                       'pattern':g['pattern'],'fixed':g['fixed'],'free':g['free'],'frame':g['frame'],
                       'support_group':g.get('support_group'),'projection_residual_px':residual,
                       'endpoint_curves':poses,'image':str(path),'moving_mesh_vertices':int(np.count_nonzero(~fixed)),
                       'fixed_mesh_vertices':int(np.count_nonzero(fixed))})
        ledger[-1].update(source_alpha_clipped=alpha_clipped,source_uv_projection_residual_px=uv_residual)
    table=Image.new('RGB',(overview.width+490,max(overview.height,len(groups)*22+85)),'#20252d')
    table.paste(overview,(0,0),overview);td=ImageDraw.Draw(table)
    td.text((overview.width+10,10),'SpringPendulum / XY | anatomy is protected',fill='white')
    for i,g in enumerate(groups):
        td.text((overview.width+10,40+i*22),f'{i+1:02d} {nodes[g["target"]]["name"]} | {g["pattern"]}',fill='white')
    table.save(out/'physics-overlay-overview.png');write_json(out/'physics-overlay.json',{'groups':ledger,'evidence':'Actual rest capture and generated endpoint bindings; not a simulated trajectory'})
    return ledger


if __name__=='__main__':
    from riglib.live import Live
    from riglib.physics_structure import psd_materials
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--out',required=True);p.add_argument('--njc',required=True)
    args=p.parse_args();run=Path(args.run);dest=Path(args.out);n=Live(args.njc)
    authored=read_json(dest/'physics-authored.json')
    assets=psd_materials(run,read_json(run/'evidence.json'))
    overlay_plan(n,read_json(dest/'physics-program.json'),assets,dest)
