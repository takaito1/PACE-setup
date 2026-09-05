#!/usr/bin/env python3
"""Python translation of gen_netcdf_anom_multi.m.

Assembles annual O2-anomaly maps (1965-2025, 67 depth levels) from the
per-year/per-level ``o2map_<year>_klev<k>.mat`` files, masks land with
``basin_mask_01_0-360.nc``, applies the same two smoothing passes as the
original script (meridional near the Southern Ocean boundary, then
vertical), and writes a CF-compliant NetCDF4 file.

Notes on the translation (things that are NOT a 1:1 textual port):

* The .mat files are MATLAB v7.3 (HDF5), so they are read with h5py, not
  scipy.io.loadmat. h5py returns each array with axes reversed relative to
  MATLAB's native (column-major) shape, e.g. MATLAB's 360x180 ``o2map``
  reads back as (180, 360) = (lat, lon). This is used deliberately below
  instead of transposing back, because it lines up exactly with how
  netCDF4-python reads ``basin_mask`` (also un-reversed, (depth, lat, lon)).
* The output variable is written with dimension order
  (time, depth, lat, lon) -- the standard CF/xarray convention -- instead
  of MATLAB's literal (lon, lat, depth, time), which only came from the
  low-level netcdf.defVar dimid order. Values are identical; only the
  on-disk axis order differs. Same for depth_bnds: (depth, bnds) here vs.
  (bnds, depth) in the original.
* ``time`` is written as the raw calendar year (1965, 1966, ...), exactly
  like the original T=1965:2025 -- note this does NOT actually match the
  declared units "days since 1980-01-01 00:00:00" in either the original
  or this translation. That mismatch is preserved faithfully, not fixed.
* x/y/z are read once (from the first file) instead of on every one of the
  4087 loop iterations, since the grid is assumed constant across files
  (same assumption the original relies on when it uses the last-loaded
  x/y/z after the loop).
"""
import warnings
from datetime import datetime
from pathlib import Path

import h5py
import netCDF4 as nc
import numpy as np

BASE_DIR = Path(__file__).resolve().parent
MASK_FILE = BASE_DIR / "basin_mask_01_0-360.nc"
INTERMED_DIR = BASE_DIR / "intermed_files_IAP"
OUT_FILE = BASE_DIR / "o2_IAP_ann_clim_65C5.nc"

YEARS = [2025]#list(range(1965, 2026))  # 61 years
NLEV = 102
YC = -50.0  # Southern Ocean boundary (deg N)
YC_HALFWIDTH = 6.0
FILL_VALUE = -99999.0


def movmean3_omitnan(a, axis):
    """3-point centered running mean matching MATLAB's
    movmean(a, [1 1], axis, 'omitnan'): shrinking window at the edges,
    NaNs ignored within the window. Padding the array with NaN and taking
    nanmean over the 3-slice stack reproduces both behaviors at once,
    since an out-of-range neighbor and a NaN neighbor are both simply
    excluded from the mean.
    """
    pad_width = [(0, 0)] * a.ndim
    pad_width[axis] = (1, 1)
    padded = np.pad(a, pad_width, mode="constant", constant_values=np.nan)
    n = a.shape[axis]

    def sl(start):
        idx = [slice(None)] * a.ndim
        idx[axis] = slice(start, start + n)
        return tuple(idx)

    stacked = np.stack([padded[sl(0)], padded[sl(1)], padded[sl(2)]], axis=0)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)  # all-NaN window -> NaN
        return a #np.nanmean(stacked, axis=0)


