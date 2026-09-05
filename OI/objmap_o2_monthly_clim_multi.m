% %%% objmap_o2_monthly_clim_multi
% %%% Single-(level,month) OI worker for the Oxygen_<source>_1x1bin_mon_clim_lon0to360.nc
% %%% files. Designed to be called from a parfor loop: all basin-mask /
% %%% grid data that used to be reloaded from disk on every call is now
% %%% passed in as arguments (loaded once in the driver, sent to each
% %%% worker as a broadcast variable) -- same refactor as
% %%% objmap_o2_annual_clim_multi / objmap_o2anom_annual_multi.

function dummy = objmap_o2_monthly_clim_multi(klevel, mon, fn, outdir, ...
                                               mask0, bindK, maskNz, x, y, z, xx, yy)

Nx = length(x);
Ny = length(y);

% set parameters
S2N = 5;       % signal to noise ratio in obs
L = 750.0e3;   % e-folding scale for Gaussian covariance function

% load data
mn = ncread(fn, 'o2', [1 1 klevel mon], [360 180 1 1]);
mn(mn<0) = NaN;

k = klevel;
bind = bindK{k}.data;
wn = fullfile(outdir, ['o2map_mon', num2str(mon), '_klev', num2str(k), '.mat']);
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

      % mapping matrix, with Lagrange multiplier term to enforce
      % unbiasedness (weights sum to 1) -- required for absolute fields
      % like climatology
      invUU = inv(UU);
      v = ones(1,N2);
      lmd1 = (1 - VU*invUU*v');
      lmd2 = (v*invUU*v');
      A = (VU + lmd1*v/lmd2)*invUU;

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
