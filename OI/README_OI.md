## (3) Optimal interpolation of climatological means
- parallel execution on PACE cluster
- sbatch submit_objmap_o2_annual_clim.sbatch
- sbatch submit_objmap_o2_monthly_clim.sbatch
- then, generate netCDF file
- python gen_netcdf_ann_clim.py
- python gen_netcdf_mon_clim.py
* output: 
- o2_NCEI_ann_clim_65C5.nc
- o2_NCEI_mon_clim_65C5.nc

## (4) Subtract climatology from the binned data to generate anomaly
- bin_anomaly_profiles.ipynb
- compare_bindata_clim.ipynb
- At this time, the climatological data is rotated by 180 degree in long again
- And compare against the existing o2 anomaly data for quick check
* output
- o2anom_NCEI_ItoClim_1x1bin_1965-2025.nc

## (5) Optimal interpolation of yearly anomaly fields
- sbatch submit_objmap_o2anom.batch
- python gen_netcdf_anom_multi.py
* outout
- o2anom_NCEI_ItoClim_65C5.nc
