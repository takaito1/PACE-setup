#!/usr/bin/env python
"""Run GTMLO2_PyTorch_single.ipynb once per ocean basin.

For each requested basin, this patches the `ver = '...'` line in the
notebook's config cell so only the 3rd digit (basin) changes -- the other
digits (data-source/T-S-source/predictor-set; the 1st and 6th digits aren't
used by this notebook) are kept as they are in the notebook on disk --
executes the notebook end to end, and saves the executed copy under
basin_runs_PyTorch/. Each basin's own final cell writes a
`Results_v{ver}.csv` (see the notebook's results-accumulator/df_results
cell); this script concatenates all of those into one combined
`Results_all_basins_PyTorch.csv`.

Basins are run sequentially in a single process, since the notebook trains
on one GPU. This notebook's kernel (`ml4o2`, for PyTorch) must be the active
environment when this script itself is launched -- the kernel is resolved
by name ("python3") from the currently active env's own
sys.prefix/share/jupyter/kernels, not from anything encoded in the notebook.
To run this in the background, use nohup/disown from the shell:

    conda activate ml4o2
    nohup python run_all_basins_PyTorch.py > run_all_basins_PyTorch.log 2>&1 &
    disown

Usage:
    python run_all_basins_PyTorch.py                # default basin subset (see BASIN_IDS below)
    python run_all_basins_PyTorch.py 2 4 5           # only Pacific, Southern, Arctic
"""
import re
import sys
import traceback
from pathlib import Path

import nbformat
import pandas as pd
from nbclient import NotebookClient
from nbclient.exceptions import CellExecutionError

NOTEBOOK = Path(__file__).parent / 'GTMLO2_PyTorch_single.ipynb'
OUTDIR = Path(__file__).parent / 'basin_runs_PyTorch'

BASINS = ['atlantic', 'pacific', 'indian', 'southern', 'arctic',
          'mediterranean', 'baltic', 'black', 'red', 'persian',
          'hudson', 'japan-east', 'caspian']

# basins with input data available for this pipeline (excludes red/persian/hudson/caspian)
BASIN_IDS = [1, 2, 3, 4, 5, 6, 12]

VER_RE = re.compile(r"^ver\s*=\s*'[^']*'", re.MULTILINE)


def make_ver(template_ver, basin_idx):
    """Swap only the 3rd (basin) digit of an existing ver string."""
    digits = template_ver.split('.')
    digits[2] = str(basin_idx)
    return '.'.join(digits)


def get_template_ver(nb):
    for cell in nb.cells:
        if cell.cell_type == 'code':
            m = VER_RE.search(cell.source)
            if m:
                return m.group(0).split("'")[1]
    raise RuntimeError("could not find a `ver = '...'` line in the notebook")


def run_one_basin(template_nb, template_ver, basin_idx):
    ver = make_ver(template_ver, basin_idx)
    name = BASINS[basin_idx - 1]
    print(f'=== basin {basin_idx:2d} ({name}): ver={ver} ===', flush=True)

    nb = nbformat.from_dict(template_nb)

    patched = False
    for cell in nb.cells:
        if cell.cell_type == 'code' and VER_RE.search(cell.source):
            cell.source = VER_RE.sub(f"ver = '{ver}'", cell.source, count=1)
            patched = True
            break
    if not patched:
        raise RuntimeError("could not find a `ver = '...'` line to patch")

    # fresh run: drop any stale outputs/execution counts carried over from disk
    for cell in nb.cells:
        if cell.cell_type == 'code':
            cell.outputs = []
            cell.execution_count = None

    # kernel_name explicitly set to "python3" (rather than relying on the
    # notebook's own metadata.kernelspec.name) so a kernel picked from
    # Jupyter's UI doesn't silently break this script by rewriting that
    # metadata to something unregistered, e.g. "conda-env-...-py". "python3"
    # resolves to whichever conda env is active when this script is run;
    # must be ml4o2 for PyTorch.
    client = NotebookClient(nb, timeout=-1, kernel_name='python3',
                             resources={'metadata': {'path': str(NOTEBOOK.parent)}})
    status = 'ok'
    try:
        client.execute()
    except CellExecutionError:
        status = 'FAILED'
        traceback.print_exc()
    finally:
        OUTDIR.mkdir(exist_ok=True)
        out_path = OUTDIR / f'GTMLO2_PyTorch_single_basin{basin_idx:02d}_{name}.ipynb'
        nbformat.write(nb, out_path)
        print(f'  -> wrote {out_path} [{status}]', flush=True)

    return status, ver, name


def main():
    basin_ids = [int(a) for a in sys.argv[1:]] if len(sys.argv) > 1 else BASIN_IDS

    template_nb = nbformat.read(NOTEBOOK, as_version=4)
    template_ver = get_template_ver(template_nb)
    print(f'template ver on disk: {template_ver!r} (only digit 3, the basin, will be varied)')
    print(f'basins to run: {[BASINS[b - 1] for b in basin_ids]}')

    statuses = []
    for basin_idx in basin_ids:
        status, ver, name = run_one_basin(template_nb, template_ver, basin_idx)
        statuses.append((basin_idx, name, ver, status))

    print('\n=== summary ===')
    for basin_idx, name, ver, status in statuses:
        print(f'  {basin_idx:2d}  {name:15s} {ver:15s} {status}')

    # each basin's own notebook run wrote its own Results_v{ver}.csv (see the
    # df_results cell in the notebook); gather them
    frames = []
    for basin_idx, name, ver, status in statuses:
        if status != 'ok':
            continue
        csv_path = NOTEBOOK.parent / f'Results_v{ver}.csv'
        if csv_path.exists():
            frames.append(pd.read_csv(csv_path))
        else:
            print(f'  warning: expected {csv_path} not found for basin {name}')

    if frames:
        df_all = pd.concat(frames, ignore_index=True)
        combined_path = NOTEBOOK.parent / 'Results_all_basins_PyTorch.csv'
        df_all.to_csv(combined_path, index=False)
        print(f'\nWrote combined results for {len(frames)} basin(s) to {combined_path} '
              f'({len(df_all)} rows)')
    else:
        print('\nNo per-basin result CSVs found; Results_all_basins_PyTorch.csv not written')


if __name__ == '__main__':
    main()
