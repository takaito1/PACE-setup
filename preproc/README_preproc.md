## Pre-processing
  - binning of profile data
  - bin_profiles_XXX.ipynb

### Output for the IAP data
  - Oxygen_IAP_1x1bin_ann_clim_lon0to360.nc
  - Oxygen_IAP_1x1bin_mon_clim_lon0to360.nc

### Output for the NCEI data 
  - Oxygen_OSD_1x1bin_1965-2025.nc
  - Oxygen_CTD_1x1bin_1971-2025.nc
  - Oxygen_PFL_1x1bin_2002-2025.nc
  - These files can be combined into a single file using o2_combineQC_202608.ipynb
  - The combined output files are:
  - Oxygen_NCEI_1x1bin_1965-2025.nc
  - Oxygen_NCEI_1x1bin_ann_clim_lon0to360.nc
  - Oxygen_NCEI_1x1bin_mon_clim_lon0to360.nc
