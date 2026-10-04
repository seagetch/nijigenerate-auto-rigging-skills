"""Options shared by every stage of a PSD run."""
from pathlib import Path
from .data import read_json


def render_images(run):
    origin = Path(run) / 'run-origin.json'
    return origin.is_file() and read_json(origin).get('render_images') is True
