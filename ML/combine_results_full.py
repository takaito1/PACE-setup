#!/usr/bin/env python
"""Combine every per-run `Results_v{ver}.csv` file in this directory into one
archival `Results_all_basins_full.csv`.

Each basin/run notebook execution writes its own `Results_v{ver}.csv` (ver =
alg.run.basin.tsource.predset.hp, e.g. `1.4.1.5.6.4`). The existing
`run_all_basins_RF.py` only combines the basins from its own latest run
(e.g. all `1.4.*` files) into `Results_all_basins_RF.csv`. This script instead
globs *all* `Results_v*.csv` files present on disk -- every run index, every
algorithm (RF ver='1.*' and PyTorch ver='2.*') -- and concatenates them, so
the "_full" file is a complete history rather than just the latest run.

Pre-existing aggregate files (Results_all_basins_RF.csv,
Results_all_basins_PyTorch.csv, Results_ensemble_all.csv, etc.) are not
per-run files -- they don't match the `Results_v*.csv` glob -- so they are
naturally excluded and won't get double-counted.

Usage:
    python combine_results_full.py
"""
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).parent
OUT_PATH = SCRIPT_DIR / 'Results_all_basins_full.csv'


def main():
    csv_paths = sorted(SCRIPT_DIR.glob('Results_v*.csv'))
    csv_paths = [p for p in csv_paths if p != OUT_PATH]

    if not csv_paths:
        print(f'No Results_v*.csv files found in {SCRIPT_DIR}; nothing to combine')
        return

    frames = []
    for csv_path in csv_paths:
        try:
            frames.append(pd.read_csv(csv_path))
        except Exception as exc:
            print(f'  warning: could not read {csv_path.name}: {exc}')

    df_all = pd.concat(frames, ignore_index=True)
    if 'ver' in df_all.columns and 'basin' in df_all.columns:
        df_all = df_all.sort_values(['ver', 'basin']).reset_index(drop=True)

    df_all.to_csv(OUT_PATH, index=False)
    print(f'Combined {len(frames)} file(s) ({len(df_all)} rows) into {OUT_PATH}')


if __name__ == '__main__':
    main()
