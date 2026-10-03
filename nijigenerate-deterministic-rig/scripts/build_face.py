"""Compatibility entry point for the common reference facial-control builder."""
import argparse
from pathlib import Path
import numpy as np


def frame(points):
    a,b=np.asarray(points,float);u=b-a;u=u/np.linalg.norm(u)
    return a,np.column_stack((u,[-u[1],u[0]]))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('capture','observation','evidence','state','njc','journal'):p.add_argument('--'+name,required=True)
    a=p.parse_args();run=Path(a.state).resolve().parent
    for name in ('capture','observation','evidence'):
        if Path(getattr(a,name)).resolve()!=run/(name+'.json'):
            raise ValueError('Facial controls must use the same PSD-derived run intermediates')
    from apply_facial_controls import apply
    apply(run,a.njc)
