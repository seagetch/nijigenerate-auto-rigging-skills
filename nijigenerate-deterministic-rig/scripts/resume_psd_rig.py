"""Compatibility entry: validation always starts from the PSD, never a saved rig."""
import argparse
from run_psd_rig import run

def resume(psd,out,njc,render_images=False):return run(psd,out,njc,render_images=render_images)

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('psd','out','njc'):p.add_argument('--'+name,required=True)
    p.add_argument('--render-images',action='store_true')
    a=p.parse_args();resume(a.psd,a.out,a.njc,a.render_images)
