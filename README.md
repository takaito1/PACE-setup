# PACE-setup
Setting up computing environment for GT PACE cluster
  - Your GT username will be the name of your user account
  - When you do this, request a GPU node (V100 would be sufficient)
  
## Setting up your work space
  - set up symbolic links
```
ln -s /storage/project/r-takamitsu3-0/shared shared
ln -s r-takamitsu3-0 work
```

## Setting up the python environment
  - Install miniconda3 on your cluster account
  - Initialize conda command
```
mkdir -p ~/work/miniconda3
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O ~/work/miniconda3/miniconda.sh
bash ~/work/miniconda3/miniconda.sh -b -u -p ~/work/miniconda3
rm -rf ~/work/miniconda3/miniconda.sh
source ~/work/miniconda3/etc/profile.d/conda.sh
conda activate
```
  - Then create a new environment called ml4o2.  
```
conda create --name ml4o2 python=3.11
```
  - Then activate ml4o2.
```
conda activate ml4o2
```
  - Then install mamba in ml4o2.
```
conda install -c conda-forge mamba
```
  - Install packages manually
```
mamba install -c conda-forge numpy matplotlib pandas netcdf4 dask nc-time-axis cartopy seaborn gsw xarray scikit-learn scipy joblib ipykernel ipython pip
```
  - Install PyTorch with GPU support
  - You can check the current CUDA version using nvidia-smi
  - The command below install CUDA version12.1
```
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```
  - Once it is complete, make this environment available to the Jupyter Notebook:
```
python -m ipykernel install --user --name ml4o2 --display-name ML4O2
```
  - At this point the "ML4O2" environment should be ready to use in Jupyterlab/Jupyter Notebook. 
