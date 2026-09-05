#!/bin/bash
# One job per input source (Oxygen_{NCEI,IAP}_1x1bin_mon_clim_lon0to360.nc):
# SLURM_ARRAY_TASK_ID selects the source inside
# run_objmap_o2_monthly_clim_multi.m. Each job parfor's over its source's
# 57 levels x 12 months (684 tasks) across --cpus-per-task workers.
#
# 'IAP' is a placeholder in all_files -- its input file does not exist yet,
# so array task 2 (IAP) will just log a skip message and exit until that
# file is available. Only --array=1 (NCEI) does real work today.
#
# The annual-clim job (same worker pattern) OOM-killed on cpu-medium
# (350G/24 workers): this worker keeps the Lagrange-multiplier
# unbiasedness term (needed for correctness), so an explicit inv() of the
# dense obs-obs covariance matrix for a shallow, heavily-sampled basin
# (e.g. Pacific) peaks around 15GB/worker -- worst case ~24 x 15GB =
# 360GB, too tight on a 350G/385G-per-node partition. The driver now
# randomizes task order before parfor so the worst (level,month) tasks
# don't all land on the first N workers at once, but moved to cpu-large
# (772GB/node) as well, keeping all 24 workers with headroom to spare.

#SBATCH --job-name=objmap_o2monclim
#SBATCH -A gts-takamitsu3-atlas
#SBATCH --partition=cpu-large
#SBATCH --array=1
#SBATCH --cpus-per-task=24
#SBATCH --mem=700G
#SBATCH --time=02:00:00
#SBATCH --output=logs/objmapmonclim_%A_%a.out
#SBATCH --error=logs/objmapmonclim_%A_%a.err

cd "/storage/project/r-takamitsu3-0/takamitsu3/GODIP/Ito22_OI_mapping" || exit 1

module load matlab/r2025b

matlab -nodisplay -nosplash -batch "run_objmap_o2_monthly_clim_multi"