def main():
    # ---- load mask: (depth, lat, lon), matches file order directly ----
    with nc.Dataset(MASK_FILE) as mf:
        mask0 = np.asarray(mf.variables["basin_mask"][:])

    # ---- grid (assumed constant across all files) ----
    first_file = INTERMED_DIR / f"o2map_ann_klev1.mat"
    with h5py.File(first_file, "r") as f:
        x = np.asarray(f["x"][:]).ravel()
        y = np.asarray(f["y"][:]).ravel()
        z = np.asarray(f["z"][:]).ravel()

    an = np.full((len(YEARS), NLEV, len(y), len(x)), np.nan, dtype=np.float64)

    for mi, year in enumerate(YEARS):
        for k in range(1, NLEV + 1):
            fn = INTERMED_DIR / f"o2map_ann_klev{k}.mat"
            with h5py.File(fn, "r") as f:
                o2map = np.asarray(f["o2map"][:])  # (lat, lon)
            maskk = mask0[k - 1, :, :]  # (lat, lon)
            o2map = np.where(maskk == 0, np.nan, o2map)
            an[mi, k - 1, :, :] = o2map

    # ---- meridional smoothing near the Southern Ocean boundary ----
    J = np.where((y > (YC - YC_HALFWIDTH)) & (y < (YC + YC_HALFWIDTH)))[0]
    an[:, :, J, :] = movmean3_omitnan(an[:, :, J, :], axis=2)

    # ---- vertical smoothing (3-point running mean) ----
    an = movmean3_omitnan(an, axis=1)

    # ---- fill value handling (NaN and exact-zero both -> fill) ----
    V = an.copy()
    V[np.isnan(V)] = FILL_VALUE
    V[V == 0] = FILL_VALUE

    # ---- depth bounds (ZF), replicated including ZF(1)==0 default ----
    nz = len(z)
    dz = np.diff(z)
    zf = np.zeros(nz + 1)
    zf[1:nz] = 0.5 * (z[:-1] + z[1:])
    zf[nz] = zf[nz - 1] + dz[-1]
    depth_bnds = np.stack([zf[:-1], zf[1:]], axis=1)  # (depth, bnds)

    T = (np.asarray(YEARS, dtype=np.float64)-1980)*365.25  # raw years, not converted to days-since (see docstring)

    # ---- write NetCDF ----
    with nc.Dataset(OUT_FILE, "w", format="NETCDF4") as ds:
        ds.createDimension("lon", len(x))
        ds.createDimension("lat", len(y))
        ds.createDimension("depth", nz)
        ds.createDimension("bnds", 2)
        ds.createDimension("time", len(T))

        v = ds.createVariable("lon", "f8", ("lon",), fill_value=FILL_VALUE)
        v.standard_name = "lon"
        v.long_name = "longitude"
        v.units = "degrees_east"
        v[:] = x

        v = ds.createVariable("lat", "f8", ("lat",), fill_value=FILL_VALUE)
        v.standard_name = "lat"
        v.long_name = "latitude"
        v.units = "degrees_north"
        v[:] = y

        v = ds.createVariable("depth", "f8", ("depth",), fill_value=FILL_VALUE)
        v.standard_name = "depth"
        v.long_name = "depth from the surface ocean"
        v.units = "m"
        v.bounds = "depth_bnds"
        v[:] = z

        v = ds.createVariable("depth_bnds", "f8", ("depth", "bnds"), fill_value=FILL_VALUE)
        v.standard_name = "depth"
        v.units = "m"
        v[:, :] = depth_bnds

        v = ds.createVariable("time", "f8", ("time",), fill_value=FILL_VALUE)
        v.standard_name = "time"
        v.long_name = "time"
        v.units = "days since 1980-01-01 00:00:00"
        v[:] = T

        ds.title = "objectively mapped dissolved oxygen based on IAP QC data"
        ds.Conventions = "CF-1.6"
        ds.CreationDate = datetime.now().strftime("%Y/%m/%d %H:%M:%S")

        vo = ds.createVariable(
            "o2", "f8", ("time", "depth", "lat", "lon"), fill_value=FILL_VALUE
        )
        vo.long_name = "objective map of dissolved oxygen based on IAP QC data"
        vo.units = "micro-molO2/kg"
        vo[:] = V

    print(f"wrote {OUT_FILE}")


if __name__ == "__main__":
    main()
