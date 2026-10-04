import argparse
from riglib.shape_controls import apply,apply_eyes
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--njc',required=True)
    p.add_argument('--replace-owned',action='store_true')
    p.add_argument('--eyes-only',action='store_true',help='Replace only Blink bindings on the already-open saved model')
    a=p.parse_args()
    if a.eyes_only:apply_eyes(a.run,a.njc)
    else:apply(a.run,a.njc,a.replace_owned)
