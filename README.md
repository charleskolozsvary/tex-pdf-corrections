# Package and environment structure
I use conda for the virtual environment and poetry for package installation and dependency management.

## conda environment
Create the conda environment from `environment.yaml` with
```shell
conda env create -f environment.yaml
```
Activate and deactivate the environment with
```shell
conda activate texpdfannots
conda deactivate
```

## python packages
After activating the conda environment, run
```shell
poetry install
```