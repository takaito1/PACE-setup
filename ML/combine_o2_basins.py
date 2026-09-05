#!/usr/bin/env python
"""Combines per-basin O2 gapfill reconstructions into a single global field.

Modernized version of combine_data_fast.ipynb: reads the O2map_v{ver}.nc
files produced by o2_project_torch.py for each basin (basins are
non-overlapping and NaN outside their own footprint, so combining is just a
nanmean across basins per grid cell), chunked by depth to bound memory, with
each depth chunk assembled in a worker process.

Basin boundaries are hard mask edges, and adjacent basins are independently-
trained models with no guarantee of agreeing at that edge -- most visibly
between the Southern Ocean (polar-coordinate features) and the Atlantic/
Pacific/Indian (raw lon/lat features) around 50S, where the mismatch shows up
as a visible step in the combined map. `--smooth-band`/`--smooth-sigma-deg`
apply a NaN-aware Gaussian blend across a latitude band to soften this into a
gradual transition, using only the already-combined values (no new inference).

Usage:
    python combine_o2_basins.py --basins 1,2,3,4,5,6,7,8,12
    python combine_o2_basins.py --seeds 0-29   # combine all 30 ensemble members
"""
import argparse
import math
import multiprocessing as mp
import os

# Must be set before HDF5 is initialized: this storage is a GPFS/Lustre-style
# networked mount, and HDF5's default file locking spuriously fails with
# PermissionError under concurrent access from many processes.
os.environ.setdefault('HDF5_USE_FILE_LOCKING', 'FALSE')

from concurrent.futures import ProcessPoolExecutor

import numpy as np
import xarray as xr
from scipy.ndimage import gaussian_filter1d

VER_TEMPLATE = '2.7.{bid}.5.6.4'
DEFAULT_BASINS = '1,2,3,4,5,6,12'

_worker = {}


def n_available_cores():
    try:
        return len(os.sched_getaffinity(0))
    except AttributeError:
        return os.cpu_count() or 4


def parse_int_list(spec):
    """Parses a comma-separated list of ints and/or 'a-b' ranges, e.g.
    '0-29' -> [0..29], '1,2,5-8' -> [1,2,5,6,7,8]."""
    out = []
    for part in spec.split(','):
        part = part.strip()
        if '-' in part:
            lo, hi = part.split('-')
            out.extend(range(int(lo), int(hi) + 1))
        else:
            out.append(int(part))
    return out


def _init_worker(basin_paths, chunk_size, Nz, tmp_dir, smooth_band, smooth_sigma_deg,
                  smooth_lon_band_range, smooth_lon_lat_range, smooth_lon_sigma_deg):
    _worker['basin_paths'] = basin_paths
    _worker['chunk_size'] = chunk_size
    _worker['Nz'] = Nz
    _worker['tmp_dir'] = tmp_dir
    _worker['smooth_band'] = smooth_band
    _worker['smooth_sigma_deg'] = smooth_sigma_deg
    _worker['smooth_lon_band_range'] = smooth_lon_band_range
    _worker['smooth_lon_lat_range'] = smooth_lon_lat_range
    _worker['smooth_lon_sigma_deg'] = smooth_lon_sigma_deg


def _normalized_convolve1d(sub, axis, sigma_deg):
    """NaN-aware 1D Gaussian smoothing along `axis`: blends each valid cell
    with its valid neighbors (weighted by distance), without ever inventing
    a value at a cell that was NaN to begin with. That last part matters
    here specifically -- every NaN in this dataset is deliberate (land, or a
    basin we didn't model, or below the seafloor at that depth), not a
    transient data gap, so a plain normalized convolution (which happily
    fills small NaN holes from nearby valid data) would leak ocean values
    onto land near any coastline that falls inside the smoothing region."""
    valid = ~np.isnan(sub)
    filled = np.where(valid, sub, 0.0)
    num = gaussian_filter1d(filled, sigma=sigma_deg, axis=axis, mode='nearest')
    den = gaussian_filter1d(valid.astype(np.float32), sigma=sigma_deg, axis=axis, mode='nearest')
    smoothed = np.divide(num, den, out=np.full_like(num, np.nan), where=den > 1e-6)
    return np.where(valid, smoothed, np.nan)  # never fabricate a value where there was none


def smooth_lat_band(arr, lat, band, sigma_deg):
    """NaN-aware Gaussian smoothing along the lat axis (second-to-last axis),
    restricted to a latitude band, to soften the hard edge where two basins
    meet. Working on the already-combined field rather than re-running
    inference means there's no second prediction to blend with in the
    transition zone -- this instead blends each basin's own edge values with
    its neighbor's.

    This smooths uniformly across the whole band at every longitude, not
    just where a basin boundary actually falls -- simpler than detecting the
    boundary's exact shape, at the cost of mildly blurring genuine
    within-basin structure inside the band everywhere, not only at seams."""
    if sigma_deg <= 0:
        return arr
    lat_axis = arr.ndim - 2
    in_band = (lat >= band[0]) & (lat <= band[1])
    if not np.any(in_band):
        return arr
    band_idx = np.where(in_band)[0]
    # extend beyond the band so the kernel (truncated at ~4 sigma) has real
    # neighbors to draw from at the band's own edges
    pad = int(np.ceil(4 * sigma_deg))
    lo = max(band_idx.min() - pad, 0)
    hi = min(band_idx.max() + pad + 1, lat.size)

    smoothed = _normalized_convolve1d(arr[..., lo:hi, :], lat_axis, sigma_deg)

    out = arr.copy()
    band_lo = band_idx.min() - lo
    band_hi = band_idx.max() - lo + 1
    out[..., lo + band_lo:lo + band_hi, :] = smoothed[..., band_lo:band_hi, :]
    return out


