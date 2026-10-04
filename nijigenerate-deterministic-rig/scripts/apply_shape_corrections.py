"""Apply PSD-derived cheek Part corrections after native depth angle baking."""
import argparse
from riglib.cheek_correction import apply

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', required=True); parser.add_argument('--njc', required=True)
    parser.add_argument('--single-feature-check', action='store_true',
                        help='Explicitly check only owned cheek corrections on the current existing INX; no import/open')
    parser.add_argument('--contour-only', action='store_true', help='Draw vector contour overlays and differences, without PNG captures')
    args = parser.parse_args(); apply(args.run, args.njc, single_feature_check=args.single_feature_check,
                                     contour_only=args.contour_only)
