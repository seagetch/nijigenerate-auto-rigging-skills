"""Identify backdrop rasters whose geometry contradicts a head-part name."""
import numpy as np
from PIL import Image


def classify(run,materials):
    active=[m for m in materials if m['active']]
    faces=[m['cloud'] for m in active if m['role']=='face']
    feet=[m['cloud'] for m in active if m['role']=='foot']
    result={m['part']:{'reason':'explicit PSD background role'} for m in active if m['role']=='background'}
    if not faces or not feet:return result
    face=np.concatenate(faces);foot=np.concatenate(feet)
    face_span=np.ptp(face,axis=0);body_height=float(foot[:,1].max()-face[:,1].min())
    for m in active:
        if m['role']!='ear':continue
        q=m['cloud'];span=np.ptp(q,axis=0)
        if not (span[0]>4*face_span[0] and span[1]>.85*body_height and q[:,1].max()>=np.median(foot[:,1])):continue
        a=np.asarray(Image.open(run/m['layer']['asset']['path']).convert('RGBA'))[:,:,3]
        band=max(1,int(min(a.shape)*.04))
        strips=[a[:band],a[-band:],a[:,:band],a[:,-band:]]
        coverage=sum(int(np.count_nonzero(s>32)) for s in strips)/sum(s.size for s in strips)
        if coverage<.65:continue
        result[m['part']]={'reason':'ear-name candidate is a full-body backdrop with a broad opaque perimeter',
            'width_in_face_widths':float(span[0]/face_span[0]),'height_in_body_heights':float(span[1]/body_height),
            'opaque_perimeter_coverage':coverage,'motion':'retain source render hierarchy; exclude from anatomical and deforming supports'}
    return result
