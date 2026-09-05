## (3) preprocess the data (you may skip this unless you know what you are doing)
  - o2_preproc_v2026.ipynb

## (4) run the mapping script in batch mode
  - conda activate calc
  - nohup python run_all_basins_PyTorch.py > run_all_basins_PyTorch.log 2>&1 &
  - Results are intermediate product of year-by-year mapped data

## (5) run the combine script to form a single map
  - python combine_o2_basins.py
