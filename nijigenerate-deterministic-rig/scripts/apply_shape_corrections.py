"""Apply PSD-derived cheek Part corrections after native depth angle baking."""
import argparse
from riglib.cheek_correction import apply

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', required=True); parser.add_argument('--njc', required=True)
    args = parser.parse_args(); apply(args.run, args.njc)
