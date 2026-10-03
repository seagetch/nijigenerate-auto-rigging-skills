"""Withdrawn entry point: reference Part displacement transfer is prohibited."""
from riglib.reference_materials import require_shape_based_part_solver


def apply(run, njc):
    require_shape_based_part_solver()


if __name__ == '__main__':
    require_shape_based_part_solver()
