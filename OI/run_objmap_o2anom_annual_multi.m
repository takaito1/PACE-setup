% %%% run_objmap_o2anom_annual_multi
% %%% Driver for objmap_o2anom_annual_multi. Runs OI mapping over all
% %%% 67 depth levels and all 61 years (1965-2025) for each of the three
% %%% o2anom_annual_NCEI_Ito22clim_XXX.nc input files, using parfor to
% %%% spread the 67*61=4087 (level,year) tasks per file across the node's
% %%% cores.
% %%%
% %%% Basin mask / grid / basin-name data are loaded once here and passed
% %%% into the worker function as broadcast variables, instead of being
% %%% reloaded from disk on every one of the 3*4087=12251 task calls.
% %%%
% %%% Under a SLURM job array (--array=1-3), SLURM_ARRAY_TASK_ID selects
% %%% which single file this job processes (see submit_objmap_o2anom.sbatch)
% %%% -- one job per file. Run standalone (no array task id set) to process
% %%% all three files in one session instead.

%all_files = {'S','SA','ScA'};   % o2anom_annual_NCEI_Ito22clim_<tag>.nc
%all_files = {'ScA_eq','ScA_tanh_eq'};

all_files = {'NCEI','IAP'};
%all_files = {'Zhou'};

taskid = str2double(getenv('SLURM_ARRAY_TASK_ID'));
if isnan(taskid)
    files = all_files;
else
    files = all_files(taskid);
end
Nlev = 67;
years = 1:61;                % yid; calendar year = yid+1964, i.e. 1965-2025

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

% --- flatten (level, year) into one task list per file ---
[K,Y] = ndgrid(1:Nlev, years);
K = K(:);
Y = Y(:);
Ntask = numel(K);
disp(['Tasks per file: ',num2str(Ntask)]);

% --- size the worker pool from the SLURM allocation, not just numcores ---
% NOTE: worst-case memory per task (a large, well-sampled basin like the
% Pacific, borrowing obs south of 30S) can run into the multi-GB range for
% the dense obs-obs covariance matrix. Pick --cpus-per-task / --mem in the
% sbatch script so that (workers * worst_case_GB) comfortably fits the
% node, e.g. on cpu-medium (24+ cores, 385GB+) 24 workers is safe.
nw = str2double(getenv('SLURM_CPUS_PER_TASK'));
if isnan(nw) || nw <= 0
    nw = feature('numcores');
end
if isempty(gcp('nocreate'))
    parpool('local', nw);
end
disp(['Using ',num2str(nw),' parallel workers']);

for iFile = 1:numel(files)
    tag = files{iFile};
    fn = ['o2anom_annual_',tag,'_ItoClim_1x1bin_1965-2025.nc'];
    outdir = ['intermed_files_', tag,'_202608'];
    if ~exist(outdir,'dir')
        mkdir(outdir);
    end
    disp(['=== Mapping ', fn, ' -> ', outdir, ' ===']);

    parfor t = 1:Ntask
        objmap_o2anom_annual_multi(K(t), Y(t), fn, outdir, ...
            mask0, bindK, maskNz, x, y, z, xx, yy);
    end
end
