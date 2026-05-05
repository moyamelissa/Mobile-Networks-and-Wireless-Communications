from pathlib import Path
import sys
from pathlib import Path
repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root))

import cairosvg

IN_DIR = Path('diagrams')
OUT_DIR = IN_DIR
OUT_DIR.mkdir(exist_ok=True)

svg_files = list(IN_DIR.glob('*.svg'))
if not svg_files:
    print('No SVG files found in diagrams/')
    raise SystemExit(1)

for svg in svg_files:
    png_path = svg.with_suffix('.png')
    try:
        cairosvg.svg2png(url=str(svg), write_to=str(png_path))
        print(f'Wrote {png_path}')
    except Exception as e:
        print(f'Failed to convert {svg}: {e}')
