#!/bin/bash
# One job per input source (Oxygen_{NCEI,IAP}_1x1bin_ann_clim_lon0to360.nc):
# SLURM_ARRAY_TASK_ID selects the source inside
# run_objmap_o2_annual_clim_multi.m. Each job parfor's over its source's
# 102 levels across --cpus-per-task workers.
#
# 'IAP' is a placeholder in all_files -- its input file does not exist yet,
# so array task 2 (IAP) will just log a skip message and exit until that
# file is available. Only --array=1 (NCEI) does real work today.
#
# First attempt used cpu-medium (350G/24 workers) and got OOM-killed:
# this worker keeps the Lagrange-multiplier unbiasedness term (needed for
# correctness -- verified against the original serial function), which
# means an explicit inv() of the dense obs-obs covariance matrix for a
# shallow, heavily-sampled basin (e.g. Pacific) peaks around 15GB/worker.
# The driver now randomizes level order before parfor so the worst levels
# don't all land on the first N workers at once, but the true worst case
# is still ~24 x 15GB = 360GB -- too tight on a 350G/385G-per-node
# partition. Moved to cpu-large (772GB/node) instead, keeping all 24
# workers, with headroom to spare. Walltime bumped up since the earlier
# 30min budget was too tight even before the OOM churn.

#SBATCH --job-name=objmap_o2anom
#SBATCH -A gts-takamitsu3-atlas
#SBATCH --partition=cpu-large
#SBATCH --array=1
#SBATCH --cpus-per-task=24
#SBATCH --mem=700G
#SBATCH --time=03:00:00
#SBATCH --output=logs/objmapclim_%A_%a.out
#SBATCH --error=logs/objmapclim_%A_%a.err

cd "~/work/PACE-setup/OI" || exit 1

module load matlab/r2025b

matlab -nodisplay -nosplash -batch "run_objmap_o2_annual_clim_multi"
