import argparse
from riglib.shape_controls import apply
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--njc',required=True)
    p.add_argument('--replace-owned',action='store_true')
    a=p.parse_args();apply(a.run,a.njc,a.replace_owned)
