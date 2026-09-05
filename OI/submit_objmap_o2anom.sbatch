#!/bin/bash
# One job per input file (o2anom_annual_NCEI_Ito22clim_{S,SA,ScA}.nc):
# SLURM_ARRAY_TASK_ID 1/2/3 selects the file inside
# run_objmap_o2anom_annual_multi.m. Each job parfor's over its file's
# 67 levels x 61 years (4087 tasks) across --cpus-per-task workers.
#
# Sized for the cpu-medium partition (24+ cores, 385GB+ per node): 24
# workers x ~10GB worst-case (large, well-sampled basin) comfortably
# fits under the 350G requested here. Adjust --mem/--cpus-per-task
# together if you move to a different partition.

#SBATCH --job-name=objmap_o2anom
#SBATCH -A gts-takamitsu3-atlas
#SBATCH --partition=cpu-medium
#SBATCH --array=1-2
#SBATCH --cpus-per-task=24
#SBATCH --mem=350G
#SBATCH --time=04:00:00
#SBATCH --output=logs/objmap_%A_%a.out
#SBATCH --error=logs/objmap_%A_%a.err

cd "/storage/project/r-takamitsu3-0/takamitsu3/GODIP/Ito22_OI_mapping" || exit 1

module load matlab/r2025b

matlab -nodisplay -nosplash -batch "run_objmap_o2anom_annual_multi"
