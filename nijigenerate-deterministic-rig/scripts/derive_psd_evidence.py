"""PSD-derived semantic, region and mechanism observations."""
import argparse
from pathlib import Path
from riglib.psd_evidence import derive

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--run',required=True)
    args=parser.parse_args()
    derive(args.run,Path(__file__).resolve().parents[1])