def smooth_lon_band(arr, lon, lat, lon_range, lat_range, sigma_deg):
    """NaN-aware Gaussian smoothing along the lon axis (last axis), restricted
    to a lon range AND a lat range -- for a seam that runs roughly N-S over a
    limited latitude span rather than a zonal seam spanning all longitudes,
    e.g. the Atlantic/Indian boundary south of Africa near 20E, which only
    matters between the tip of South Africa and where the Southern Ocean
    band (smooth_lat_band) takes over."""
    if sigma_deg <= 0:
        return arr
    lon_axis = arr.ndim - 1
    lat_idx = np.where((lat >= lat_range[0]) & (lat <= lat_range[1]))[0]
    lon_idx = np.where((lon >= lon_range[0]) & (lon <= lon_range[1]))[0]
    if lat_idx.size == 0 or lon_idx.size == 0:
        return arr

    pad = int(np.ceil(4 * sigma_deg))
    lon_lo = max(lon_idx.min() - pad, 0)
    lon_hi = min(lon_idx.max() + pad + 1, lon.size)
    lat_lo, lat_hi = lat_idx.min(), lat_idx.max() + 1  # no padding: not smoothing along lat here

    smoothed = _normalized_convolve1d(arr[..., lat_lo:lat_hi, lon_lo:lon_hi], lon_axis, sigma_deg)

    out = arr.copy()
    band_lo = lon_idx.min() - lon_lo
    band_hi = lon_idx.max() - lon_lo + 1
    out[..., lat_lo:lat_hi, lon_lo + band_lo:lon_lo + band_hi] = smoothed[..., band_lo:band_hi]
    return out


def _assemble_chunk(n):
    """Runs in a worker process: for depth levels [n*chunk_size, ...), loads
    every basin's o2est at that depth range for all months, combines them
    with a nanmean across basins (they don't overlap, so this just picks
    whichever basin actually covers each grid cell), and writes one NetCDF
    chunk file. Looping over time rather than loading the full (time, depth,
    lat, lon) array per basin keeps peak memory bounded."""
    basin_paths = _worker['basin_paths']
    chunk_size = _worker['chunk_size']
    Nz = _worker['Nz']
    tmp_dir = _worker['tmp_dir']

    n0 = n * chunk_size
    n1 = min(n0 + chunk_size, Nz)
    dz = n1 - n0

    dsets = [xr.open_dataset(p) for p in basin_paths]
    Nt = dsets[0].sizes['time']
    Ny = dsets[0].sizes['lat']
    Nx = dsets[0].sizes['lon']

    o2 = np.full((Nt, dz, Ny, Nx), np.nan, dtype=np.float32)
    tmp = np.empty((len(dsets), dz, Ny, Nx), dtype=np.float32)
    for t in range(Nt):
        for b, ds in enumerate(dsets):
            tmp[b] = ds.o2est[t, n0:n1, :, :].to_numpy()
        combined = np.nanmean(tmp, axis=0)
        o2[t] = np.where(combined == 0, np.nan, combined)

    z, x, y, time = dsets[0].depth[n0:n1], dsets[0].lon, dsets[0].lat, dsets[0].time
    for ds in dsets:
        ds.close()

    o2 = smooth_lat_band(o2, y.values, _worker['smooth_band'], _worker['smooth_sigma_deg'])
    o2 = smooth_lon_band(o2, x.values, y.values, _worker['smooth_lon_band_range'],
                          _worker['smooth_lon_lat_range'], _worker['smooth_lon_sigma_deg'])

    da = xr.DataArray(o2, name='o2est', dims=['time', 'depth', 'lat', 'lon'],
                       coords={'time': time, 'depth': z, 'lat': y, 'lon': x})
    outpath = os.path.join(tmp_dir, f'o2_global_chunk{n:02d}.nc')
    da.to_dataset().to_netcdf(outpath)
    return outpath


