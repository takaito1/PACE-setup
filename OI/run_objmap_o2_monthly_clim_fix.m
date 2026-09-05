% %%% run_objmap_o2_monthly_clim_multi
% %%% Driver for objmap_o2_monthly_clim_multi. Runs OI mapping over
% %%% depth levels 1-57 and all 12 months for each
% %%% Oxygen_<source>_1x1bin_mon_clim_lon0to360.nc input file, using
% %%% parfor to spread the 57*12=684 (level,month) tasks per source across
% %%% the node's cores.
% %%%
% %%% Basin mask / grid data are loaded once here and passed into the
% %%% worker function as broadcast variables, instead of being reloaded
% %%% from disk on every one of the 684 task calls -- same pattern as
% %%% run_objmap_o2_annual_clim_multi / run_objmap_o2anom_annual_multi.
% %%%
% %%% Under a SLURM job array (--array=1-N), SLURM_ARRAY_TASK_ID selects
% %%% which single source this job processes (see
% %%% submit_objmap_o2_monthly_clim.sbatch) -- one job per source. Run
% %%% standalone (no array task id set) to process all available sources
% %%% in one session instead.
% %%%
% %%% 'IAP' is listed as a placeholder: its input file
% %%% (Oxygen_IAP_1x1bin_mon_clim_lon0to360.nc) does not exist yet, so it
% %%% is skipped automatically until that file shows up -- only 'NCEI' is
% %%% actually run today.

all_files = {'IAP'};   % Oxygen_<tag>_1x1bin_mon_clim_lon0to360.nc

taskid = str2double(getenv('SLURM_ARRAY_TASK_ID'));
if isnan(taskid)
    files = all_files;
else
    files = all_files(taskid);
end
Nlev = 57;              % process klevel = 1:57 only
months = 12;

% --- load grid / basin mask once ---
mask0 = ncread('basin_mask_01_0-360.nc','basin_mask');
for k = 1:Nlev
   maskk = mask0(:,:,k);
   bind0 = unique(maskk(:));
   bindK{k}.data = bind0(2:end);
end
maskNz = mask0(:,:,1:Nlev);

x = ncread('basin_mask_01_0-360.nc','lon');
y = ncread('basin_mask_01_0-360.nc','lat');
z0 = ncread('basin_mask_01_0-360.nc','depth');
z = z0(1:Nlev);
[yy,xx] = meshgrid(y,x);

% --- flatten (level, month) into one task list per file ---
[K,M] = ndgrid(1:Nlev, months);
K = K(:);
M = M(:);
Ntask = numel(K);
disp(['Tasks per file: ',num2str(Ntask)]);

% --- size the worker pool from the SLURM allocation, not just numcores ---
% NOTE: worst-case memory per task (a large, well-sampled basin like the
% Pacific, borrowing obs south of 30S) needs an explicit inv() of the
% dense obs-obs covariance matrix (the Lagrange-multiplier unbiasedness
% term this worker keeps) -- measured around 15GB for a shallow, heavily-
% sampled level. Pick --cpus-per-task / --mem in the sbatch script so that
% (workers * worst_case_GB) comfortably fits the node.
nw = str2double(getenv('SLURM_CPUS_PER_TASK'));
if isnan(nw) || nw <= 0
    nw = feature('numcores');
end
if isempty(gcp('nocreate'))
    parpool('local', nw);
end
disp(['Using ',num2str(nw),' parallel workers']);

% shuffle task order before handing it to parfor: (K,M) was built via
% ndgrid so shallow levels (the most memory-hungry, most heavily sampled)
% are contiguous in the task list, and parfor's default contiguous-block
% scheduling would assign them to the first N workers all at once --
% exactly the peak-memory pileup that OOM-killed a previous run of the
% annual-clim job built the same way. Randomizing spreads cheap/expensive
% tasks evenly across workers over time.
taskOrder = randperm(Ntask);

for iFile = 1:numel(files)
    tag = files{iFile};
    fn = ['Oxygen_',tag,'_1x1bin_mon_clim_lon0to360.nc'];
    if ~exist(fn,'file')
        disp(['=== Skipping ', tag, ': input file ', fn, ' not found yet ===']);
        continue
    end
    outdir = ['intermed_files_', tag];
    if ~exist(outdir,'dir')
        mkdir(outdir);
    end
    disp(['=== Mapping ', fn, ' -> ', outdir, ' ===']);

    parfor idx = 1:Ntask
        t = taskOrder(idx);
        objmap_o2_monthly_clim_multi(K(t), M(t), fn, outdir, ...
            mask0, bindK, maskNz, x, y, z, xx, yy);
    end
end
