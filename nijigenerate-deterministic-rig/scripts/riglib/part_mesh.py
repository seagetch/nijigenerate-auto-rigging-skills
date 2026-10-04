"""Validate native AutoMesh readback; never generate Part mesh geometry."""
import numpy as np
from .data import json_digest

METHOD='njc AutoMesh; native mesh readback'


def captured_mesh(data):
    mesh=data['mesh'];vertices=np.asarray(mesh['verts'],dtype=float).reshape(-1,2)
    indices=np.asarray(mesh['indices'],dtype=int).reshape(-1,3)
    if len(vertices)<3 or len(indices)<1 or not np.isfinite(vertices).all():
        raise ValueError('Native AutoMesh returned empty or nonfinite geometry')
    if indices.min()<0 or indices.max()>=len(vertices):raise ValueError('Invalid native triangle index')
    a=vertices[indices[:,1]]-vertices[indices[:,0]];b=vertices[indices[:,2]]-vertices[indices[:,0]]
    areas=a[:,0]*b[:,1]-a[:,1]*b[:,0]
    if np.min(abs(areas))<1e-8:raise ValueError('Native AutoMesh returned degenerate triangles')
    # Preserve the native vertex order, triangle order, coordinates and UVs.
    return {'vertices':mesh['verts'],'indices':mesh['indices'],'uvs':mesh['uvs'],'origin':mesh['origin'],'native_mesh_sha256':json_digest(mesh),
            'method':METHOD,'vertex_count':len(vertices),'triangle_count':len(indices),
            'minimum_absolute_triangle_area_twice':float(np.min(abs(areas)))}


def verify_mesh(data,record):
    if record.get('method')!=METHOD:raise ValueError('Part mesh must originate from NJC AutoMesh')
    if data['mesh']['verts']!=record['vertices'] or data['mesh']['indices']!=record['indices']:
        raise ValueError('Live Part geometry differs from recorded AutoMesh output')
    for key in ('uvs','origin'):
        if key in record and data['mesh'][key]!=record[key]:
            raise ValueError('Live Part '+key+' differs from recorded AutoMesh output')