def parse_args():
    p = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--basins', default=DEFAULT_BASINS,
                    help='comma-separated basin ids whose O2map_v{ver}.nc files to combine')
    p.add_argument('--seeds', default=None,
                    help="comma-separated seeds and/or 'a-b' ranges (e.g. '0-29') -- combines "
                         "O2map_v{ver}_seed{seed}.nc per basin (from run_o2_project_torch_all_basins.py "
                         "--seeds) into one O2map_v{global_ver}_seed{seed}.nc per seed. "
                         "Default: unset, single combine with no seed (today's behavior).")
    p.add_argument('--ver-template', default=VER_TEMPLATE,
                    help="ver string with '{bid}' where the basin digit goes")
    p.add_argument('--chunk-size', type=int, default=10, help='depth levels per chunk')
    p.add_argument('--workers', type=int, default=None,
                    help='worker processes (default: available cores - 1)')
    p.add_argument('--output', default=None,
                    help="output filename (default: O2map_v{ver_template with bid=ALL}.nc)")
    p.add_argument('--smooth-band', type=float, nargs=2, default=(-55.0, -45.0),
                    metavar=('LAT_MIN', 'LAT_MAX'),
                    help='latitude band (deg) to smooth across basin transitions, '
                         'e.g. the Southern Ocean/Atlantic-Pacific-Indian seam near 50S')
    p.add_argument('--smooth-sigma-deg', type=float, default=2.0,
                    help='Gaussian sigma (deg latitude) for the transition smoothing; 0 disables it')
    p.add_argument('--smooth-lon-band', type=float, nargs=2, default=(15.0, 25.0),
                    metavar=('LON_MIN', 'LON_MAX'),
                    help='longitude band (deg) to smooth across the Atlantic/Indian seam '
                         'south of Africa, e.g. near 20E')
    p.add_argument('--smooth-lon-lat-range', type=float, nargs=2, default=(-50.0, -34.0),
                    metavar=('LAT_MIN', 'LAT_MAX'),
                    help='latitude range where the Africa lon-smoothing applies -- '
                         'the tip of South Africa down to where smooth-band takes over')
    p.add_argument('--smooth-lon-sigma-deg', type=float, default=2.0,
                    help='Gaussian sigma (deg longitude) for the Africa seam smoothing; 0 disables it')
    return p.parse_args()


def combine_one(args, basins, results_dir, seed=None):
    suffix = '' if seed is None else f'_seed{seed}'
    tag = 'seed=' + str(seed) if seed is not None else 'single run'
    print(f'--- combining ({tag}) ---')

    scratch = f'{os.environ["HOME"]}/scratch'
    tmp_subdir = f'{scratch}/ML4O2_temp/global_combine{suffix}'
    os.makedirs(tmp_subdir, exist_ok=True)

    basin_paths = [os.path.join(results_dir, f'O2map_v{args.ver_template.format(bid=b)}{suffix}.nc')
                    for b in basins]
    missing = [p for p in basin_paths if not os.path.exists(p)]
    if missing:
        raise FileNotFoundError(f'missing basin output(s): {missing}')

    ds0 = xr.open_dataset(basin_paths[0])
    Nz = ds0.sizes['depth']
    ds0.close()
    n_chunks = math.ceil(Nz / args.chunk_size)
    print(f'{len(basins)} basins, Nz={Nz}, {n_chunks} depth chunks of size {args.chunk_size}')

    n_workers = args.workers or max(1, n_available_cores() - 1)
    print(f'using {n_workers} worker processes')
    if args.smooth_sigma_deg > 0:
        print(f'smoothing basin transitions in lat band {args.smooth_band} '
              f'(sigma={args.smooth_sigma_deg} deg)')
    if args.smooth_lon_sigma_deg > 0:
        print(f'smoothing Africa seam in lon band {args.smooth_lon_band}, '
              f'lat range {args.smooth_lon_lat_range} (sigma={args.smooth_lon_sigma_deg} deg)')

    # spawn, not fork: HDF5/netCDF4 isn't fork-safe, and this process has
    # already opened a netCDF file (ds0) by this point.
    with ProcessPoolExecutor(max_workers=n_workers, mp_context=mp.get_context('spawn'),
                              initializer=_init_worker,
                              initargs=(basin_paths, args.chunk_size, Nz, tmp_subdir,
                                        args.smooth_band, args.smooth_sigma_deg,
                                        args.smooth_lon_band, args.smooth_lon_lat_range,
                                        args.smooth_lon_sigma_deg)) as pool:
        chunk_paths = list(pool.map(_assemble_chunk, range(n_chunks)))
        for p in chunk_paths:
            print(f'wrote {p}')

    ds_all = xr.open_mfdataset(sorted(chunk_paths))
    global_ver = args.ver_template.format(bid='ALL')
    outpath = os.path.join(results_dir, args.output or f'O2map_v{global_ver}{suffix}.nc')
    ds_all.to_netcdf(outpath)
    print(f'wrote {outpath}')


def main():
    args = parse_args()
    basins = [int(b) for b in args.basins.split(',')]
    seeds = parse_int_list(args.seeds) if args.seeds else [None]
    if args.output and len(seeds) > 1:
        raise ValueError('--output cannot be used with --seeds (would collide across seeds); '
                          'omit --output to use the default O2map_v{ver}_seed{seed}.nc naming')

    scratch = f'{os.environ["HOME"]}/scratch'
    results_dir = f'{scratch}/ML4O2_results'

    for seed in seeds:
        combine_one(args, basins, results_dir, seed=seed)


if __name__ == '__main__':
    main()
