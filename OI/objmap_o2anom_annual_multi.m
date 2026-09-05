% %%% objmap_o2anom_annual_multi
% %%% Single-(level,year) OI worker for the o2anom_annual_NCEI_Ito22clim_XXX.nc
% %%% files. Designed to be called from a parfor loop: all basin-mask /
% %%% grid data that used to be reloaded from disk on every call is now
% %%% passed in as arguments (loaded once in the driver, sent to each
% %%% worker as a broadcast variable).
% %%%
% %%% The input data are sparse in time, so a 5-year centered running mean
% %%% (clipped near the 1965/2025 edges) is applied before mapping to fill
% %%% temporal gaps -- same windowing logic as objmap_o2anom_DOMIP.

function dummy = objmap_o2anom_annual_multi(klevel, yid, fn, outdir, ...
                                             mask0, bindK, maskNz, x, y, z, xx, yy)

Nx = length(x);
Ny = length(y);
year = yid + 1964;

% set parameters
S2N = 5;       % signal to noise ratio in obs
L = 750.0e3;   % e-folding scale for Gaussian covariance function

% load a 5-year window of the annual anomaly at this level, clipped near
% the ends of the record (1965 and 2025), then average over the window
if (year >= 1967) && (year <= 2023)
    mn0 = ncread(fn, 'o2anom', [1 1 klevel yid-2], [360 180 1 5]);
elseif year < 1967
    mn0 = ncread(fn, 'o2anom', [1 1 klevel 1], [360 180 1 2+yid]);
else
    mn0 = ncread(fn, 'o2anom', [1 1 klevel yid-2], [360 180 1 61-yid+3]);
end
mn = nanmean(mn0, 4);

k = klevel;
bind = bindK{k}.data;
wn = fullfile(outdir, ['o2map_', num2str(year), '_klev', num2str(k), '.mat']);
o2map = zeros(360, 180);

for b = 1:length(bind)
   % extract data
   dd = squeeze(mn(:,:,1));
   bb = mask0(:,:,k);
   b0 = bb(:);
   d0 = dd(:);
   x0 = xx(:);
   y0 = yy(:);
   Y0 = zeros(size(x0));

   % use data only from the adjacent basin; Atlantic/Pacific/Indian/Southern
   % (1,2,3,10) also borrow obs from south of 30S since the Southern Ocean
   % connects them
   if b<=3 || b==10
      I = find(~isnan(d0) & (b0==bind(b) | y0<-30));
      J = find(b0==bind(b));
   else
      I = find(~isnan(d0) & b0==bind(b));
      J = find(b0==bind(b));
   end

   if ~isempty(I)
      d2 = d0(I);
      x2 = x0(I);
      y2 = y0(I);
      N2 = length(d2);
      x0j = x0(J);
      y0j = y0(J);
      N0 = length(x0j);

      % distance between two points in obs
      f = pi/180;
      dlon = repmat(x2,[1 N2]) - repmat(x2',[N2 1]);
      ds = acos(sin(f*y2)*sin(f*y2')+cos(f*y2)*cos(f*y2').*cos(f*dlon));
      dl = 6.371e6*real(ds);

      % obs-obs gaussian covariance function
      UU = exp(-.5*(dl/L).^2) + 1/S2N*eye(N2);

      % D(m,n): m: grid point, n: obs point ref, non-square (N0,N2)
      f = pi/180;
      dlon = repmat(x0j,[1 N2]) - repmat(x2',[N0 1]);
      ds = acos(sin(f*y0j)*sin(f*y2')+cos(f*y0j)*cos(f*y2').*cos(f*dlon));
      dl = 6.371e6*real(ds);
      % obs-grid gaussian covariance function
      VU = exp(-.5*(dl/L).^2);

      % mapping matrix (solved via mrdivide instead of forming inv(UU)
      % explicitly: faster and more numerically stable)
      A = VU/UU;

      %% map it
      Y = A*d2;
      Y0(J) = Y;
      Test = reshape(Y0,[Nx,Ny]);
      o2map = o2map + Test;
      o2map(maskNz(:,:,k)==0) = NaN;
   end
end

o2_mn = mn;
save('-v7.3', wn, 'o2map', 'o2_mn', 'x', 'y', 'z');
dummy = 0;
